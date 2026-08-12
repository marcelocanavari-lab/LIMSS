"""
Módulo I: Muestras y Envíos (REQ-ENV-001 a 005).

Digitaliza el flujo desde la toma de muestra hasta el despacho a un laboratorio
externo. El orden de declaración de rutas importa: FastAPI/Starlette matchea la
primera ruta cuyo patrón calza sintácticamente, y "/{id_muestra}" (un solo
segmento, tipo genérico a nivel de ruteo) calzaría con "/laboratorios" si se
declarara antes -- por eso los literales van primero.
"""
from datetime import date, datetime
from typing import Optional

import pyodbc
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response

from app.core.security import get_current_user, require_rol
from app.db.connections import erp_db, limss_db
from app.schemas.muestras import (
    ContactoLaboratorioCreate,
    ContactoLaboratorioResponse,
    ContactoLaboratorioUpdate,
    EnsayoSolicitado,
    EnvioCreate,
    EnvioResponse,
    EtiquetaResponse,
    FacturaResumenEnvio,
    LaboratorioCreate,
    LaboratorioResponse,
    LaboratorioUpdate,
    LineaIR,
    MaterialEncontrado,
    MuestraCreate,
    MuestraResponse,
    MuestraUpdate,
    ProtocoloEnvio,
    RemitoResponse,
    TestigoEnviado,
    TestigoRemito,
)
from app.api.routes.facturas import ensayos_de_envio
from app.api.routes.solicitudes_muestreo import generar_pdf_etiquetas_de_solicitud, obtener_solicitud_o_404
from app.schemas.facturas import EnvioSinFacturar
from app.schemas.recorrido import RecorridoResponse
from app.services import audit, storage
from app.services.erp_ir import buscar_lineas_ir, formatear_nro_ir, normalizar_fecha_sentinel
from app.services.erp_lotes import buscar_lote
from app.services.erp_materiales import obtener_codsar_por_tipo
from app.services.pdf_legajo import AdjuntoLegajo, generar_pdf_legajo
from app.services.recorrido import construir_recorrido

router = APIRouter(prefix="/api/muestras", tags=["Muestras y Envíos"])


# ── Helpers internos ─────────────────────────────────────────────

def _a_fecha(valor) -> Optional[date]:
    """El driver ODBC no devuelve un tipo consistente para columnas DATE en
    este entorno (a veces date/datetime, a veces str); se normaliza siempre
    a date antes de operar."""
    if valor is None:
        return None
    if isinstance(valor, datetime):
        return valor.date()
    if isinstance(valor, date):
        return valor
    return date.fromisoformat(str(valor))


def _fila_a_laboratorio(row) -> LaboratorioResponse:
    return LaboratorioResponse(
        id_laboratorio=row.id_laboratorio,
        nombre=row.nombre,
        direccion=row.direccion,
        contacto=row.contacto,
        email=row.email,
        telefono=row.telefono,
        activo=bool(row.activo),
    )


def _fila_a_muestra(row) -> MuestraResponse:
    return MuestraResponse(
        id_muestra=row.id_muestra,
        codigo_muestra=row.codigo_muestra,
        tipo_referencia=row.tipo_referencia,
        tipo_material=row.tipo_material,
        nro_referencia=row.nro_referencia,
        erp_IdM21=row.erp_IdM21,
        erp_CODART=row.erp_CODART,
        erp_DESART=row.erp_DESART,
        erp_cantidad_lote=float(row.erp_cantidad_lote) if row.erp_cantidad_lote is not None else None,
        erp_proveedor=row.erp_proveedor,
        cantidad_enviada=float(row.cantidad_enviada) if row.cantidad_enviada is not None else None,
        unidad_enviada=row.unidad_enviada,
        id_especificacion=row.id_especificacion,
        estado=row.estado,
        id_usuario_muestreo=row.id_usuario_muestreo,
        usuario_muestreo_nombre=row.usuario_muestreo_nombre,
        fecha_muestreo=row.fecha_muestreo,
        observaciones=row.observaciones,
        datos_muestreo_pendientes=bool(row.datos_muestreo_pendientes),
    )


def _fila_a_etiqueta(fila, muestra) -> EtiquetaResponse:
    return EtiquetaResponse(
        id_etiqueta=fila.id_etiqueta,
        id_muestra=fila.id_muestra,
        codigo_muestra=muestra.codigo_muestra,
        erp_CODART=muestra.erp_CODART,
        erp_DESART=muestra.erp_DESART,
        tipo_referencia=muestra.tipo_referencia,
        nro_referencia=muestra.nro_referencia,
        fecha_muestreo=muestra.fecha_muestreo,
        usuario_muestreo_nombre=muestra.usuario_muestreo_nombre,
        es_reimpresion=bool(fila.reimpresion),
        id_usuario_impresion=fila.id_usuario,
        fecha_hora=fila.fecha_impresion,
    )


_SELECT_MUESTRA = """
    SELECT m.*, u.nombre + ' ' + u.apellido AS usuario_muestreo_nombre
    FROM lims_muestras m
    INNER JOIN lims_usuarios u ON u.id_usuario = m.id_usuario_muestreo
"""


# ── Laboratorios (prerrequisito técnico de los envíos) ────────────

