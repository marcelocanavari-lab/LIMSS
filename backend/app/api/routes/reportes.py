"""
Reportes transversales (no ligados a una sola pantalla de gestión) -- hoy
solo el Libro de Ingresos (Materia Prima / Material de Empaque), pensado
como el lugar donde agregar futuros reportes de auditoría/gestión.
"""
import csv
import io
from datetime import date
from typing import Optional

import pyodbc
from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response

from app.core.security import require_rol
from app.db.connections import limss_db
from app.schemas.reportes import LibroIngresosLinea
from app.services.bultos import obtener_grupos_bultos
from app.services.formato import formatear_cantidad

router = APIRouter(prefix="/api/reportes", tags=["Reportes"])

_ROLES_GESTION = ("analista_qc", "qa", "admin")


def _fecha_vencimiento_o_vacio(valor):
    """Igual criterio que normalizar_fecha_sentinel (erp_ir.py: NULL o el
    sentinel 1899-12-30 del ERP se muestran vacíos, no la fecha literal) --
    pero no se reutiliza esa función porque asume un date/datetime nativo
    (así lo devuelve la conexión al ERP) y acá, con el driver ODBC "SQL
    Server" de la conexión a LIMSS, una columna DATE llega como str (mismo
    tipo de limitación de driver ya documentada en otros módulos de este
    proyecto para datetime.date en parámetros, acá del lado de lectura) --
    se compara como texto en vez de acceder a .year. El valor se devuelve
    tal cual (str u date) para que LibroIngresosLinea (Optional[date]) lo
    parsee normal cuando no es el sentinel."""
    if not valor:
        return None
    return None if str(valor)[:10] == "1899-12-30" else valor


def _formatear_bultos_detalle(cursor, id_solicitud: Optional[int], nro_bultos: Optional[int]) -> Optional[str]:
    """"4 x 50 kg, 1 x 30 kg" a partir de lims_solicitud_bultos (mismo
    origen que ya usan las etiquetas CUARENTENA/APROBADO/RECHAZADO, ver
    expandir_bultos en app/services/bultos.py) -- sin grupos cargados
    (solicitud vieja, o sin id_solicitud), se cae a "N bultos" sin detalle
    por grupo, mismo criterio de fallback que el resto del sistema."""
    if id_solicitud is None:
        return None
    grupos = obtener_grupos_bultos(cursor, id_solicitud)
    if grupos:
        return ", ".join(
            f"{g.cantidad_bultos} x {formatear_cantidad(g.cantidad_unidades)} {g.unidad_medida or ''}".strip()
            for g in grupos
        )
    if nro_bultos:
        return f"{nro_bultos} bultos"
    return None


def _obtener_libro_ingresos(cursor, fecha_desde: Optional[date], fecha_hasta: Optional[date]) -> list[LibroIngresosLinea]:
    """Una fila por muestra de Materia Prima/Material de Empaque
    (numero_analisis asignado, ver asignar_numero_analisis_si_corresponde),
    con los datos de recepción de la Solicitud de Muestreo que la originó
    -- LEFT JOIN porque una muestra numerada podría no tener solicitud
    asociada (creada directo por "Nueva Muestra"), caso borde en el que la
    fila igual se muestra, con esas columnas vacías en vez de excluirla."""
    condiciones = ["m.numero_analisis IS NOT NULL"]
    params: list = []
    if fecha_desde:
        condiciones.append("s.fecha_ingreso >= ?")
        params.append(str(fecha_desde))
    if fecha_hasta:
        condiciones.append("s.fecha_ingreso <= ?")
        params.append(str(fecha_hasta))
    where = "WHERE " + " AND ".join(condiciones)

    cursor.execute(
        f"""
        SELECT m.id_muestra, m.numero_analisis, m.erp_CODART, m.erp_DESART, m.estado, m.fecha_muestreo,
               s.id_solicitud, s.fecha_ingreso, s.erp_nro_ir, s.fecha_vencimiento,
               s.proveedor_nombre, s.fecha_factura_proveedor, s.numero_factura_proveedor,
               s.lote_proveedor, s.cantidad_ingresada, s.unidad_cantidad, s.nro_bultos, s.observaciones,
               ur.nombre AS recibio_nombre, ur.apellido AS recibio_apellido,
               uro.nombre AS rotulo_nombre, uro.apellido AS rotulo_apellido,
               um.nombre AS muestreador_nombre, um.apellido AS muestreador_apellido
        FROM lims_muestras m
        LEFT JOIN lims_solicitudes_muestreo s ON s.id_muestra = m.id_muestra
        LEFT JOIN lims_usuarios ur ON ur.id_usuario = s.id_usuario_recibio
        LEFT JOIN lims_usuarios uro ON uro.id_usuario = s.id_usuario_rotulo
        LEFT JOIN lims_usuarios um ON um.id_usuario = s.id_muestreador
        {where}
        ORDER BY m.numero_analisis
        """,
        *params,
    )
    filas = cursor.fetchall()

    return [
        LibroIngresosLinea(
            numero_analisis=r.numero_analisis,
            fecha_ingreso=r.fecha_ingreso,
            nro_ir=r.erp_nro_ir,
            # Sentinel del ERP (1899-12-30) -- se muestra vacío, no la fecha
            # literal (ver normalizar_fecha_sentinel en erp_ir.py).
            fecha_vencimiento=_fecha_vencimiento_o_vacio(r.fecha_vencimiento),
            erp_codart=r.erp_CODART.strip() if r.erp_CODART else None,
            erp_desart=r.erp_DESART.strip() if r.erp_DESART else None,
            proveedor_nombre=r.proveedor_nombre,
            fecha_factura_proveedor=r.fecha_factura_proveedor,
            numero_factura_proveedor=r.numero_factura_proveedor,
            lote_proveedor=r.lote_proveedor.strip() if r.lote_proveedor and r.lote_proveedor.strip() else "S/L",
            cantidad_texto=(
                f"{formatear_cantidad(r.cantidad_ingresada)} {r.unidad_cantidad or ''}".strip()
                if r.cantidad_ingresada is not None else None
            ),
            bultos_detalle=_formatear_bultos_detalle(cursor, r.id_solicitud, r.nro_bultos),
            usuario_recibio=f"{r.recibio_nombre} {r.recibio_apellido}" if r.recibio_nombre else None,
            usuario_rotulo=f"{r.rotulo_nombre} {r.rotulo_apellido}" if r.rotulo_nombre else None,
            observaciones=r.observaciones,
            estado_muestra=r.estado,
            usuario_muestreador=f"{r.muestreador_nombre} {r.muestreador_apellido}" if r.muestreador_nombre else None,
            fecha_muestreo=r.fecha_muestreo,
        )
        for r in filas
    ]