@router.post("/laboratorios", response_model=LaboratorioResponse, status_code=201)
def crear_laboratorio(
    body: LaboratorioCreate,
    user: dict = Depends(require_rol("analista_qc", "qa", "admin")),
    conn: pyodbc.Connection = Depends(limss_db),
):
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO lims_laboratorios (nombre, direccion, contacto, email, telefono)
        VALUES (?, ?, ?, ?, ?)
        """,
        body.nombre, body.direccion, body.contacto, body.email, body.telefono,
    )
    cursor.execute("SELECT @@IDENTITY AS id")
    id_laboratorio = int(cursor.fetchone().id)

    audit.registrar(
        conn, entidad="laboratorio", accion="crear",
        id_usuario=user["id_usuario"], id_entidad=id_laboratorio,
        valor_nuevo={"nombre": body.nombre},
    )

    cursor.execute("SELECT * FROM lims_laboratorios WHERE id_laboratorio = ?", id_laboratorio)
    return _fila_a_laboratorio(cursor.fetchone())


@router.get("/laboratorios", response_model=list[LaboratorioResponse])
def listar_laboratorios(
    activo: Optional[bool] = Query(None),
    user: dict = Depends(get_current_user),
    conn: pyodbc.Connection = Depends(limss_db),
):
    cursor = conn.cursor()
    if activo is None:
        cursor.execute("SELECT * FROM lims_laboratorios ORDER BY nombre")
    else:
        cursor.execute("SELECT * FROM lims_laboratorios WHERE activo = ? ORDER BY nombre", 1 if activo else 0)
    return [_fila_a_laboratorio(r) for r in cursor.fetchall()]


@router.put("/laboratorios/{id_laboratorio}", response_model=LaboratorioResponse)
def editar_laboratorio(
    id_laboratorio: int,
    body: LaboratorioUpdate,
    user: dict = Depends(require_rol("analista_qc", "qa", "admin")),
    conn: pyodbc.Connection = Depends(limss_db),
):
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM lims_laboratorios WHERE id_laboratorio = ?", id_laboratorio)
    row = cursor.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Laboratorio no encontrado")

    campos_anteriores = {
        "nombre": row.nombre, "direccion": row.direccion, "contacto": row.contacto,
        "email": row.email, "telefono": row.telefono, "activo": bool(row.activo),
    }
    campos_nuevos = {
        "nombre": body.nombre, "direccion": body.direccion, "contacto": body.contacto,
        "email": body.email, "telefono": body.telefono, "activo": body.activo,
    }

    cursor.execute(
        """
        UPDATE lims_laboratorios
        SET nombre = ?, direccion = ?, contacto = ?, email = ?, telefono = ?, activo = ?
        WHERE id_laboratorio = ?
        """,
        body.nombre, body.direccion, body.contacto, body.email, body.telefono,
        1 if body.activo else 0, id_laboratorio,
    )

    valor_anterior = {k: v for k, v in campos_anteriores.items() if v != campos_nuevos[k]}
    valor_nuevo = {k: v for k, v in campos_nuevos.items() if v != campos_anteriores[k]}
    audit.registrar(
        conn, entidad="laboratorio", accion="modificar",
        id_usuario=user["id_usuario"], id_entidad=id_laboratorio,
        valor_anterior=valor_anterior or None, valor_nuevo=valor_nuevo or None,
    )

    cursor.execute("SELECT * FROM lims_laboratorios WHERE id_laboratorio = ?", id_laboratorio)
    return _fila_a_laboratorio(cursor.fetchone())


@router.put("/laboratorios/{id_laboratorio}/estado", response_model=LaboratorioResponse)
def cambiar_estado_laboratorio(
    id_laboratorio: int,
    activo: bool,
    user: dict = Depends(require_rol("analista_qc", "qa", "admin")),
    conn: pyodbc.Connection = Depends(limss_db),
):
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM lims_laboratorios WHERE id_laboratorio = ?", id_laboratorio)
    row = cursor.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Laboratorio no encontrado")

    cursor.execute(
        "UPDATE lims_laboratorios SET activo = ? WHERE id_laboratorio = ?",
        1 if activo else 0, id_laboratorio,
    )

    audit.registrar(
        conn, entidad="laboratorio", accion="activar" if activo else "desactivar",
        id_usuario=user["id_usuario"], id_entidad=id_laboratorio,
        valor_anterior={"activo": bool(row.activo)}, valor_nuevo={"activo": activo},
    )

    cursor.execute("SELECT * FROM lims_laboratorios WHERE id_laboratorio = ?", id_laboratorio)
    return _fila_a_laboratorio(cursor.fetchone())


# ── Contactos por laboratorio ─────────────────────────────────────
#
# Rutas literales de 3 segmentos ("/laboratorios/{id}/contactos..."): no
# colisionan con "/{id_muestra}" (un solo segmento) sin importar el orden de
# declaración, pero se agrupan acá junto al resto de rutas de laboratorios
# por prolijidad.

def _fila_a_contacto(row) -> ContactoLaboratorioResponse:
    return ContactoLaboratorioResponse(
        id_contacto=row.id_contacto, id_laboratorio=row.id_laboratorio, nombre=row.nombre,
        cargo=row.cargo, email=row.email, telefono=row.telefono, activo=bool(row.activo),
    )


@router.get("/laboratorios/{id_laboratorio}/contactos", response_model=list[ContactoLaboratorioResponse])
def listar_contactos_laboratorio(
    id_laboratorio: int,
    user: dict = Depends(get_current_user),
    conn: pyodbc.Connection = Depends(limss_db),
):
    cursor = conn.cursor()
    cursor.execute("SELECT 1 FROM lims_laboratorios WHERE id_laboratorio = ?", id_laboratorio)
    if not cursor.fetchone():
        raise HTTPException(status_code=404, detail="Laboratorio no encontrado")
    cursor.execute(
        "SELECT * FROM lims_laboratorio_contactos WHERE id_laboratorio = ? AND activo = 1 ORDER BY nombre",
        id_laboratorio,
    )
    return [_fila_a_contacto(r) for r in cursor.fetchall()]


@router.post("/laboratorios/{id_laboratorio}/contactos", response_model=ContactoLaboratorioResponse, status_code=201)
def crear_contacto_laboratorio(
    id_laboratorio: int,
    body: ContactoLaboratorioCreate,
    user: dict = Depends(require_rol("analista_qc", "qa", "admin")),
    conn: pyodbc.Connection = Depends(limss_db),
):
    cursor = conn.cursor()
    cursor.execute("SELECT 1 FROM lims_laboratorios WHERE id_laboratorio = ?", id_laboratorio)
    if not cursor.fetchone():
        raise HTTPException(status_code=404, detail="Laboratorio no encontrado")

    cursor.execute(
        """
        INSERT INTO lims_laboratorio_contactos (id_laboratorio, nombre, cargo, email, telefono, activo)
        VALUES (?, ?, ?, ?, ?, 1)
        """,
        id_laboratorio, body.nombre, body.cargo, body.email, body.telefono,
    )
    cursor.execute("SELECT @@IDENTITY AS id")
    id_contacto = int(cursor.fetchone().id)

    audit.registrar(
        conn, entidad="laboratorio_contacto", accion="crear",
        id_usuario=user["id_usuario"], id_entidad=id_contacto,
        valor_nuevo={"id_laboratorio": id_laboratorio, "nombre": body.nombre},
    )

    cursor.execute("SELECT * FROM lims_laboratorio_contactos WHERE id_contacto = ?", id_contacto)
    return _fila_a_contacto(cursor.fetchone())


@router.put("/laboratorios/{id_laboratorio}/contactos/{id_contacto}", response_model=ContactoLaboratorioResponse)
def editar_contacto_laboratorio(
    id_laboratorio: int,
    id_contacto: int,
    body: ContactoLaboratorioUpdate,
    user: dict = Depends(require_rol("analista_qc", "qa", "admin")),
    conn: pyodbc.Connection = Depends(limss_db),
):
    cursor = conn.cursor()
    cursor.execute(
        "SELECT * FROM lims_laboratorio_contactos WHERE id_contacto = ? AND id_laboratorio = ?",
        id_contacto, id_laboratorio,
    )
    row = cursor.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Contacto no encontrado")

    cursor.execute(
        """
        UPDATE lims_laboratorio_contactos
        SET nombre = ?, cargo = ?, email = ?, telefono = ?, activo = ?
        WHERE id_contacto = ?
        """,
        body.nombre, body.cargo, body.email, body.telefono, 1 if body.activo else 0, id_contacto,
    )

    audit.registrar(
        conn, entidad="laboratorio_contacto", accion="modificar",
        id_usuario=user["id_usuario"], id_entidad=id_contacto,
        valor_anterior={"nombre": row.nombre, "cargo": row.cargo, "activo": bool(row.activo)},
        valor_nuevo={"nombre": body.nombre, "cargo": body.cargo, "activo": body.activo},
    )

    cursor.execute("SELECT * FROM lims_laboratorio_contactos WHERE id_contacto = ?", id_contacto)
    return _fila_a_contacto(cursor.fetchone())


@router.delete("/laboratorios/{id_laboratorio}/contactos/{id_contacto}", status_code=204)
def eliminar_contacto_laboratorio(
    id_laboratorio: int,
    id_contacto: int,
    user: dict = Depends(require_rol("qa", "admin")),
    conn: pyodbc.Connection = Depends(limss_db),
):
    """Si el contacto ya fue usado (envíos o remitos de testigos), no se
    puede borrar sin dejar referencias huérfanas -- se desactiva en su
    lugar, igual que el patrón ya usado para testigos/especificaciones."""
    cursor = conn.cursor()
    cursor.execute(
        "SELECT * FROM lims_laboratorio_contactos WHERE id_contacto = ? AND id_laboratorio = ?",
        id_contacto, id_laboratorio,
    )
    row = cursor.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Contacto no encontrado")

    cursor.execute("SELECT COUNT(*) AS n FROM lims_envios WHERE id_contacto = ?", id_contacto)
    tiene_envios = cursor.fetchone().n > 0
    cursor.execute("SELECT COUNT(*) AS n FROM lims_remito_testigos_cab WHERE id_contacto = ?", id_contacto)
    tiene_remitos_testigos = cursor.fetchone().n > 0

    if tiene_envios or tiene_remitos_testigos:
        cursor.execute("UPDATE lims_laboratorio_contactos SET activo = 0 WHERE id_contacto = ?", id_contacto)
        accion = "desactivar"
    else:
        cursor.execute("DELETE FROM lims_laboratorio_contactos WHERE id_contacto = ?", id_contacto)
        accion = "eliminar"

    audit.registrar(
        conn, entidad="laboratorio_contacto", accion=accion,
        id_usuario=user["id_usuario"], id_entidad=id_contacto,
        valor_anterior={"nombre": row.nombre},
    )


@router.get("/laboratorios/{id_laboratorio}/envios-sin-facturar", response_model=list[EnvioSinFacturar])
def envios_sin_facturar(
    id_laboratorio: int,
    user: dict = Depends(require_rol("analista_qc", "qa", "admin")),
    conn: pyodbc.Connection = Depends(limss_db),
):
    """Envíos de este laboratorio que todavía no están vinculados a ninguna
    factura (lims_factura_envios) -- para poblar el selector al crear/editar
    una factura en el módulo de Facturación."""
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT e.id_envio, rem.nro_remito_interno AS nro_remito, e.fecha_despacho, e.id_laboratorio,
               m.codigo_muestra, m.erp_CODART, m.erp_DESART, m.erp_nro_ir, sm.lote_proveedor,
               lab.nombre AS laboratorio_nombre,
               (SELECT COUNT(*) FROM lims_envio_ensayos ee WHERE ee.id_envio = e.id_envio) AS cant_ensayos
        FROM lims_envios e
        INNER JOIN lims_muestras m ON m.id_muestra = e.id_muestra
        INNER JOIN lims_laboratorios lab ON lab.id_laboratorio = e.id_laboratorio
        LEFT JOIN lims_solicitudes_muestreo sm ON sm.id_muestra = m.id_muestra
        OUTER APPLY (
            SELECT TOP 1 r.nro_remito_interno
            FROM lims_remitos r
            WHERE r.id_envio = e.id_envio
            ORDER BY r.id_remito DESC
        ) rem
        WHERE e.id_laboratorio = ?
          AND NOT EXISTS (SELECT 1 FROM lims_factura_envios fe WHERE fe.id_envio = e.id_envio)
        ORDER BY e.fecha_despacho DESC
        """,
        id_laboratorio,
    )
    filas = cursor.fetchall()
    return [
        EnvioSinFacturar(
            id_envio=r.id_envio, nro_remito=r.nro_remito, codigo_muestra=r.codigo_muestra,
            fecha_despacho=r.fecha_despacho, id_laboratorio=r.id_laboratorio, laboratorio_nombre=r.laboratorio_nombre,
            erp_CODART=r.erp_CODART, erp_DESART=r.erp_DESART, erp_nro_ir=r.erp_nro_ir,
            lote_proveedor=r.lote_proveedor,
            cantidad_ensayos=r.cant_ensayos,
            ensayos=ensayos_de_envio(cursor, r.id_envio),
        )
        for r in filas
    ]


# ── Búsqueda de IR en el ERP (REQ-ENV-002) ────────────────────────

@router.get("/erp/ir/{nro_ir}", response_model=list[LineaIR])
def buscar_ir(
    nro_ir: str,
    user: dict = Depends(require_rol("muestreador", "analista_qc", "qa", "admin")),
    erp: pyodbc.Connection = Depends(erp_db),
):
    rows = buscar_lineas_ir(erp, nro_ir)
    if not rows:
        raise HTTPException(status_code=404, detail=f"No se encontró el IR '{nro_ir}' en el ERP")
    return [
        LineaIR(
            N01Id=r.N01Id, NUMCOMO=formatear_nro_ir(r.NUMCOMO, r.FECCOR), IdM21=r.IdM21,
            CODART=r.CODART, DESART=r.DESART, CANTID=float(r.CANTID),
            unidad=r.unidad, proveedor=r.proveedor, proveedor_codigo=r.proveedor_codigo,
            fecha_ingreso=normalizar_fecha_sentinel(r.FECCOM),
            fecha_vencimiento=normalizar_fecha_sentinel(r.VENCOM),
            cantidad_ingresada=float(r.cantidad_total) if r.cantidad_total is not None else None,
            advertencia=(
                f"Este IR corresponde a un artículo de tipo {r.DESSAR.strip()} (no es Materia Prima). "
                "Verificá que el número de IR sea correcto."
                if r.CODSAR is not None and r.CODSAR != "0001" else None
            ),
        )
        for r in rows
    ]


@router.get("/buscar-material", response_model=list[MaterialEncontrado])
def buscar_material(
    tipo: str = Query(..., pattern=r"^(materia_prima|granel|semi_elaborado|producto_terminado)$"),
    referencia: str = Query(..., min_length=1),
    user: dict = Depends(require_rol("muestreador", "analista_qc", "qa", "admin")),
    erp: pyodbc.Connection = Depends(erp_db),
    conn: pyodbc.Connection = Depends(limss_db),
):
    """Búsqueda unificada por tipo: Materia Prima se busca por IR en el ERP
    (GIN01CPB); el resto (Granel/Semi-Elaborado/Producto Terminado) se busca
    por número de lote, también en el ERP pero como atributo del artículo
    (GIM25ALT/GIT52DSC -- ver erp_lotes.py), no por un documento de recepción."""
    if tipo == "materia_prima":
        rows = buscar_lineas_ir(erp, referencia)
        if not rows:
            raise HTTPException(status_code=404, detail=f"No se encontró el IR '{referencia}' en el ERP")
        return [
            MaterialEncontrado(
                referencia=formatear_nro_ir(r.NUMCOMO, r.FECCOR), IdM21=r.IdM21, CODART=r.CODART, DESART=r.DESART,
                cantidad=float(r.CANTID), unidad=r.unidad, proveedor=r.proveedor, proveedor_codigo=r.proveedor_codigo,
                fecha_ingreso=normalizar_fecha_sentinel(r.FECCOM),
                fecha_vencimiento=normalizar_fecha_sentinel(r.VENCOM),
                cantidad_ingresada=float(r.cantidad_total) if r.cantidad_total is not None else None,
                advertencia=(
                    f"Este IR corresponde a un artículo de tipo {r.DESSAR.strip()} (no es Materia Prima). "
                    "Verificá que el número de IR sea correcto."
                    if r.CODSAR is not None and r.CODSAR != "0001" else None
                ),
            )
            for r in rows
        ]

    rows = buscar_lote(erp, obtener_codsar_por_tipo(conn)[tipo], referencia)
    if not rows:
        raise HTTPException(status_code=404, detail=f"No se encontró el lote '{referencia}' en el ERP para este tipo de material")
    return [
        MaterialEncontrado(
            referencia=referencia.strip(), IdM21=r.IdM21, CODART=r.CODART, DESART=r.DESART, unidad=r.unidad,
        )
        for r in rows
    ]


# ── Muestras (REQ-ENV-001) ────────────────────────────────────────