@router.get("/libro-ingresos", response_model=list[LibroIngresosLinea])
def libro_ingresos(
    fecha_desde: Optional[date] = Query(None, description="Filtra por fecha_ingreso (solicitud) >= esta fecha"),
    fecha_hasta: Optional[date] = Query(None, description="Filtra por fecha_ingreso (solicitud) <= esta fecha"),
    user: dict = Depends(require_rol(*_ROLES_GESTION)),
    conn: pyodbc.Connection = Depends(limss_db),
):
    """Libro de Ingresos: una fila por muestra de Materia Prima/Material de
    Empaque (numero_analisis asignado), filtrable por rango de fecha de
    ingreso."""
    cursor = conn.cursor()
    return _obtener_libro_ingresos(cursor, fecha_desde, fecha_hasta)


# (campo del schema, título de columna) -- mismo orden pedido, usado para el
# CSV de exportación.
_ENCABEZADOS_CSV = [
    ("numero_analisis", "N de analisis"),
    ("fecha_ingreso", "Fecha de ingreso"),
    ("nro_ir", "N de IR"),
    ("fecha_vencimiento", "Fecha de vencimiento"),
    ("erp_codart", "Codigo de articulo"),
    ("erp_desart", "Descripcion del articulo"),
    ("proveedor_nombre", "Proveedor"),
    ("fecha_factura_proveedor", "Fecha de factura"),
    ("numero_factura_proveedor", "N de factura"),
    ("lote_proveedor", "Lote del proveedor"),
    ("cantidad_texto", "Peso o cantidad total"),
    ("bultos_detalle", "Bultos"),
    ("usuario_recibio", "Recibio"),
    ("usuario_rotulo", "Rotulo"),
    ("observaciones", "Observaciones"),
    ("estado_muestra", "Estado"),
    ("usuario_muestreador", "Muestreador"),
    ("fecha_muestreo", "Fecha de muestreo"),
]


@router.get("/libro-ingresos/exportar")
def libro_ingresos_exportar(
    fecha_desde: Optional[date] = Query(None),
    fecha_hasta: Optional[date] = Query(None),
    user: dict = Depends(require_rol(*_ROLES_GESTION)),
    conn: pyodbc.Connection = Depends(limss_db),
):
    """CSV (se abre directo en Excel) con las mismas columnas y el mismo
    filtro que GET /libro-ingresos -- el proyecto no tiene ninguna
    dependencia de generación de .xlsx real en ningún lado (ni acá ni en
    los otros reportes, ver ReporteImportesFacturadosPage.jsx/
    ReporteTestigosPage.jsx, que solo ofrecen PDF vía window.print() del
    lado del frontend); CSV es el formato más simple que Excel abre
    nativamente sin sumar una dependencia nueva. El PDF de este reporte
    sigue el mismo mecanismo (window.print()), del lado del frontend."""
    cursor = conn.cursor()
    lineas = _obtener_libro_ingresos(cursor, fecha_desde, fecha_hasta)

    buffer = io.StringIO()
    buffer.write("﻿")  # BOM -- para que Excel detecte UTF-8 y no rompa los acentos
    writer = csv.writer(buffer)
    writer.writerow([titulo for _, titulo in _ENCABEZADOS_CSV])
    for linea in lineas:
        writer.writerow([
            getattr(linea, campo) if getattr(linea, campo) is not None else ""
            for campo, _ in _ENCABEZADOS_CSV
        ])

    return Response(
        content=buffer.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="libro_ingresos.csv"'},
    )