@router.post("/", response_model=MuestraResponse, status_code=201)
def crear_muestra(
    body: MuestraCreate,
    user: dict = Depends(require_rol("muestreador", "analista_qc", "qa", "admin")),
    conn: pyodbc.Connection = Depends(limss_db),
):
    cursor = conn.cursor()

    anio = date.today().year
    cursor.execute(
        "SELECT MAX(codigo_muestra) AS ultimo FROM lims_muestras WHERE codigo_muestra LIKE ?",
        f"SAMP-{anio}-%",
    )
    ultimo = cursor.fetchone().ultimo
    correlativo = int(ultimo.split("-")[-1]) + 1 if ultimo else 1
    codigo_muestra = f"SAMP-{anio}-{correlativo:04d}"

    cursor.execute(
        "SELECT id_especificacion FROM lims_especificaciones WHERE erp_IdM21 = ? AND vigente = 1",
        body.erp_IdM21,
    )
    espec = cursor.fetchone()
    id_especificacion = espec.id_especificacion if espec else None

    cantidad_enviada = body.cantidad_enviada
    unidad_enviada = body.unidad_enviada
    if cantidad_enviada is None and id_especificacion is not None:
        # lims_especificaciones.cantidad_muestra quedó deprecado a favor de
        # lims_especificacion_muestras (una fila por tipo de muestra, soporta
        # varias por especificación) y en la práctica siempre viene NULL --
        # mismo fix que _obtener_cantidades en solicitudes_muestreo.py.
        cursor.execute("SELECT OBJECT_ID('lims_especificacion_muestras') AS oid")
        if cursor.fetchone().oid is not None:
            cursor.execute(
                "SELECT TOP 1 cantidad, unidad FROM lims_especificacion_muestras "
                "WHERE id_especificacion = ? AND tipo_muestra = 'analisis' ORDER BY orden",
                id_especificacion,
            )
            fila_cantidad = cursor.fetchone()
            if fila_cantidad:
                cantidad_enviada = float(fila_cantidad.cantidad)
                unidad_enviada = fila_cantidad.unidad

    cursor.execute(
        """
        INSERT INTO lims_muestras
            (codigo_muestra, tipo_referencia, tipo_material, nro_referencia, erp_IdM21, erp_CODART, erp_DESART,
             erp_cantidad_lote, erp_proveedor, cantidad_enviada, unidad_enviada, id_especificacion, estado,
             id_usuario_muestreo, observaciones)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pendiente_envio', ?, ?)
        """,
        codigo_muestra, body.tipo_referencia, body.tipo_material, body.nro_referencia, body.erp_IdM21, body.erp_CODART, body.erp_DESART,
        body.erp_cantidad_lote, body.erp_proveedor, cantidad_enviada, unidad_enviada, id_especificacion,
        user["id_usuario"], body.observaciones,
    )
    cursor.execute("SELECT @@IDENTITY AS id")
    id_muestra = int(cursor.fetchone().id)

    audit.registrar(
        conn, entidad="muestra", accion="crear",
        id_usuario=user["id_usuario"], id_entidad=id_muestra,
        valor_nuevo={"codigo_muestra": codigo_muestra, "tipo_referencia": body.tipo_referencia, "nro_referencia": body.nro_referencia},
    )

    cursor.execute(_SELECT_MUESTRA + " WHERE m.id_muestra = ?", id_muestra)
    return _fila_a_muestra(cursor.fetchone())


@router.get("/", response_model=list[MuestraResponse])
def listar_muestras(
    estado: Optional[str] = Query(None),
    buscar: str = Query(""),
    mio: Optional[bool] = Query(None, description="Si es true, solo las muestras creadas por el usuario logueado"),
    tipo_material: Optional[str] = Query(None, description="Filtra por lims_muestras.tipo_material"),
    fecha_desde: Optional[date] = Query(None),
    fecha_hasta: Optional[date] = Query(None),
    id_laboratorio: Optional[int] = Query(None, description="Solo muestras que tengan algún envío a este laboratorio"),
    user: dict = Depends(get_current_user),
    conn: pyodbc.Connection = Depends(limss_db),
):
    """Listado general de muestras (ConsultaMuestrasPage) con filtros
    opcionales; con mio=true queda acotado a "mis muestras" (MuestrasPage,
    Etapa 1 del flujo)."""
    cursor = conn.cursor()
    like = f"%{buscar}%"
    condiciones = ["(m.codigo_muestra LIKE ? OR m.nro_referencia LIKE ? OR m.erp_CODART LIKE ? OR m.erp_DESART LIKE ?)"]
    params: list = [like, like, like, like]

    if estado:
        condiciones.append("m.estado = ?")
        params.append(estado)
    if mio:
        condiciones.append("m.id_usuario_muestreo = ?")
        params.append(user["id_usuario"])
    if tipo_material:
        condiciones.append("m.tipo_material = ?")
        params.append(tipo_material)
    if fecha_desde:
        condiciones.append("m.fecha_muestreo >= ?")
        params.append(fecha_desde)
    if fecha_hasta:
        condiciones.append("m.fecha_muestreo < DATEADD(day, 1, ?)")
        params.append(fecha_hasta)
    if id_laboratorio:
        condiciones.append(
            "EXISTS (SELECT 1 FROM lims_envios e WHERE e.id_muestra = m.id_muestra AND e.id_laboratorio = ?)"
        )
        params.append(id_laboratorio)

    cursor.execute(
        _SELECT_MUESTRA + " WHERE " + " AND ".join(condiciones) + " ORDER BY m.fecha_muestreo DESC",
        *params,
    )
    return [_fila_a_muestra(r) for r in cursor.fetchall()]


@router.get("/pendientes-envio", response_model=list[MuestraResponse])
def listar_pendientes_envio(
    buscar: str = Query(""),
    user: dict = Depends(get_current_user),
    conn: pyodbc.Connection = Depends(limss_db),
):
    """Bandeja de Envío de Muestras (Etapas 2/3): muestras que todavía
    admiten crear un nuevo envío o cargar resultados de los que ya tiene."""
    cursor = conn.cursor()
    like = f"%{buscar}%"
    cursor.execute(
        _SELECT_MUESTRA + """
        WHERE m.estado IN ('pendiente_envio', 'en_análisis')
          AND (m.codigo_muestra LIKE ? OR m.nro_referencia LIKE ? OR m.erp_CODART LIKE ? OR m.erp_DESART LIKE ?)
        ORDER BY m.fecha_muestreo DESC
        """,
        like, like, like, like,
    )
    return [_fila_a_muestra(r) for r in cursor.fetchall()]


@router.get("/{id_muestra}", response_model=MuestraResponse)
def detalle_muestra(
    id_muestra: int,
    user: dict = Depends(get_current_user),
    conn: pyodbc.Connection = Depends(limss_db),
):
    cursor = conn.cursor()
    cursor.execute(_SELECT_MUESTRA + " WHERE m.id_muestra = ?", id_muestra)
    row = cursor.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Muestra no encontrada")
    return _fila_a_muestra(row)


@router.patch("/{id_muestra}", response_model=MuestraResponse)
def editar_muestra(
    id_muestra: int,
    body: MuestraUpdate,
    user: dict = Depends(require_rol("analista_qc", "qa", "admin")),
    conn: pyodbc.Connection = Depends(limss_db),
):
    """Edición post-ingreso, limitada a tipo_material y observaciones --
    todo lo demás (datos del ERP, estado del flujo) es de solo lectura acá,
    se toca únicamente a través de sus propios endpoints/flujos."""
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM lims_muestras WHERE id_muestra = ?", id_muestra)
    row = cursor.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Muestra no encontrada")

    sets = []
    params = []
    valor_anterior = {}
    valor_nuevo = {}

    if body.tipo_material is not None and body.tipo_material != row.tipo_material:
        sets.append("tipo_material = ?")
        params.append(body.tipo_material)
        valor_anterior["tipo_material"] = row.tipo_material
        valor_nuevo["tipo_material"] = body.tipo_material

    if body.observaciones is not None and body.observaciones != (row.observaciones or ""):
        sets.append("observaciones = ?")
        params.append(body.observaciones)
        valor_anterior["observaciones"] = row.observaciones
        valor_nuevo["observaciones"] = body.observaciones

    if sets:
        params.append(id_muestra)
        cursor.execute(f"UPDATE lims_muestras SET {', '.join(sets)} WHERE id_muestra = ?", *params)

        audit.registrar(
            conn, entidad="muestra", accion="edicion_muestra",
            id_usuario=user["id_usuario"], id_entidad=id_muestra,
            valor_anterior=valor_anterior, valor_nuevo=valor_nuevo,
        )

    cursor.execute(_SELECT_MUESTRA + " WHERE m.id_muestra = ?", id_muestra)
    return _fila_a_muestra(cursor.fetchone())


# ── Envío a laboratorio externo (REQ-ENV-004/005) ─────────────────

@router.get("/{id_muestra}/ensayos-para-envio", response_model=list[EnsayoSolicitado])
def ensayos_para_envio(
    id_muestra: int,
    id_laboratorio: int = Query(...),
    user: dict = Depends(get_current_user),
    conn: pyodbc.Connection = Depends(limss_db),
):
    """Ensayos de la especificación de la muestra que tienen asignado
    justamente el laboratorio elegido para este envío -- el formulario de
    envío recalcula esta lista cada vez que cambia el laboratorio."""
    cursor = conn.cursor()
    cursor.execute("SELECT id_especificacion FROM lims_muestras WHERE id_muestra = ?", id_muestra)
    muestra = cursor.fetchone()
    if not muestra:
        raise HTTPException(status_code=404, detail="Muestra no encontrada")
    if not muestra.id_especificacion:
        return []

    cursor.execute(
        """
        SELECT se.id_espec_ensayo, m.nombre_ensayo, se.requerido_por_defecto, se.id_laboratorio, lab.nombre AS laboratorio_nombre
        FROM lims_especificacion_ensayos se
        INNER JOIN lims_ensayos_maestro m ON m.id_ensayo_maestro = se.id_ensayo_maestro
        INNER JOIN lims_laboratorios lab ON lab.id_laboratorio = se.id_laboratorio
        WHERE se.id_especificacion = ? AND se.id_laboratorio = ?
        ORDER BY se.orden
        """,
        muestra.id_especificacion, id_laboratorio,
    )
    return [
        EnsayoSolicitado(
            id_espec_ensayo=e.id_espec_ensayo, nombre_ensayo=e.nombre_ensayo,
            requerido_por_defecto=bool(e.requerido_por_defecto),
            id_laboratorio=e.id_laboratorio, laboratorio_nombre=e.laboratorio_nombre,
        )
        for e in cursor.fetchall()
    ]


@router.post("/{id_muestra}/envios", response_model=EnvioResponse, status_code=201)
def confirmar_envio(
    id_muestra: int,
    body: EnvioCreate,
    user: dict = Depends(require_rol("analista_qc", "qa", "admin")),
    conn: pyodbc.Connection = Depends(limss_db),
):
    """Una muestra puede tener múltiples envíos (a distintos laboratorios,
    con distintos ensayos cada uno) mientras esté 'pendiente_envio' o ya
    'en_análisis' -- solo se bloquea una vez dictaminada."""
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM lims_muestras WHERE id_muestra = ?", id_muestra)
    muestra = cursor.fetchone()
    if not muestra:
        raise HTTPException(status_code=404, detail="Muestra no encontrada")
    if muestra.estado not in ("pendiente_envio", "en_análisis"):
        raise HTTPException(
            status_code=409,
            detail=f"La muestra está en estado '{muestra.estado}', no se puede confirmar un envío",
        )

    cursor.execute(
        "SELECT 1 FROM lims_laboratorios WHERE id_laboratorio = ? AND activo = 1",
        body.id_laboratorio,
    )
    if not cursor.fetchone():
        raise HTTPException(status_code=404, detail="Laboratorio no encontrado o inactivo")

    if body.id_contacto is not None:
        cursor.execute(
            "SELECT 1 FROM lims_laboratorio_contactos WHERE id_contacto = ? AND id_laboratorio = ? AND activo = 1",
            body.id_contacto, body.id_laboratorio,
        )
        if not cursor.fetchone():
            raise HTTPException(
                status_code=400,
                detail="El contacto indicado no pertenece a este laboratorio o está inactivo",
            )

    ids_espec_ensayo = body.id_espec_ensayo or []
    if ids_espec_ensayo:
        placeholders = ",".join("?" * len(ids_espec_ensayo))
        cursor.execute(
            f"""
            SELECT se.id_espec_ensayo, m.nombre_ensayo, se.requerido_por_defecto, se.obligatorio, se.id_laboratorio, lab.nombre AS laboratorio_nombre
            FROM lims_especificacion_ensayos se
            INNER JOIN lims_ensayos_maestro m ON m.id_ensayo_maestro = se.id_ensayo_maestro
            LEFT JOIN lims_laboratorios lab ON lab.id_laboratorio = se.id_laboratorio
            WHERE se.id_especificacion = ? AND se.id_espec_ensayo IN ({placeholders})
            """,
            muestra.id_especificacion, *ids_espec_ensayo,
        )
        ensayos_elegidos = cursor.fetchall()
        if len(ensayos_elegidos) != len(set(ids_espec_ensayo)):
            raise HTTPException(
                status_code=400,
                detail="Alguno de los ensayos indicados no pertenece a la especificación de la muestra",
            )
    else:
        # Sin lista explícita: se solicitan los ensayos de la especificación
        # asignados justamente al laboratorio elegido para ESTE envío -- antes
        # de soportar múltiples envíos esto no importaba tanto (un solo lab
        # por muestra), pero con varios envíos a labs distintos hay que
        # filtrar, si no un envío terminaría llevándose ensayos de otro lab.
        cursor.execute(
            """
            SELECT se.id_espec_ensayo, m.nombre_ensayo, se.requerido_por_defecto, se.obligatorio, se.id_laboratorio, lab.nombre AS laboratorio_nombre
            FROM lims_especificacion_ensayos se
            INNER JOIN lims_ensayos_maestro m ON m.id_ensayo_maestro = se.id_ensayo_maestro
            LEFT JOIN lims_laboratorios lab ON lab.id_laboratorio = se.id_laboratorio
            WHERE se.id_especificacion = ? AND se.id_laboratorio = ?
            """,
            muestra.id_especificacion, body.id_laboratorio,
        )
        ensayos_elegidos = cursor.fetchall()

    ids_testigo_permitidos = set()
    if muestra.id_especificacion:
        cursor.execute(
            "SELECT id_testigo FROM lims_especificacion_testigos WHERE id_especificacion = ?",
            muestra.id_especificacion,
        )
        ids_testigo_permitidos = {r.id_testigo for r in cursor.fetchall()}

    hoy = date.today()
    alerta_testigo_por_vencer = False
    testigos_confirmados = []  # testigo_row

    for item in body.testigos:
        if item.id_testigo not in ids_testigo_permitidos:
            raise HTTPException(
                status_code=400,
                detail=f"El testigo {item.id_testigo} no está asociado a la especificación de la muestra",
            )

        cursor.execute("SELECT * FROM lims_testigos WHERE id_testigo = ?", item.id_testigo)
        testigo = cursor.fetchone()
        if not testigo:
            raise HTTPException(status_code=404, detail="Testigo no encontrado")
        if not testigo.activo:
            raise HTTPException(status_code=400, detail=f"El testigo '{testigo.codigo}' está inactivo")

        # Sin fecha de vencimiento cargada, no se puede considerar vencido ni
        # próximo a vencer.
        fecha_vencimiento = _a_fecha(testigo.fecha_vencimiento)
        if fecha_vencimiento is not None:
            if fecha_vencimiento < hoy:
                # REQ-ENV-004-A: bloqueo absoluto, testigo vencido no puede enviarse.
                raise HTTPException(
                    status_code=400,
                    detail=f"El testigo '{testigo.codigo}' está VENCIDO ({fecha_vencimiento}). No se puede confirmar el envío.",
                )
            if (fecha_vencimiento - hoy).days < 30:
                alerta_testigo_por_vencer = True

        testigos_confirmados.append(testigo)

    cursor.execute(
        """
        INSERT INTO lims_envios
            (id_muestra, id_laboratorio, id_contacto,
             temperatura_transporte, nro_remito, transportista,
             analisis_solicitados, protocolo_utilizar, id_usuario_envio)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        id_muestra, body.id_laboratorio, body.id_contacto,
        body.temperatura_transporte, body.nro_remito, body.transportista,
        body.analisis_solicitados, body.protocolo_utilizar, user["id_usuario"],
    )
    cursor.execute("SELECT @@IDENTITY AS id")
    id_envio = int(cursor.fetchone().id)

    for e in ensayos_elegidos:
        cursor.execute(
            "INSERT INTO lims_envio_ensayos (id_envio, id_espec_ensayo) VALUES (?, ?)",
            id_envio, e.id_espec_ensayo,
        )

    testigos_enviados = []
    hubo_alerta_reorden = False
    for testigo in testigos_confirmados:
        cursor.execute(
            "INSERT INTO lims_envio_testigos (id_envio, id_testigo, cantidad) VALUES (?, ?, 0)",
            id_envio, testigo.id_testigo,
        )

        # Descuento automático de stock según el consumo configurado para este
        # testigo en ESTE laboratorio (lims_testigo_laboratorios) -- si no está
        # configurado, el consumo es manual y no se toca el stock acá.
        cursor.execute(
            "SELECT consumo_estimado FROM lims_testigo_laboratorios WHERE id_testigo = ? AND id_laboratorio = ?",
            testigo.id_testigo, body.id_laboratorio,
        )
        consumo_row = cursor.fetchone()
        consumo_estimado = (
            float(consumo_row.consumo_estimado)
            if consumo_row and consumo_row.consumo_estimado is not None
            else None
        )

        if consumo_estimado is not None:
            stock_resultante = float(testigo.stock_actual) - consumo_estimado
            cursor.execute(
                "UPDATE lims_testigos SET stock_actual = ? WHERE id_testigo = ?",
                stock_resultante, testigo.id_testigo,
            )
            cursor.execute(
                """
                INSERT INTO lims_testigo_movimientos
                    (id_testigo, id_envio, tipo, cantidad, stock_resultante, id_usuario, observaciones)
                VALUES (?, ?, 'egreso', ?, ?, ?, ?)
                """,
                testigo.id_testigo, id_envio, -consumo_estimado, stock_resultante, user["id_usuario"],
                f"Consumo por envío de muestra - remito {body.nro_remito or f'(envío #{id_envio})'}",
            )
            # Stock negativo no bloquea el envío -- solo indica que hay que
            # reponer el testigo; se avisa vía alerta_reorden en la respuesta.
            if stock_resultante <= float(testigo.stock_minimo):
                hubo_alerta_reorden = True
            audit.registrar(
                conn, entidad="testigo", accion="consumo_envio",
                id_usuario=user["id_usuario"], id_entidad=testigo.id_testigo,
                valor_anterior={"stock_actual": float(testigo.stock_actual)},
                valor_nuevo={"stock_actual": stock_resultante, "id_envio": id_envio, "consumo_estimado": consumo_estimado},
            )
        else:
            audit.registrar(
                conn, entidad="testigo", accion="consumo_envio_omitido",
                id_usuario=user["id_usuario"], id_entidad=testigo.id_testigo,
                valor_nuevo={
                    "id_envio": id_envio, "id_laboratorio": body.id_laboratorio,
                    "motivo": "Sin consumo_estimado configurado para este testigo/laboratorio -- no se descontó stock automáticamente",
                },
            )

        testigos_enviados.append(TestigoEnviado(
            id_testigo=testigo.id_testigo, codigo=testigo.codigo, nombre=testigo.nombre, nro_ir=testigo.nro_ir,
        ))

    if muestra.estado == "pendiente_envio":
        cursor.execute("UPDATE lims_muestras SET estado = 'en_análisis' WHERE id_muestra = ?", id_muestra)

    audit.registrar(
        conn, entidad="envio", accion="confirmar",
        id_usuario=user["id_usuario"], id_entidad=id_envio,
        valor_nuevo={"id_muestra": id_muestra, "id_laboratorio": body.id_laboratorio},
    )

    cursor.execute("SELECT nombre FROM lims_laboratorios WHERE id_laboratorio = ?", body.id_laboratorio)
    laboratorio_nombre = cursor.fetchone().nombre

    contacto_nombre = None
    if body.id_contacto is not None:
        cursor.execute("SELECT nombre FROM lims_laboratorio_contactos WHERE id_contacto = ?", body.id_contacto)
        c = cursor.fetchone()
        contacto_nombre = c.nombre if c else None

    cursor.execute("SELECT * FROM lims_envios WHERE id_envio = ?", id_envio)
    row = cursor.fetchone()
    return EnvioResponse(
        id_envio=row.id_envio,
        id_muestra=row.id_muestra,
        id_laboratorio=row.id_laboratorio,
        laboratorio_nombre=laboratorio_nombre,
        id_contacto=row.id_contacto,
        contacto_nombre=contacto_nombre,
        testigos=testigos_enviados,
        fecha_despacho=row.fecha_despacho,
        temperatura_transporte=row.temperatura_transporte,
        nro_remito=row.nro_remito,
        transportista=row.transportista,
        analisis_solicitados=row.analisis_solicitados,
        protocolo_utilizar=row.protocolo_utilizar,
        id_usuario_envio=row.id_usuario_envio,
        alerta_testigo_por_vencer=alerta_testigo_por_vencer,
        alerta_reorden=hubo_alerta_reorden,
        ensayos_solicitados=[
            EnsayoSolicitado(
                id_espec_ensayo=e.id_espec_ensayo, nombre_ensayo=e.nombre_ensayo,
                requerido_por_defecto=bool(e.requerido_por_defecto),
                obligatorio=bool(e.obligatorio),
                id_laboratorio=e.id_laboratorio, laboratorio_nombre=e.laboratorio_nombre,
            )
            for e in ensayos_elegidos
        ],
        completo=False,
    )


def _obtener_ensayos_solicitados(cursor, id_envio: int) -> list[EnsayoSolicitado]:
    """Ensayos pedidos para un envío, con su resultado ya cargado si lo hay
    (join por id_envio -- cada envío tiene sus propios resultados, ver
    migrations_flujo_envios_multiples.sql)."""
    cursor.execute(
        """
        SELECT se.id_espec_ensayo, m.nombre_ensayo, se.requerido_por_defecto, se.id_laboratorio, lab.nombre AS laboratorio_nombre,
               se.obligatorio, r.valor_numerico, r.valor_cualitativo, r.dentro_especificacion
        FROM lims_envio_ensayos ee
        INNER JOIN lims_especificacion_ensayos se ON se.id_espec_ensayo = ee.id_espec_ensayo
        INNER JOIN lims_ensayos_maestro m ON m.id_ensayo_maestro = se.id_ensayo_maestro
        LEFT JOIN lims_laboratorios lab ON lab.id_laboratorio = se.id_laboratorio
        LEFT JOIN lims_resultados r ON r.id_espec_ensayo = ee.id_espec_ensayo AND r.id_envio = ee.id_envio
        WHERE ee.id_envio = ?
        ORDER BY se.orden
        """,
        id_envio,
    )
    return [
        EnsayoSolicitado(
            id_espec_ensayo=e.id_espec_ensayo, nombre_ensayo=e.nombre_ensayo,
            requerido_por_defecto=bool(e.requerido_por_defecto),
            id_laboratorio=e.id_laboratorio, laboratorio_nombre=e.laboratorio_nombre,
            obligatorio=bool(e.obligatorio),
            valor_numerico=float(e.valor_numerico) if e.valor_numerico is not None else None,
            valor_cualitativo=e.valor_cualitativo,
            dentro_especificacion=bool(e.dentro_especificacion) if e.dentro_especificacion is not None else None,
        )
        for e in cursor.fetchall()
    ]


def _envio_completo(ensayos: list[EnsayoSolicitado]) -> bool:
    """True si todos los ensayos obligatorios del envío ya tienen resultado
    cargado -- mismo criterio que la validación de guardado en envios.py."""
    return all(
        (e.valor_numerico is not None or bool((e.valor_cualitativo or "").strip()))
        for e in ensayos
        if e.obligatorio
    )


def _obtener_protocolo_envio(cursor, id_envio: int) -> Optional[ProtocoloEnvio]:
    cursor.execute(
        "SELECT * FROM lims_protocolos WHERE id_envio = ? ORDER BY fecha_carga DESC",
        id_envio,
    )
    p = cursor.fetchone()
    if not p:
        return None
    return ProtocoloEnvio(
        id_protocolo=p.id_protocolo,
        nro_protocolo_ext=p.nro_protocolo_ext,
        fecha_emision=p.fecha_emision,
        pdf_nombre_original=p.pdf_nombre_original,
        fecha_carga=p.fecha_carga,
    )


def _obtener_factura_de_envio(cursor, id_envio: int) -> Optional[FacturaResumenEnvio]:
    cursor.execute(
        """
        SELECT f.id_factura, f.nro_factura, f.estado_pago
        FROM lims_factura_envios fe
        JOIN lims_facturas f ON f.id_factura = fe.id_factura
        WHERE fe.id_envio = ?
        """,
        id_envio,
    )
    row = cursor.fetchone()
    if not row:
        return None
    return FacturaResumenEnvio(id_factura=row.id_factura, nro_factura=row.nro_factura, estado_pago=row.estado_pago)


def _obtener_testigos_enviados(cursor, id_envio: int) -> list[TestigoEnviado]:
    cursor.execute(
        """
        SELECT t.id_testigo, t.codigo, t.nombre, et.cantidad
        FROM lims_envio_testigos et
        INNER JOIN lims_testigos t ON t.id_testigo = et.id_testigo
        WHERE et.id_envio = ?
        ORDER BY t.codigo
        """,
        id_envio,
    )
    return [
        TestigoEnviado(
            id_testigo=t.id_testigo, codigo=t.codigo, nombre=t.nombre, cantidad=float(t.cantidad),
        )
        for t in cursor.fetchall()
    ]


@router.get("/{id_muestra}/envios", response_model=list[EnvioResponse])
def listar_envios(
    id_muestra: int,
    user: dict = Depends(get_current_user),
    conn: pyodbc.Connection = Depends(limss_db),
):
    """Todos los envíos de la muestra (posiblemente a distintos laboratorios),
    cada uno con sus propios ensayos/resultados/protocolo -- reemplaza el
    viejo GET .../envio (singular, tomaba solo el más reciente)."""
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT e.*, lab.nombre AS laboratorio_nombre, c.nombre AS contacto_nombre
        FROM lims_envios e
        INNER JOIN lims_laboratorios lab ON lab.id_laboratorio = e.id_laboratorio
        LEFT JOIN lims_laboratorio_contactos c ON c.id_contacto = e.id_contacto
        WHERE e.id_muestra = ?
        ORDER BY e.id_envio
        """,
        id_muestra,
    )
    filas = cursor.fetchall()

    envios = []
    for row in filas:
        ensayos = _obtener_ensayos_solicitados(cursor, row.id_envio)
        envios.append(EnvioResponse(
            id_envio=row.id_envio,
            id_muestra=row.id_muestra,
            id_laboratorio=row.id_laboratorio,
            laboratorio_nombre=row.laboratorio_nombre,
            id_contacto=row.id_contacto,
            contacto_nombre=row.contacto_nombre,
            testigos=_obtener_testigos_enviados(cursor, row.id_envio),
            fecha_despacho=row.fecha_despacho,
            temperatura_transporte=row.temperatura_transporte,
            nro_remito=row.nro_remito,
            transportista=row.transportista,
            analisis_solicitados=row.analisis_solicitados,
            protocolo_utilizar=row.protocolo_utilizar,
            id_usuario_envio=row.id_usuario_envio,
            ensayos_solicitados=ensayos,
            protocolo=_obtener_protocolo_envio(cursor, row.id_envio),
            completo=_envio_completo(ensayos),
            factura=_obtener_factura_de_envio(cursor, row.id_envio),
        ))
    return envios


@router.get("/{id_muestra}/envios/{id_envio}/remito", response_model=RemitoResponse)
def obtener_remito(
    id_muestra: int,
    id_envio: int,
    user: dict = Depends(get_current_user),
    conn: pyodbc.Connection = Depends(limss_db),
):
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT e.id_envio,
               m.codigo_muestra, m.tipo_referencia, m.nro_referencia, m.erp_CODART, m.erp_DESART, m.fecha_muestreo,
               m.cantidad_enviada, m.unidad_enviada,
               u.nombre + ' ' + u.apellido AS usuario_muestreo_nombre,
               e.fecha_despacho, e.temperatura_transporte, e.nro_remito, e.transportista,
               e.analisis_solicitados, e.protocolo_utilizar, e.id_contacto,
               lab.nombre AS laboratorio_nombre, lab.direccion AS laboratorio_direccion,
               lab.contacto AS laboratorio_contacto,
               c.nombre AS contacto_nombre, c.cargo AS contacto_cargo
        FROM lims_muestras m
        INNER JOIN lims_envios e ON e.id_muestra = m.id_muestra
        INNER JOIN lims_usuarios u ON u.id_usuario = m.id_usuario_muestreo
        INNER JOIN lims_laboratorios lab ON lab.id_laboratorio = e.id_laboratorio
        LEFT JOIN lims_laboratorio_contactos c ON c.id_contacto = e.id_contacto
        WHERE m.id_muestra = ? AND e.id_envio = ?
        """,
        id_muestra, id_envio,
    )
    row = cursor.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Envío no encontrado para esta muestra")

    cursor.execute(
        """
        SELECT t.id_testigo, t.codigo, t.nombre, t.nro_ir, t.nro_lote, t.fecha_vencimiento
        FROM lims_envio_testigos et
        INNER JOIN lims_testigos t ON t.id_testigo = et.id_testigo
        WHERE et.id_envio = ?
        ORDER BY t.codigo
        """,
        row.id_envio,
    )
    testigos = [
        TestigoRemito(
            id_testigo=t.id_testigo, codigo=t.codigo, nombre=t.nombre, nro_ir=t.nro_ir,
            nro_lote=t.nro_lote, fecha_vencimiento=t.fecha_vencimiento,
        )
        for t in cursor.fetchall()
    ]

    cursor.execute(
        "SELECT TOP 1 * FROM lims_remitos WHERE id_envio = ? ORDER BY id_remito DESC",
        row.id_envio,
    )
    remito_pdf = cursor.fetchone()

    return RemitoResponse(
        id_remito=remito_pdf.id_remito if remito_pdf else None,
        id_envio=row.id_envio,
        codigo_muestra=row.codigo_muestra,
        tipo_referencia=row.tipo_referencia,
        nro_referencia=row.nro_referencia,
        erp_CODART=row.erp_CODART,
        erp_DESART=row.erp_DESART,
        fecha_muestreo=row.fecha_muestreo,
        usuario_muestreo_nombre=row.usuario_muestreo_nombre,
        cantidad_enviada=float(row.cantidad_enviada) if row.cantidad_enviada is not None else None,
        unidad_enviada=row.unidad_enviada,
        laboratorio_nombre=row.laboratorio_nombre,
        laboratorio_direccion=row.laboratorio_direccion,
        laboratorio_contacto=row.laboratorio_contacto,
        id_contacto=row.id_contacto,
        contacto_nombre=row.contacto_nombre,
        contacto_cargo=row.contacto_cargo,
        fecha_despacho=row.fecha_despacho,
        temperatura_transporte=row.temperatura_transporte,
        nro_remito=row.nro_remito,
        transportista=row.transportista,
        analisis_solicitados=row.analisis_solicitados,
        protocolo_utilizar=row.protocolo_utilizar,
        ensayos_solicitados=_obtener_ensayos_solicitados(cursor, row.id_envio),
        testigos=testigos,
        tiene_copia_firmada=bool(remito_pdf.pdf_copia_firmada) if remito_pdf else False,
        fecha_recepcion=_a_fecha(remito_pdf.fecha_recepcion) if remito_pdf else None,
        recibido_por=remito_pdf.recibido_por if remito_pdf else None,
    )


@router.get("/{id_muestra}/recorrido", response_model=RecorridoResponse)
def obtener_recorrido(
    id_muestra: int,
    user: dict = Depends(get_current_user),
    conn: pyodbc.Connection = Depends(limss_db),
):
    """Reporte de recorrido completo de la muestra (ConsultaMuestrasPage,
    punto 7): datos de la muestra + todos sus envíos con sus resultados +
    dictamen final si ya se emitió."""
    cursor = conn.cursor()
    recorrido = construir_recorrido(cursor, id_muestra)
    if not recorrido:
        raise HTTPException(status_code=404, detail="Muestra no encontrada")
    return recorrido


@router.get("/{id_muestra}/legajo-pdf")
def descargar_legajo(
    id_muestra: int,
    protocolo_proveedor: bool = Query(True),
    protocolo_laboratorio: bool = Query(True),
    documentacion_proveedor: bool = Query(True),
    user: dict = Depends(get_current_user),
    conn: pyodbc.Connection = Depends(limss_db),
):
    """PDF único: Recorrido de Muestra (siempre incluido) + los documentos
    adjuntos reales que el usuario haya tildado en el selector previo de
    Consulta de Muestras. Un adjunto tildado cuyo archivo no existe se
    omite en silencio (ver _paginas_de_adjunto en pdf_legajo.py) -- no
    bloquea la generación del resto."""
    cursor = conn.cursor()
    recorrido = construir_recorrido(cursor, id_muestra)
    if not recorrido:
        raise HTTPException(status_code=404, detail="Muestra no encontrada")

    adjuntos: list[AdjuntoLegajo] = []

    if protocolo_proveedor or documentacion_proveedor:
        cursor.execute(
            """
            SELECT TOP 1 protocolo_proveedor_path, protocolo_proveedor_nombre_original,
                   documentacion_proveedor_path, documentacion_proveedor_nombre_original
            FROM lims_solicitudes_muestreo WHERE id_muestra = ? ORDER BY id_solicitud DESC
            """,
            id_muestra,
        )
        sol = cursor.fetchone()
        if sol:
            if protocolo_proveedor and sol.protocolo_proveedor_path:
                adjuntos.append(AdjuntoLegajo(
                    titulo="Protocolo del proveedor",
                    ruta_absoluta=storage.ruta_absoluta(sol.protocolo_proveedor_path),
                    nombre_original=sol.protocolo_proveedor_nombre_original,
                ))
            if documentacion_proveedor and sol.documentacion_proveedor_path:
                adjuntos.append(AdjuntoLegajo(
                    titulo="Factura/Remito del proveedor",
                    ruta_absoluta=storage.ruta_absoluta(sol.documentacion_proveedor_path),
                    nombre_original=sol.documentacion_proveedor_nombre_original,
                ))

    if protocolo_laboratorio:
        for en in recorrido.envios:
            cursor.execute(
                "SELECT TOP 1 pdf_path, pdf_nombre_original FROM lims_protocolos WHERE id_envio = ? ORDER BY fecha_carga DESC",
                en.id_envio,
            )
            prot = cursor.fetchone()
            if prot and prot.pdf_path:
                adjuntos.append(AdjuntoLegajo(
                    titulo=f"Protocolo del laboratorio — {en.laboratorio_nombre} (Envío N° {en.nro_remito or en.id_envio})",
                    ruta_absoluta=storage.ruta_absoluta(prot.pdf_path),
                    nombre_original=prot.pdf_nombre_original,
                ))

    pdf_bytes = generar_pdf_legajo(recorrido, adjuntos)
    return Response(
        content=pdf_bytes, media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{recorrido.codigo_muestra}_legajo.pdf"'},
    )


# ── Etiquetas (REQ-ENV-003) ────────────────────────────────────────

@router.post("/{id_muestra}/etiqueta", response_model=EtiquetaResponse, status_code=201)
def generar_etiqueta(
    id_muestra: int,
    user: dict = Depends(require_rol("muestreador", "analista_qc", "qa", "admin")),
    conn: pyodbc.Connection = Depends(limss_db),
):
    """Genera (e imprime) una etiqueta para la muestra. Cada llamada registra
    una fila nueva en lims_etiquetas -- la primera es la impresión original,
    las siguientes quedan marcadas como reimpresión."""
    cursor = conn.cursor()
    cursor.execute(_SELECT_MUESTRA + " WHERE m.id_muestra = ?", id_muestra)
    muestra = cursor.fetchone()
    if not muestra:
        raise HTTPException(status_code=404, detail="Muestra no encontrada")

    cursor.execute("SELECT COUNT(*) AS n FROM lims_etiquetas WHERE id_muestra = ?", id_muestra)
    es_reimpresion = cursor.fetchone().n > 0

    cursor.execute(
        "INSERT INTO lims_etiquetas (id_muestra, id_usuario, reimpresion) VALUES (?, ?, ?)",
        id_muestra, user["id_usuario"], es_reimpresion,
    )
    cursor.execute("SELECT @@IDENTITY AS id")
    id_etiqueta = int(cursor.fetchone().id)

    audit.registrar(
        conn, entidad="etiqueta", accion="reimprimir" if es_reimpresion else "imprimir",
        id_usuario=user["id_usuario"], id_entidad=id_etiqueta,
        valor_nuevo={"id_muestra": id_muestra, "reimpresion": es_reimpresion},
    )

    cursor.execute("SELECT * FROM lims_etiquetas WHERE id_etiqueta = ?", id_etiqueta)
    return _fila_a_etiqueta(cursor.fetchone(), muestra)


@router.get("/{id_muestra}/etiqueta", response_model=EtiquetaResponse)
def obtener_ultima_etiqueta(
    id_muestra: int,
    user: dict = Depends(get_current_user),
    conn: pyodbc.Connection = Depends(limss_db),
):
    cursor = conn.cursor()
    cursor.execute(_SELECT_MUESTRA + " WHERE m.id_muestra = ?", id_muestra)
    muestra = cursor.fetchone()
    if not muestra:
        raise HTTPException(status_code=404, detail="Muestra no encontrada")

    cursor.execute(
        "SELECT TOP 1 * FROM lims_etiquetas WHERE id_muestra = ? ORDER BY id_etiqueta DESC",
        id_muestra,
    )
    fila = cursor.fetchone()
    if not fila:
        raise HTTPException(status_code=404, detail="Todavía no se generó ninguna etiqueta para esta muestra")
    return _fila_a_etiqueta(fila, muestra)


@router.get("/{id_muestra}/etiquetas-pdf")
def descargar_etiquetas_de_muestra(
    id_muestra: int,
    user: dict = Depends(get_current_user),
    conn: pyodbc.Connection = Depends(limss_db),
):
    """PDF de etiquetas para reimprimir desde Consulta de Muestras -- usa la
    misma función de armado que "Descargar etiquetas" en Solicitudes
    (ver generar_pdf_etiquetas_de_solicitud en solicitudes_muestreo.py) para
    que ambos caminos generen exactamente el mismo PDF, en vez de un
    template paralelo. El registro de auditoría de la reimpresión
    (lims_etiquetas.reimpresion) lo sigue llevando POST /{id_muestra}/etiqueta,
    sin cambios."""
    cursor = conn.cursor()
    cursor.execute("SELECT id_solicitud FROM lims_solicitudes_muestreo WHERE id_muestra = ?", id_muestra)
    fila = cursor.fetchone()
    if not fila:
        raise HTTPException(status_code=404, detail="Esta muestra no tiene una solicitud de muestreo asociada")

    row = obtener_solicitud_o_404(cursor, fila.id_solicitud)
    pdf_bytes = generar_pdf_etiquetas_de_solicitud(cursor, row)

    return Response(
        content=pdf_bytes, media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{row.nro_solicitud}_etiquetas.pdf"'},
    )
