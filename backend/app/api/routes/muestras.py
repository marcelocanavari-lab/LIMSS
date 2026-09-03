"""
Módulo I: Muestras y Envíos (REQ-ENV-001 a 005).

Digitaliza el flujo desde la toma de muestra hasta el despacho a un laboratorio
externo. El orden de declaración de rutas importa: FastAPI/Starlette matchea la
primera ruta cuyo patrón calza sintácticamente, y "/{id_muestra}" (un solo
segmento, tipo genérico a nivel de ruteo) calzaría con "/laboratorios" si se
declarara antes -- por eso los literales van primero.
"""
import logging
from datetime import date, datetime
from types import SimpleNamespace
from typing import Optional

import pyodbc
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response

from app.core.security import get_current_user, require_rol
from app.db.connections import erp_db, limss_db
from app.schemas.muestras import (
    CantidadEtiquetasResponse,
    ContactoLaboratorioCreate,
    ContactoLaboratorioResponse,
    ContactoLaboratorioUpdate,
    EnsayoSolicitado,
    EnvioCreate,
    EnvioResponse,
    EspecificacionCandidata,
    EtiquetaResponse,
    FacturaResumenEnvio,
    ImpresoraEtiquetaCreate,
    ImpresoraEtiquetaResponse,
    ImpresoraEtiquetaUpdate,
    ImprimirDirectoBody,
    ImprimirDirectoResponse,
    ItemImpresionEtiquetas,
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
    VincularEspecificacionBody,
)
from app.api.routes.facturas import _tiene_tabla_factura_detalle, ensayos_de_envio
from app.api.routes.solicitudes_muestreo import (
    _ROLES_MUESTREADOR_O_SUPERIOR,
    generar_pdf_etiquetas_de_solicitud,
    iniciales_muestreador,
    obtener_muestras_confirmadas,
    obtener_solicitud_o_404,
    obtener_tipos_de_especificacion,
)
from app.services.impresion_sato import (
    armar_pares_etiquetas_muestra,
    generar_sbpl_etiqueta,
    generar_sbpl_etiqueta_complementaria,
    generar_sbpl_etiqueta_estado,
    generar_sbpl_etiqueta_par,
    imprimir_sbpl,
)
from app.services.pdf_solicitud_muestreo import generar_pdf_etiqueta_muestra, generar_pdf_etiquetas_v2
from app.schemas.facturas import EnvioSinFacturar
from app.schemas.recorrido import RecorridoResponse
from app.schemas.solicitudes_muestreo import ChecklistMuestreoItem, ChecklistMuestreoRespuesta
from app.services import audit, storage
from app.services.bultos import expandir_bultos, filtrar_rango_bultos, obtener_grupos_bultos
from app.services.formato import etiqueta_referencia, formatear_cantidad, normalizar_unidad, titulo_etiqueta_por_tipo
from app.services.especificaciones import guardar_checklist_muestreo, obtener_checklist_muestreo, tiene_ensayos_analisis
from app.services.erp_ir import buscar_todos_candidatos_ir, formatear_nro_ir, normalizar_fecha_sentinel
from app.services.erp_lotes import buscar_lote
from app.services.erp_materiales import asignar_numero_analisis_si_corresponde, obtener_codsar_por_tipo, tiene_numero_analisis
from app.services.pdf_legajo import AdjuntoLegajo, generar_pdf_legajo
from app.services.recorrido import construir_recorrido

logger = logging.getLogger("muestras")

router = APIRouter(prefix="/api/muestras", tags=["Muestras y Envíos"])


# ── Helpers internos ─────────────────────────────────────────────

def _g(row, atributo: str):
    """Lee un atributo que puede no existir todavía en el esquema real
    (mismo criterio que _g en solicitudes_muestreo.py) -- getattr con
    default None en vez de romper toda la respuesta por una columna nueva
    que este entorno todavía no migró (ver requiere_coas_proveedor,
    migrations_laboratorio_requiere_coas.sql)."""
    return getattr(row, atributo, None)


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


def _datos_vencimiento_confirmado(cursor, id_muestra: int) -> tuple[Optional[date], bool, bool]:
    """(fecha_vencimiento_real, sin_vencimiento_confirmado, tiene_solicitud)
    de la Solicitud de Muestreo de esta muestra -- consulta aparte del resto
    de obtener_remito, no un JOIN directo en esa query, para tolerar que
    sin_vencimiento_confirmado (ver migrations_solicitud_vencimiento_
    confirmado.sql) todavía no exista en algún entorno sin romper el SELECT
    principal por un nombre de columna inválido (mismo criterio que
    _tiene_sin_vencimiento_confirmado en envios.py).

    tiene_solicitud distingue "no confirmado todavía" de "no aplica ningún
    aviso acá" -- una muestra creada directo con Nueva Muestra (sin
    Solicitud de Muestreo asociada, ver bug real: SAMP-2026-0010/muestra 30,
    con vencimiento resuelto en vivo contra el ERP e igual mostraba el aviso
    de "sin vencimiento") nunca va a tener fila en lims_solicitudes_muestreo,
    así que jamás puede confirmarse por acá -- el frontend no debe pedir esa
    confirmación para un caso que estructuralmente no existe."""
    try:
        cursor.execute("SELECT COL_LENGTH('lims_solicitudes_muestreo', 'sin_vencimiento_confirmado') AS c")
        tiene_columna = cursor.fetchone().c is not None
        campo_sin_vencimiento = "s.sin_vencimiento_confirmado" if tiene_columna else "0"
        cursor.execute(
            f"""
            SELECT s.fecha_vencimiento_real, {campo_sin_vencimiento} AS sin_vencimiento_confirmado
            FROM lims_solicitudes_muestreo s
            WHERE s.id_muestra = ?
            """,
            id_muestra,
        )
        fila = cursor.fetchone()
    except pyodbc.Error:
        return None, False, False
    if not fila:
        return None, False, False
    return _a_fecha(fila.fecha_vencimiento_real), bool(fila.sin_vencimiento_confirmado), True


def _datos_coas(cursor, id_muestra: int, id_laboratorio: int) -> tuple[bool, bool]:
    """(laboratorio_requiere_coas, tiene_protocolo_proveedor) -- para que el
    frontend pueda avisar ANTES de generar el remito si el laboratorio
    exige el COAS del proveedor y todavía no está cargado en la Solicitud
    de Muestreo (mismo mecanismo que _laboratorio_requiere_coas en
    envios.py, que es el que efectivamente adjunta el archivo al generar).
    Tolerante a que requiere_coas_proveedor todavía no exista en este
    entorno (ver migrations_laboratorio_requiere_coas.sql)."""
    cursor.execute("SELECT COL_LENGTH('lims_laboratorios', 'requiere_coas_proveedor') AS c")
    if cursor.fetchone().c is None:
        return False, False
    cursor.execute(
        "SELECT requiere_coas_proveedor FROM lims_laboratorios WHERE id_laboratorio = ?",
        id_laboratorio,
    )
    fila_lab = cursor.fetchone()
    laboratorio_requiere_coas = bool(fila_lab.requiere_coas_proveedor) if fila_lab else False
    if not laboratorio_requiere_coas:
        return False, False

    cursor.execute(
        "SELECT protocolo_proveedor_path FROM lims_solicitudes_muestreo WHERE id_muestra = ?",
        id_muestra,
    )
    fila_sol = cursor.fetchone()
    tiene_protocolo_proveedor = bool(fila_sol.protocolo_proveedor_path) if fila_sol else False
    return laboratorio_requiere_coas, tiene_protocolo_proveedor


def _fila_a_laboratorio(row) -> LaboratorioResponse:
    return LaboratorioResponse(
        id_laboratorio=row.id_laboratorio,
        nombre=row.nombre,
        direccion=row.direccion,
        contacto=row.contacto,
        email=row.email,
        telefono=row.telefono,
        activo=bool(row.activo),
        requiere_coas_proveedor=bool(_g(row, "requiere_coas_proveedor")),
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

    try:
        # Columna agregada en migrations_laboratorio_requiere_coas.sql -- si
        # todavía no se corrió en este entorno, se omite sin bloquear el
        # resto del alta (mismo criterio de tolerancia ya usado en
        # confirmar_orden_trabajo para sin_vencimiento_confirmado).
        cursor.execute(
            "UPDATE lims_laboratorios SET requiere_coas_proveedor = ? WHERE id_laboratorio = ?",
            1 if body.requiere_coas_proveedor else 0, id_laboratorio,
        )
    except pyodbc.Error:
        pass

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
        "requiere_coas_proveedor": bool(_g(row, "requiere_coas_proveedor")),
    }
    campos_nuevos = {
        "nombre": body.nombre, "direccion": body.direccion, "contacto": body.contacto,
        "email": body.email, "telefono": body.telefono, "activo": body.activo,
        "requiere_coas_proveedor": body.requiere_coas_proveedor,
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
    try:
        # Ver misma nota de tolerancia en crear_laboratorio.
        cursor.execute(
            "UPDATE lims_laboratorios SET requiere_coas_proveedor = ? WHERE id_laboratorio = ?",
            1 if body.requiere_coas_proveedor else 0, id_laboratorio,
        )
    except pyodbc.Error:
        pass

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
               m.codigo_muestra, m.erp_CODART, m.erp_DESART, m.tipo_referencia, m.nro_referencia,
               lab.nombre AS laboratorio_nombre,
               (SELECT COUNT(*) FROM lims_envio_ensayos ee WHERE ee.id_envio = e.id_envio) AS cant_ensayos
        FROM lims_envios e
        INNER JOIN lims_muestras m ON m.id_muestra = e.id_muestra
        INNER JOIN lims_laboratorios lab ON lab.id_laboratorio = e.id_laboratorio
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
            erp_CODART=r.erp_CODART, erp_DESART=r.erp_DESART, tipo_referencia=r.tipo_referencia,
            nro_referencia=r.nro_referencia,
            cantidad_ensayos=r.cant_ensayos,
            ensayos=ensayos_de_envio(cursor, r.id_envio),
        )
        for r in filas
    ]


# ── Búsqueda de IR en el ERP (REQ-ENV-002) ────────────────────────

# CODSAR de artículos que legítimamente se buscan por IR en estas pantallas
# -- Materia Prima ('0001') y Material de Empaque, codificado o sin
# codificar ('0005'/'0006'). Cualquier otro CODSAR (Granel, Semi-Elaborado,
# Producto Terminado) sí amerita la advertencia de "verificá el IR", porque
# esos tipos no se reciben por IR en el circuito normal.
_CODSAR_ESPERADOS_POR_IR = {"0001", "0005", "0006"}


def _advertencia_codsar_inesperado(codsar: Optional[str], dessar: Optional[str]) -> Optional[str]:
    if codsar is None or codsar in _CODSAR_ESPERADOS_POR_IR:
        return None
    return (
        f"Este IR corresponde a un artículo de tipo {dessar.strip()} (no es Materia Prima ni Material de Empaque). "
        "Verificá que el número de IR sea correcto."
    )


@router.get("/erp/ir/{nro_ir}", response_model=list[LineaIR])
def buscar_ir(
    nro_ir: str,
    user: dict = Depends(require_rol("muestreador", "analista_qc", "qa", "admin")),
    erp: pyodbc.Connection = Depends(erp_db),
):
    # buscar_todos_candidatos_ir (en vez de buscar_lineas_ir): si hay
    # colisión real de (NUMCOMO, año) -- más de un comprobante para este IR,
    # ver investigación previa -- devuelve los ítems de TODOS los candidatos
    # en vez de que el backend elija uno solo. Sin colisión, el resultado es
    # idéntico a antes (0 o 1 comprobante).
    rows = buscar_todos_candidatos_ir(erp, nro_ir)
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
            advertencia=_advertencia_codsar_inesperado(r.CODSAR, r.DESSAR),
            fecha_comprobante=r.FECCOR.date() if hasattr(r.FECCOR, "date") else r.FECCOR,
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
        # buscar_todos_candidatos_ir: ver comentario en buscar_ir más arriba
        # -- misma lógica, un MaterialEncontrado por cada comprobante
        # candidato cuando hay colisión, cada uno con su propio N01Id.
        rows = buscar_todos_candidatos_ir(erp, referencia)
        if not rows:
            raise HTTPException(status_code=404, detail=f"No se encontró el IR '{referencia}' en el ERP")
        return [
            MaterialEncontrado(
                referencia=formatear_nro_ir(r.NUMCOMO, r.FECCOR), IdM21=r.IdM21, CODART=r.CODART, DESART=r.DESART,
                cantidad=float(r.CANTID), unidad=r.unidad, proveedor=r.proveedor, proveedor_codigo=r.proveedor_codigo,
                fecha_ingreso=normalizar_fecha_sentinel(r.FECCOM),
                fecha_vencimiento=normalizar_fecha_sentinel(r.VENCOM),
                cantidad_ingresada=float(r.cantidad_total) if r.cantidad_total is not None else None,
                CODSAR=r.CODSAR,
                advertencia=_advertencia_codsar_inesperado(r.CODSAR, r.DESSAR),
                N01Id=r.N01Id,
                fecha_comprobante=r.FECCOR.date() if hasattr(r.FECCOR, "date") else r.FECCOR,
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


@router.get("/buscar-etiquetas", response_model=list[ItemImpresionEtiquetas])
def buscar_para_etiquetas(
    buscar: str = Query(..., min_length=1),
    user: dict = Depends(get_current_user),
    conn: pyodbc.Connection = Depends(limss_db),
):
    """Búsqueda unificada para la pantalla "Impresión de Etiquetas" del
    Dashboard: solicitudes (candidatas a CUARENTENA, aunque todavía no
    tengan muestra vinculada -- se imprime al ingreso, antes del muestreo
    físico) + muestras (candidatas a MUESTRA siempre, y a APROBADO si el
    dictamen las aprobó). Ruta literal -- declarada ACÁ, antes de cualquier
    "/{id_muestra}" (empieza más abajo, en "Muestras"), mismo motivo que
    "/impresoras..." un poco más abajo: un solo segmento matchea contra
    "/{id_muestra}" sin importar el nombre."""
    cursor = conn.cursor()
    like = f"%{buscar}%"
    resultados: list[ItemImpresionEtiquetas] = []

    cursor.execute(
        """
        SELECT TOP 20 id_solicitud, nro_solicitud, erp_CODART, erp_DESART, estado, nro_bultos
        FROM lims_solicitudes_muestreo
        WHERE (nro_solicitud LIKE ? OR erp_CODART LIKE ? OR erp_DESART LIKE ? OR erp_nro_ir LIKE ?)
          AND estado <> 'anulada' AND nro_bultos IS NOT NULL
        ORDER BY fecha_solicitud DESC
        """,
        like, like, like, like,
    )
    for r in cursor.fetchall():
        resultados.append(ItemImpresionEtiquetas(
            tipo="solicitud", id=r.id_solicitud, identificador=r.nro_solicitud,
            erp_CODART=(r.erp_CODART or "").strip(), erp_DESART=r.erp_DESART or "",
            estado=r.estado, etiquetas_disponibles=["cuarentena"],
        ))

    cursor.execute(
        _SELECT_MUESTRA + """
        WHERE (m.codigo_muestra LIKE ? OR m.erp_CODART LIKE ? OR m.erp_DESART LIKE ? OR m.nro_referencia LIKE ?)
        ORDER BY m.fecha_muestreo DESC
        """,
        like, like, like, like,
    )
    for m in cursor.fetchall()[:20]:
        etiquetas = ["muestra"]
        if m.estado in ("aprobado", "aprobado_sin_dictamen"):
            # Las etiquetas complementarias de Aprobado (si la especificación
            # tiene cantidad_etiquetas_complementarias > 0) se adjuntan
            # automáticamente al mismo trabajo de impresión de "aprobado" --
            # no son una opción aparte en este listado (ver
            # _imprimir_etiqueta_estado_muestra en este mismo archivo).
            etiquetas.append("aprobado")
        elif m.estado == "rechazado":
            etiquetas.append("rechazado")
        resultados.append(ItemImpresionEtiquetas(
            tipo="muestra", id=m.id_muestra, identificador=m.codigo_muestra,
            erp_CODART=(m.erp_CODART or "").strip(), erp_DESART=m.erp_DESART or "",
            estado=m.estado, etiquetas_disponibles=etiquetas,
        ))

    return resultados


# ── Impresoras de etiquetas (SATO, impresión directa) ──────────────
#
# Rutas literales ("/impresoras...") -- se declaran ACÁ, antes de cualquier
# "/{id_muestra}" (empieza más abajo, en "Muestras"), por el mismo motivo
# documentado arriba para Laboratorios: un solo segmento matchea contra
# "/{id_muestra}" sin importar el nombre.

def _fila_a_impresora(row) -> ImpresoraEtiquetaResponse:
    return ImpresoraEtiquetaResponse(
        id_impresora=row.id_impresora, nombre=row.nombre, modelo=row.modelo,
        tipo_conexion=getattr(row, "tipo_conexion", None) or "compartida",
        ruta_red=row.ruta_red, ip_directa=getattr(row, "ip_directa", None),
        puerto_directo=getattr(row, "puerto_directo", None) or 9100,
        resolucion_dpi=row.resolucion_dpi,
        ancho_mm=row.ancho_mm, alto_mm=row.alto_mm, activa=bool(row.activa),
    )


@router.post("/impresoras", response_model=ImpresoraEtiquetaResponse, status_code=201)
def crear_impresora(
    body: ImpresoraEtiquetaCreate,
    user: dict = Depends(require_rol("analista_qc", "qa", "admin")),
    conn: pyodbc.Connection = Depends(limss_db),
):
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO lims_impresoras_etiquetas
            (nombre, modelo, tipo_conexion, ruta_red, ip_directa, puerto_directo,
             resolucion_dpi, ancho_mm, alto_mm, activa, id_usuario_carga)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?)
        """,
        body.nombre, body.modelo, body.tipo_conexion, body.ruta_red, body.ip_directa, body.puerto_directo,
        body.resolucion_dpi, body.ancho_mm, body.alto_mm, user["id_usuario"],
    )
    cursor.execute("SELECT @@IDENTITY AS id")
    id_impresora = int(cursor.fetchone().id)

    audit.registrar(
        conn, entidad="impresora_etiqueta", accion="crear",
        id_usuario=user["id_usuario"], id_entidad=id_impresora,
        valor_nuevo={
            "nombre": body.nombre, "tipo_conexion": body.tipo_conexion,
            "ruta_red": body.ruta_red, "ip_directa": body.ip_directa, "puerto_directo": body.puerto_directo,
        },
    )

    cursor.execute("SELECT * FROM lims_impresoras_etiquetas WHERE id_impresora = ?", id_impresora)
    return _fila_a_impresora(cursor.fetchone())


@router.get("/impresoras", response_model=list[ImpresoraEtiquetaResponse])
def listar_impresoras(
    activa: Optional[bool] = Query(None),
    user: dict = Depends(get_current_user),
    conn: pyodbc.Connection = Depends(limss_db),
):
    cursor = conn.cursor()
    if activa is None:
        cursor.execute("SELECT * FROM lims_impresoras_etiquetas ORDER BY nombre")
    else:
        cursor.execute("SELECT * FROM lims_impresoras_etiquetas WHERE activa = ? ORDER BY nombre", 1 if activa else 0)
    return [_fila_a_impresora(r) for r in cursor.fetchall()]


@router.put("/impresoras/{id_impresora}", response_model=ImpresoraEtiquetaResponse)
def editar_impresora(
    id_impresora: int,
    body: ImpresoraEtiquetaUpdate,
    user: dict = Depends(require_rol("analista_qc", "qa", "admin")),
    conn: pyodbc.Connection = Depends(limss_db),
):
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM lims_impresoras_etiquetas WHERE id_impresora = ?", id_impresora)
    row = cursor.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Impresora no encontrada")

    campos_anteriores = {
        "nombre": row.nombre, "modelo": row.modelo,
        "tipo_conexion": getattr(row, "tipo_conexion", None) or "compartida",
        "ruta_red": row.ruta_red, "ip_directa": getattr(row, "ip_directa", None),
        "puerto_directo": getattr(row, "puerto_directo", None) or 9100,
        "resolucion_dpi": row.resolucion_dpi, "ancho_mm": row.ancho_mm, "alto_mm": row.alto_mm,
        "activa": bool(row.activa),
    }
    campos_nuevos = {
        "nombre": body.nombre, "modelo": body.modelo, "tipo_conexion": body.tipo_conexion,
        "ruta_red": body.ruta_red, "ip_directa": body.ip_directa, "puerto_directo": body.puerto_directo,
        "resolucion_dpi": body.resolucion_dpi, "ancho_mm": body.ancho_mm, "alto_mm": body.alto_mm,
        "activa": body.activa,
    }

    cursor.execute(
        """
        UPDATE lims_impresoras_etiquetas
        SET nombre = ?, modelo = ?, tipo_conexion = ?, ruta_red = ?, ip_directa = ?, puerto_directo = ?,
            resolucion_dpi = ?, ancho_mm = ?, alto_mm = ?, activa = ?
        WHERE id_impresora = ?
        """,
        body.nombre, body.modelo, body.tipo_conexion, body.ruta_red, body.ip_directa, body.puerto_directo,
        body.resolucion_dpi, body.ancho_mm, body.alto_mm, 1 if body.activa else 0, id_impresora,
    )

    valor_anterior = {k: v for k, v in campos_anteriores.items() if v != campos_nuevos[k]}
    valor_nuevo = {k: v for k, v in campos_nuevos.items() if v != campos_anteriores[k]}
    audit.registrar(
        conn, entidad="impresora_etiqueta", accion="modificar",
        id_usuario=user["id_usuario"], id_entidad=id_impresora,
        valor_anterior=valor_anterior or None, valor_nuevo=valor_nuevo or None,
    )

    cursor.execute("SELECT * FROM lims_impresoras_etiquetas WHERE id_impresora = ?", id_impresora)
    return _fila_a_impresora(cursor.fetchone())


@router.put("/impresoras/{id_impresora}/estado", response_model=ImpresoraEtiquetaResponse)
def cambiar_estado_impresora(
    id_impresora: int,
    activa: bool,
    user: dict = Depends(require_rol("analista_qc", "qa", "admin")),
    conn: pyodbc.Connection = Depends(limss_db),
):
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM lims_impresoras_etiquetas WHERE id_impresora = ?", id_impresora)
    row = cursor.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Impresora no encontrada")

    cursor.execute(
        "UPDATE lims_impresoras_etiquetas SET activa = ? WHERE id_impresora = ?",
        1 if activa else 0, id_impresora,
    )

    audit.registrar(
        conn, entidad="impresora_etiqueta", accion="activar" if activa else "desactivar",
        id_usuario=user["id_usuario"], id_entidad=id_impresora,
        valor_anterior={"activa": bool(row.activa)}, valor_nuevo={"activa": activa},
    )

    cursor.execute("SELECT * FROM lims_impresoras_etiquetas WHERE id_impresora = ?", id_impresora)
    return _fila_a_impresora(cursor.fetchone())


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
    unidad_enviada = normalizar_unidad(body.unidad_enviada)
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

    # Sin ningún ensayo de etapa 'analisis' en la especificación (solo
    # checklist de muestreo), no hay nada que enviar a un laboratorio -- la
    # muestra arranca directo en 'en_análisis' en vez de 'pendiente_envio'
    # (mismo criterio que _crear_muestra_desde_solicitud en
    # solicitudes_muestreo.py).
    estado_inicial = "en_análisis" if not tiene_ensayos_analisis(cursor, id_especificacion) else "pendiente_envio"

    # numero_analisis (Libro de Ingresos): correlativo exclusivo de Materia
    # Prima/Material de Empaque, ver asignar_numero_analisis_si_corresponde
    # -- "Nueva Muestra" (esta pantalla) puede crear cualquier tipo de
    # material (tipo_referencia 'ir' o 'lote'), a diferencia de Solicitudes
    # de Muestreo que siempre es materia prima/empaque.
    if tiene_numero_analisis(cursor):
        numero_analisis = asignar_numero_analisis_si_corresponde(conn, id_especificacion)
        cursor.execute(
            """
            INSERT INTO lims_muestras
                (codigo_muestra, tipo_referencia, tipo_material, nro_referencia, erp_n01id, erp_IdM21, erp_CODART, erp_DESART,
                 erp_cantidad_lote, erp_proveedor, cantidad_enviada, unidad_enviada, id_especificacion, estado,
                 id_usuario_muestreo, observaciones, numero_analisis)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            codigo_muestra, body.tipo_referencia, body.tipo_material, body.nro_referencia, body.erp_n01id, body.erp_IdM21, body.erp_CODART, body.erp_DESART,
            body.erp_cantidad_lote, body.erp_proveedor, cantidad_enviada, unidad_enviada, id_especificacion,
            estado_inicial, user["id_usuario"], body.observaciones, numero_analisis,
        )
    else:
        cursor.execute(
            """
            INSERT INTO lims_muestras
                (codigo_muestra, tipo_referencia, tipo_material, nro_referencia, erp_n01id, erp_IdM21, erp_CODART, erp_DESART,
                 erp_cantidad_lote, erp_proveedor, cantidad_enviada, unidad_enviada, id_especificacion, estado,
                 id_usuario_muestreo, observaciones)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            codigo_muestra, body.tipo_referencia, body.tipo_material, body.nro_referencia, body.erp_n01id, body.erp_IdM21, body.erp_CODART, body.erp_DESART,
            body.erp_cantidad_lote, body.erp_proveedor, cantidad_enviada, unidad_enviada, id_especificacion,
            estado_inicial, user["id_usuario"], body.observaciones,
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


@router.get("/{id_muestra}/especificacion-candidata", response_model=Optional[EspecificacionCandidata])
def especificacion_candidata(
    id_muestra: int,
    user: dict = Depends(get_current_user),
    conn: pyodbc.Connection = Depends(limss_db),
):
    """Para el aviso "Vincular especificación" en la ficha de la muestra
    (caso real: SAMP-2026-0012/S0034 en producción -- crear_muestra resuelve
    id_especificacion en el momento de crear la muestra; si la especificación
    del artículo todavía no existía en Datos Maestros en ese momento, queda
    en NULL para siempre, sin ningún mecanismo para reconectarla después
    aunque la especificación se cargue más tarde).

    Devuelve la especificación vigente de este mismo erp_IdM21 si ya existe
    (para que el frontend la muestre y pida confirmar antes de vincular), o
    None si todavía no hay ninguna -- en ese caso el frontend indica que hay
    que cargarla primero en Datos Maestros."""
    cursor = conn.cursor()
    cursor.execute("SELECT erp_IdM21, id_especificacion FROM lims_muestras WHERE id_muestra = ?", id_muestra)
    muestra = cursor.fetchone()
    if not muestra:
        raise HTTPException(status_code=404, detail="Muestra no encontrada")
    if muestra.id_especificacion is not None:
        raise HTTPException(status_code=400, detail="Esta muestra ya tiene una especificación vinculada")

    cursor.execute(
        "SELECT id_especificacion, RTRIM(erp_CODART) AS erp_CODART, erp_DESART, tipo_material, version "
        "FROM lims_especificaciones WHERE erp_IdM21 = ? AND vigente = 1",
        muestra.erp_IdM21,
    )
    espec = cursor.fetchone()
    if not espec:
        return None
    return EspecificacionCandidata(
        id_especificacion=espec.id_especificacion, erp_CODART=espec.erp_CODART,
        erp_DESART=(espec.erp_DESART or "").strip(), tipo_material=espec.tipo_material, version=espec.version,
    )


@router.post("/{id_muestra}/vincular-especificacion", response_model=MuestraResponse)
def vincular_especificacion(
    id_muestra: int,
    body: VincularEspecificacionBody,
    user: dict = Depends(require_rol("analista_qc", "qa", "admin")),
    conn: pyodbc.Connection = Depends(limss_db),
):
    """Confirma la reconexión propuesta por especificacion_candidata --
    revalida server-side que la especificación indicada realmente corresponda
    a este artículo (mismo erp_IdM21) y esté vigente, en vez de confiar
    ciegamente en lo que mandó el frontend (por si cambió algo entre el GET
    y este POST). Alcance deliberadamente acotado a id_especificacion: no
    recalcula estado ni numero_analisis retroactivamente -- la muestra puede
    ya estar en medio de otro paso del flujo (envío, resultados), así que
    tocar esos campos ahora sería más riesgoso que el problema que se está
    resolviendo."""
    cursor = conn.cursor()
    cursor.execute("SELECT erp_IdM21, id_especificacion FROM lims_muestras WHERE id_muestra = ?", id_muestra)
    muestra = cursor.fetchone()
    if not muestra:
        raise HTTPException(status_code=404, detail="Muestra no encontrada")
    if muestra.id_especificacion is not None:
        raise HTTPException(status_code=409, detail="Esta muestra ya tiene una especificación vinculada")

    cursor.execute(
        "SELECT 1 FROM lims_especificaciones WHERE id_especificacion = ? AND erp_IdM21 = ? AND vigente = 1",
        body.id_especificacion, muestra.erp_IdM21,
    )
    if not cursor.fetchone():
        raise HTTPException(
            status_code=400,
            detail="La especificación indicada no corresponde a este artículo o no está vigente",
        )

    cursor.execute(
        "UPDATE lims_muestras SET id_especificacion = ? WHERE id_muestra = ?",
        body.id_especificacion, id_muestra,
    )
    audit.registrar(
        conn, entidad="muestra", accion="vincular_especificacion",
        id_usuario=user["id_usuario"], id_entidad=id_muestra,
        valor_anterior={"id_especificacion": None},
        valor_nuevo={"id_especificacion": body.id_especificacion},
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
        # m.fecha_muestreo es DATETIME (no DATE): pasar la fecha como string
        # ('YYYY-MM-DD') es riesgoso acá -- bajo DATEFORMAT=dmy (idioma
        # Español del server, ver DBCC USEROPTIONS) SQL Server interpreta ese
        # string invirtiendo mes/día al convertirlo a datetime (silencioso
        # con día <= 12, error con día > 12). Se convierte a un objeto
        # datetime de Python -- el driver lo bindea nativo (SQL_TIMESTAMP),
        # sin pasar por el parseo de string sujeto a DATEFORMAT (mismo
        # criterio que auditoria.py/equipos.py con columnas DATETIME).
        condiciones.append("m.fecha_muestreo >= ?")
        params.append(datetime.combine(fecha_desde, datetime.min.time()))
    if fecha_hasta:
        condiciones.append("m.fecha_muestreo < DATEADD(day, 1, ?)")
        params.append(datetime.combine(fecha_hasta, datetime.min.time()))
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
    admiten crear un nuevo envío o cargar resultados de los que ya tiene.

    Excluye especificaciones sin ningún ensayo de categoría con momento
    'analisis' (solo checklist de categorías con momento 'muestreo') -- no
    hay nada que enviar a ningún laboratorio para esas, quedan directo
    esperando Dictamen (ver especificaciones.tiene_ensayos_analisis y el
    estado inicial que ya les asigna la creación de la muestra). Sin
    especificación resuelta (id_especificacion NULL) se mantiene en la
    bandeja -- mismo criterio conservador de siempre."""
    cursor = conn.cursor()
    like = f"%{buscar}%"
    cursor.execute(
        _SELECT_MUESTRA + """
        WHERE m.estado IN ('pendiente_envio', 'en_análisis')
          AND (
              m.id_especificacion IS NULL
              OR EXISTS (
                  SELECT 1 FROM lims_especificacion_ensayos see
                  INNER JOIN lims_categorias_ensayo cat ON cat.id_categoria = see.id_categoria
                  WHERE see.id_especificacion = m.id_especificacion AND cat.momento = 'analisis' AND see.activo = 1
              )
          )
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


# ── Checklist de muestreo (etapa 'muestreo' de la especificación) ──
#
# Mismo mecanismo que usa Ejecutar Muestreo (Solicitud de Muestreo ->
# orden-trabajo-digital, ver solicitudes_muestreo.py), expuesto acá
# directo por id_muestra para las muestras creadas con Nueva Muestra, que
# no tienen una solicitud detrás. Reutiliza los mismos helpers
# (app/services/especificaciones.py) y los mismos schemas
# (ChecklistMuestreoItem/Respuesta) -- no hay una segunda implementación
# del checklist, solo un segundo punto de entrada.

@router.get("/{id_muestra}/checklist-muestreo", response_model=list[ChecklistMuestreoItem])
def checklist_muestreo_muestra(
    id_muestra: int,
    user: dict = Depends(get_current_user),
    conn: pyodbc.Connection = Depends(limss_db),
):
    cursor = conn.cursor()
    cursor.execute("SELECT id_especificacion FROM lims_muestras WHERE id_muestra = ?", id_muestra)
    muestra = cursor.fetchone()
    if not muestra:
        raise HTTPException(status_code=404, detail="Muestra no encontrada")
    return obtener_checklist_muestreo(cursor, id_muestra, muestra.id_especificacion)


@router.post("/{id_muestra}/checklist-muestreo", response_model=list[ChecklistMuestreoItem])
def guardar_checklist_muestreo_muestra(
    id_muestra: int,
    body: list[ChecklistMuestreoRespuesta],
    user: dict = Depends(require_rol(*_ROLES_MUESTREADOR_O_SUPERIOR)),
    conn: pyodbc.Connection = Depends(limss_db),
):
    cursor = conn.cursor()
    cursor.execute("SELECT id_especificacion FROM lims_muestras WHERE id_muestra = ?", id_muestra)
    muestra = cursor.fetchone()
    if not muestra:
        raise HTTPException(status_code=404, detail="Muestra no encontrada")

    guardar_checklist_muestreo(cursor, id_muestra, muestra.id_especificacion, body, user["id_usuario"])

    audit.registrar(
        conn, entidad="muestra", accion="completar_checklist_muestreo",
        id_usuario=user["id_usuario"], id_entidad=id_muestra,
        valor_nuevo={"items_enviados": len(body)},
    )

    return obtener_checklist_muestreo(cursor, id_muestra, muestra.id_especificacion)


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
        WHERE se.id_especificacion = ? AND se.id_laboratorio = ? AND se.activo = 1
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
            WHERE se.id_especificacion = ? AND se.id_espec_ensayo IN ({placeholders}) AND se.activo = 1
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
            WHERE se.id_especificacion = ? AND se.id_laboratorio = ? AND se.activo = 1
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


def _envio_facturado(cursor, id_envio: int) -> bool:
    """True si al menos uno de los ensayos de este envío tiene una fila en
    lims_factura_detalle (facturación por ensayo) -- ver app/api/routes/
    facturas.py, guardar_desglose. Se puebla junto con lims_factura_envios
    en la misma transacción de crear_factura, pero acá se chequea puntual
    contra lims_factura_detalle porque es el criterio pedido para este
    indicador (independiente del resumen de factura en `factura`, que usa
    lims_factura_envios). lims_factura_detalle puede no existir todavía
    (ver _tiene_tabla_factura_detalle en facturas.py, migración pendiente
    de ejecutar en algunos entornos) -- sin la tabla, ningún envío puede
    estar facturado por ensayo."""
    if not _tiene_tabla_factura_detalle(cursor):
        return False
    cursor.execute(
        """
        SELECT 1 FROM lims_envio_ensayos ee
        WHERE ee.id_envio = ? AND EXISTS (SELECT 1 FROM lims_factura_detalle fd WHERE fd.id_envio_ensayo = ee.id)
        """,
        id_envio,
    )
    return cursor.fetchone() is not None


def _envio_tiene_remito(cursor, id_envio: int) -> bool:
    cursor.execute("SELECT 1 FROM lims_remitos WHERE id_envio = ?", id_envio)
    return cursor.fetchone() is not None


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
            facturado=_envio_facturado(cursor, row.id_envio),
            tiene_remito=_envio_tiene_remito(cursor, row.id_envio),
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
        SELECT e.id_envio, e.id_laboratorio,
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

    fecha_vencimiento_confirmada, sin_vencimiento_confirmado, tiene_solicitud_muestreo = (
        _datos_vencimiento_confirmado(cursor, id_muestra)
    )
    laboratorio_requiere_coas, tiene_protocolo_proveedor = _datos_coas(cursor, id_muestra, row.id_laboratorio)

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
        fecha_vencimiento_confirmada=fecha_vencimiento_confirmada,
        sin_vencimiento_confirmado=sin_vencimiento_confirmado,
        tiene_solicitud_muestreo=tiene_solicitud_muestreo,
        laboratorio_requiere_coas=laboratorio_requiere_coas,
        tiene_protocolo_proveedor=tiene_protocolo_proveedor,
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
    sin cambios.

    Una muestra creada por "Nueva Muestra" (en vez de por Solicitudes de
    Muestreo) no tiene fila en lims_solicitudes_muestreo -- en ese caso, en
    vez de devolver 404 (el botón "Imprimir etiqueta" se ofrece para
    cualquier muestra sin importar cómo se haya creado), se busca si su
    especificación define varios tipos de muestra (lims_especificacion_
    muestras -- ver obtener_tipos_de_especificacion) y se genera una
    etiqueta por tipo, igual que para una solicitud confirmada. Solo si la
    especificación no define ningún tipo (o la muestra no tiene
    especificación) se arma la etiqueta simplificada de siempre (ver
    generar_pdf_etiqueta_muestra) -- bug real detectado con PT019 (4 tipos
    definidos en su especificación, antes solo salía 1 etiqueta genérica
    para una muestra sin solicitud)."""
    cursor = conn.cursor()
    cursor.execute("SELECT id_solicitud FROM lims_solicitudes_muestreo WHERE id_muestra = ?", id_muestra)
    fila = cursor.fetchone()

    if fila:
        row = obtener_solicitud_o_404(cursor, fila.id_solicitud)
        pdf_bytes = generar_pdf_etiquetas_de_solicitud(cursor, row)
        nombre_archivo = f"{row.nro_solicitud}_etiquetas.pdf"
    else:
        cursor.execute(_SELECT_MUESTRA + " WHERE m.id_muestra = ?", id_muestra)
        muestra = cursor.fetchone()
        if not muestra:
            raise HTTPException(status_code=404, detail="Muestra no encontrada")
        try:
            iniciales = iniciales_muestreador(cursor, muestra.id_usuario_muestreo)
            tipos = obtener_tipos_de_especificacion(cursor, muestra.id_especificacion) if muestra.id_especificacion else []
            if tipos:
                solicitud_shim = SimpleNamespace(
                    nro_solicitud=muestra.codigo_muestra,
                    erp_DESART=muestra.erp_DESART,
                    erp_CODART=muestra.erp_CODART,
                    erp_nro_ir=muestra.nro_referencia,
                    tipo_referencia=muestra.tipo_referencia,
                    fecha_solicitud=muestra.fecha_muestreo,
                )
                pdf_bytes = generar_pdf_etiquetas_v2(solicitud_shim, tipos, iniciales)
            else:
                pdf_bytes = generar_pdf_etiqueta_muestra(muestra, iniciales)
        except Exception:
            logger.error("Error generando la etiqueta simplificada (id_muestra=%s)", id_muestra, exc_info=True)
            raise HTTPException(status_code=500, detail="No se pudo generar el PDF de etiquetas -- ver el log del servidor")
        nombre_archivo = f"{muestra.codigo_muestra}_etiquetas.pdf"

    return Response(
        content=pdf_bytes, media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{nombre_archivo}"'},
    )


def _datos_etiqueta_para_impresion(cursor, id_muestra: int) -> dict:
    """Mismos datos que ya muestra la etiqueta en PDF (ver
    descargar_etiquetas_de_muestra arriba) pero como dict de campos planos,
    para que generar_sbpl_etiqueta arme el layout SBPL en vez de dibujar un
    PDF con reportlab. Se apoya siempre en lims_muestras (existe para
    cualquier muestra, tenga o no una Solicitud de Muestreo asociada) y
    enriquece con nro_solicitud/laboratorio cuando esa fila existe.

    Incluye id_solicitud e id_especificacion (no son campos de la etiqueta
    en sí, los saca imprimir_etiqueta_directo antes de armar el SBPL) para
    que el llamador pueda resolver los tipos de muestra confirmados (ver
    obtener_muestras_confirmadas) o, si no hay solicitud asociada, los tipos
    definidos en la especificación misma (ver obtener_tipos_de_
    especificacion) -- más abajo."""
    cursor.execute(_SELECT_MUESTRA + " WHERE m.id_muestra = ?", id_muestra)
    muestra = cursor.fetchone()
    if not muestra:
        raise HTTPException(status_code=404, detail="Muestra no encontrada")

    cursor.execute(
        """
        SELECT s.id_solicitud, s.nro_solicitud, lab.nombre AS laboratorio_nombre
        FROM lims_solicitudes_muestreo s
        LEFT JOIN lims_laboratorios lab ON lab.id_laboratorio = s.id_laboratorio
        WHERE s.id_muestra = ?
        """,
        id_muestra,
    )
    solicitud = cursor.fetchone()

    if muestra.cantidad_enviada is not None:
        cantidad_texto = f"{formatear_cantidad(muestra.cantidad_enviada)} {muestra.unidad_enviada or ''}".strip()
    else:
        cantidad_texto = None

    return {
        "titulo": "MUESTRA PARA ANÁLISIS" if solicitud else "MUESTRA",
        "identificador": solicitud.nro_solicitud if solicitud else muestra.codigo_muestra,
        "erp_codart": muestra.erp_CODART.strip() if muestra.erp_CODART else None,
        "erp_desart": muestra.erp_DESART.strip() if muestra.erp_DESART else None,
        "nro_ir": muestra.nro_referencia,
        "etiqueta_referencia": etiqueta_referencia(muestra.tipo_referencia),
        "cantidad_texto": cantidad_texto,
        "laboratorio_nombre": solicitud.laboratorio_nombre if solicitud else None,
        "fecha": muestra.fecha_muestreo,
        "iniciales_muestreador": iniciales_muestreador(cursor, muestra.id_usuario_muestreo),
        "id_solicitud": solicitud.id_solicitud if solicitud else None,
        "id_especificacion": muestra.id_especificacion,
    }



def _armar_etiquetas_logicas_de_muestra(cursor, id_muestra: int) -> list[dict]:
    """Una etiqueta lógica por cada tipo de muestra confirmado en la
    especificación (análisis, contramuestra, testigo, ad-hoc, etc.) --
    misma fuente de datos (obtener_muestras_confirmadas, SIN filtrar por
    tipo -- trae todas las filas confirmadas de lims_solicitud_muestras) y
    mismo criterio que ya usa el PDF (generar_pdf_etiquetas_v2 en
    solicitudes_muestreo.py), para no mantener dos lógicas de iteración
    distintas. Si la muestra no tiene Solicitud de Muestreo asociada, se
    busca en su lugar si la especificación misma define varios tipos (ver
    obtener_tipos_de_especificacion) -- bug real detectado con PT019 (4
    tipos definidos, antes salía 1 sola etiqueta genérica para una muestra
    sin solicitud). Solo si tampoco hay tipos definidos en la especificación
    (o la muestra no tiene especificación) se manda una sola etiqueta
    genérica -- mismo fallback que ya usa el PDF.

    Factorizada de imprimir_etiqueta_directo para que el conteo previo (ver
    GET /{id_muestra}/etiquetas-cantidad, para mostrar "se van a imprimir N"
    ANTES de mandar el trabajo real) use exactamente la misma resolución que
    el envío real, en vez de dos caminos que puedan divergir."""
    datos_base = _datos_etiqueta_para_impresion(cursor, id_muestra)
    id_solicitud = datos_base.pop("id_solicitud", None)
    id_especificacion = datos_base.pop("id_especificacion", None)

    tipos_confirmados = obtener_muestras_confirmadas(cursor, id_solicitud) if id_solicitud else []
    if not tipos_confirmados and id_especificacion:
        tipos_confirmados = obtener_tipos_de_especificacion(cursor, id_especificacion)

    etiquetas = []
    if tipos_confirmados:
        for t in tipos_confirmados:
            d = dict(datos_base)
            # Título por tipo (mismo texto que usa el PDF para cada etiqueta
            # individual, ver generar_pdf_etiquetas_v2) -- reemplaza al
            # título genérico de datos_base.
            d["titulo"] = titulo_etiqueta_por_tipo(t.tipo_muestra)
            d["cantidad_muestra_texto"] = (
                f"{formatear_cantidad(t.cantidad_real)} {t.unidad or ''}".strip() if t.cantidad_real is not None else None
            )
            # Laboratorio propio de ESTE tipo de muestra (puede diferir del
            # laboratorio general de la solicitud) -- mismo dato que usa el
            # PDF para cada etiqueta individual.
            d["laboratorio_nombre"] = t.laboratorio_nombre
            etiquetas.append(d)
    else:
        etiquetas.append(datos_base)
    return etiquetas


@router.get("/{id_muestra}/etiquetas-cantidad", response_model=CantidadEtiquetasResponse)
def contar_etiquetas_a_imprimir(
    id_muestra: int,
    user: dict = Depends(get_current_user),
    conn: pyodbc.Connection = Depends(limss_db),
):
    """Cuántas etiquetas lógicas y físicas (agrupadas de a 2, ver
    armar_pares_etiquetas_muestra en impresion_sato.py) se van a generar
    para esta muestra si se
    imprime por SATO -- mismo cálculo que imprimir_etiqueta_directo, para
    poder mostrarle al usuario "se van a imprimir N" ANTES de mandar el
    trabajo real a la impresora (mismo criterio ya usado para CUARENTENA,
    donde la cantidad -- una etiqueta por bulto -- se conoce de antemano sin
    tener que armar el trabajo de impresión primero)."""
    cursor = conn.cursor()
    etiquetas = _armar_etiquetas_logicas_de_muestra(cursor, id_muestra)
    return CantidadEtiquetasResponse(
        cantidad_muestras=len(etiquetas),
        cantidad_etiquetas_fisicas=len(armar_pares_etiquetas_muestra(etiquetas)),
    )


@router.post("/{id_muestra}/imprimir-directo", response_model=ImprimirDirectoResponse)
def imprimir_etiqueta_directo(
    id_muestra: int,
    body: ImprimirDirectoBody,
    user: dict = Depends(require_rol("muestreador", "analista_qc", "qa", "admin")),
    conn: pyodbc.Connection = Depends(limss_db),
):
    """Alternativa a "Descargar PDF" (no la reemplaza): arma el comando SBPL
    y lo manda directo, como trabajo RAW, a una impresora SATO configurada
    en lims_impresoras_etiquetas -- ver app/services/impresion_sato.py.

    La lista de etiquetas lógicas se arma en _armar_etiquetas_logicas_de_
    muestra (ver ahí el criterio completo de resolución/fallback).

    Esas etiquetas lógicas se agrupan de a 2 por ETIQUETA FÍSICA
    (armar_pares_etiquetas_muestra + generar_sbpl_etiqueta_par): el rollo
    es continuo, así que combinar dos muestras en una misma etiqueta física
    (una arriba, una abajo) reduce a la mitad la cantidad de etiquetas
    físicas usadas."""
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM lims_impresoras_etiquetas WHERE id_impresora = ? AND activa = 1", body.id_impresora)
    impresora = cursor.fetchone()
    if not impresora:
        raise HTTPException(status_code=404, detail="La impresora indicada no existe o está inactiva")

    etiquetas = _armar_etiquetas_logicas_de_muestra(cursor, id_muestra)

    # Dos muestras por etiqueta física (rollo continuo -- ver
    # generar_sbpl_etiqueta_par y armar_pares_etiquetas_muestra): agrupadas
    # de a 2 en el mismo orden en que viene `etiquetas`, un solo trabajo de
    # impresión por par en vez de uno por etiqueta.
    pares = armar_pares_etiquetas_muestra(etiquetas)
    enviadas = 0
    for arriba, abajo in pares:
        sbpl_bytes = generar_sbpl_etiqueta_par(
            arriba, abajo, impresora.ancho_mm, impresora.alto_mm, impresora.resolucion_dpi, cantidad_copias=body.cantidad,
        )
        nombre_trabajo = f"Etiqueta {arriba['identificador']}"
        if abajo:
            nombre_trabajo += f" + {abajo['identificador']}"
        try:
            imprimir_sbpl(impresora, sbpl_bytes, nombre_trabajo=nombre_trabajo)
        except RuntimeError as e:
            detalle = str(e)
            if enviadas:
                detalle += f" (se enviaron {enviadas} de {len(pares)} etiquetas antes de este error)"
            raise HTTPException(status_code=502, detail=detalle)
        enviadas += 1

    audit.registrar(
        conn, entidad="etiqueta", accion="imprimir_directo",
        id_usuario=user["id_usuario"], id_entidad=id_muestra,
        valor_nuevo={"id_impresora": body.id_impresora, "ruta_red": impresora.ruta_red, "cantidad_etiquetas": enviadas},
    )

    plural = "s" if enviadas != 1 else ""
    return ImprimirDirectoResponse(ok=True, mensaje=f"{enviadas} etiqueta{plural} enviada{plural} a {impresora.nombre}")


def _imprimir_etiqueta_estado_muestra(
    id_muestra: int, body: ImprimirDirectoBody, user: dict, conn: pyodbc.Connection,
    estados_permitidos: tuple[str, ...], titulo: str, entidad_auditoria: str,
) -> ImprimirDirectoResponse:
    """Etiqueta APROBADO/RECHAZADO -- reutiliza el mismo generador de layout
    (generar_sbpl_etiqueta_estado) que ya usa CUARENTENA, solo cambia el
    título.

    APROBADO acepta tanto 'aprobado' (dictamen formal ya emitido) como
    'aprobado_sin_dictamen' (decisión consciente, ver guardar_resultados en
    resultados.py: todos los ensayos ya dieron dentro de especificación, el
    material puede salir de cuarentena sin esperar el papeleo formal).
    RECHAZADO sigue exigiendo el dictamen formal ('rechazado') -- no hay
    estado "sin dictamen" equivalente para el caso de rechazo, esa decisión
    sí necesita la revisión y justificación de QA antes de imprimir nada.
    En cualquier caso, mientras la muestra esté 'en_análisis' (resultados
    todavía incompletos), ninguna de las dos etiquetas está disponible.

    Si titulo == "APROBADO" y la especificación de la muestra tiene
    cantidad_etiquetas_complementarias > 0 (ficha de especificación, Datos
    Maestros), se adjuntan esa cantidad de etiquetas "APROBADO --
    COMPLEMENTARIA" (generar_sbpl_etiqueta_complementaria) al final del
    mismo trabajo de impresión -- no es una opción aparte que haya que
    buscar o elegir, se imprime automáticamente junto con la principal.
    RECHAZADO nunca lleva complementaria."""
    cursor = conn.cursor()
    cursor.execute(_SELECT_MUESTRA + " WHERE m.id_muestra = ?", id_muestra)
    muestra = cursor.fetchone()
    if not muestra:
        raise HTTPException(status_code=404, detail="Muestra no encontrada")
    if muestra.estado not in estados_permitidos:
        raise HTTPException(
            status_code=400,
            detail=f"No se puede imprimir la etiqueta {titulo}: estado actual de la muestra '{muestra.estado}'",
        )

    cursor.execute("SELECT * FROM lims_impresoras_etiquetas WHERE id_impresora = ? AND activa = 1", body.id_impresora)
    impresora = cursor.fetchone()
    if not impresora:
        raise HTTPException(status_code=404, detail="La impresora indicada no existe o está inactiva")

    cursor.execute(
        "SELECT id_solicitud, fecha_ingreso, fecha_vencimiento, nro_bultos FROM lims_solicitudes_muestreo WHERE id_muestra = ?",
        id_muestra,
    )
    solicitud = cursor.fetchone()

    if muestra.cantidad_enviada is not None:
        cantidad_texto = f"{formatear_cantidad(muestra.cantidad_enviada)} {muestra.unidad_enviada or ''}".strip()
    else:
        cantidad_texto = None

    datos_base = {
        "erp_desart": muestra.erp_DESART,
        "erp_codart": muestra.erp_CODART,
        "nro_ir": muestra.nro_referencia,
        "etiqueta_referencia": etiqueta_referencia(muestra.tipo_referencia),
        "fecha_ingreso": _a_fecha(solicitud.fecha_ingreso) if solicitud else None,
        "fecha_vencimiento": _a_fecha(solicitud.fecha_vencimiento) if solicitud else None,
    }

    grupos = obtener_grupos_bultos(cursor, solicitud.id_solicitud) if solicitud else []
    bultos_fallback = solicitud.nro_bultos if solicitud and solicitud.nro_bultos else 1
    bultos = expandir_bultos(grupos, bultos_fallback, cantidad_texto, cantidad_valor_fallback=muestra.cantidad_enviada)
    total_bultos = bultos[0].bulto_total

    try:
        bultos_a_imprimir = filtrar_rango_bultos(bultos, body.desde_bulto, body.hasta_bulto)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # Cantidad de etiquetas complementarias a adjuntar (solo APROBADO) --
    # tolerante a que la migración de cantidad_etiquetas_complementarias
    # todavía no haya corrido en este entorno (mismo criterio que el resto
    # de columnas nuevas de este codebase): si falla, se asume 0 en vez de
    # romper toda la impresión de Aprobado por una función accesoria.
    cantidad_etiquetas_complementarias = 0
    if titulo == "APROBADO" and muestra.id_especificacion is not None:
        try:
            cursor.execute(
                "SELECT cantidad_etiquetas_complementarias FROM lims_especificaciones WHERE id_especificacion = ?",
                muestra.id_especificacion,
            )
            fila_espec = cursor.fetchone()
            cantidad_etiquetas_complementarias = int(fila_espec.cantidad_etiquetas_complementarias) if fila_espec and fila_espec.cantidad_etiquetas_complementarias else 0
        except pyodbc.Error:
            pass

    enviadas = 0
    for b in bultos_a_imprimir:
        datos = dict(
            datos_base, bulto_actual=b.bulto_actual, bulto_total=b.bulto_total,
            cantidad_texto=b.cantidad_texto, cantidad_valor=b.cantidad_valor,
        )
        sbpl_bytes = generar_sbpl_etiqueta_estado(
            datos, titulo, impresora.ancho_mm, impresora.alto_mm, impresora.resolucion_dpi,
            cantidad_copias=body.cantidad,
        )
        try:
            imprimir_sbpl(impresora, sbpl_bytes, nombre_trabajo=f"{titulo.capitalize()} {muestra.codigo_muestra} {b.bulto_actual}/{b.bulto_total}")
        except RuntimeError as e:
            detalle = str(e)
            if enviadas:
                detalle += f" (se enviaron {enviadas} de {len(bultos_a_imprimir)} etiquetas antes de este error)"
            raise HTTPException(status_code=502, detail=detalle)
        enviadas += 1

    # Etiquetas complementarias, adjuntas al mismo trabajo de impresión (ver
    # cantidad_etiquetas_complementarias más arriba) -- un solo job con N
    # copias, no una por bulto: la complementaria no lleva bulto_actual/
    # bulto_total (no hay dato que la distinga entre bultos).
    complementarias_enviadas = 0
    if cantidad_etiquetas_complementarias > 0:
        datos_complementaria = {
            "erp_codart": muestra.erp_CODART,
            "nro_ir": muestra.nro_referencia,
            "etiqueta_referencia": datos_base["etiqueta_referencia"],
        }
        sbpl_complementaria = generar_sbpl_etiqueta_complementaria(
            datos_complementaria, impresora.ancho_mm, impresora.alto_mm, impresora.resolucion_dpi,
            cantidad_copias=cantidad_etiquetas_complementarias,
        )
        try:
            imprimir_sbpl(impresora, sbpl_complementaria, nombre_trabajo=f"Aprobado complementaria {muestra.codigo_muestra}")
        except RuntimeError as e:
            raise HTTPException(
                status_code=502,
                detail=f"{str(e)} (se enviaron {enviadas} etiqueta{'s' if enviadas != 1 else ''} {titulo} antes de este error, faltaron las complementarias)",
            )
        complementarias_enviadas = cantidad_etiquetas_complementarias

    audit.registrar(
        conn, entidad=entidad_auditoria, accion="imprimir",
        id_usuario=user["id_usuario"], id_entidad=id_muestra,
        valor_nuevo={
            "id_impresora": body.id_impresora, "ruta_red": impresora.ruta_red, "cantidad": body.cantidad,
            "cantidad_etiquetas": enviadas, "cantidad_etiquetas_complementarias": complementarias_enviadas,
            "desde_bulto": body.desde_bulto, "hasta_bulto": body.hasta_bulto,
        },
    )

    plural = "s" if enviadas != 1 else ""
    mensaje = f"{enviadas} etiqueta{plural} {titulo} enviada{plural} a {impresora.nombre}"
    if len(bultos_a_imprimir) != total_bultos:
        mensaje += f" (bultos {bultos_a_imprimir[0].bulto_actual} a {bultos_a_imprimir[-1].bulto_actual} de {total_bultos})"
    if complementarias_enviadas:
        plural_compl = "s" if complementarias_enviadas != 1 else ""
        mensaje += f" + {complementarias_enviadas} complementaria{plural_compl}"
    return ImprimirDirectoResponse(ok=True, mensaje=mensaje)


@router.post("/{id_muestra}/imprimir-aprobado", response_model=ImprimirDirectoResponse)
def imprimir_etiqueta_aprobado(
    id_muestra: int,
    body: ImprimirDirectoBody,
    user: dict = Depends(require_rol("analista_qc", "qa", "admin")),
    conn: pyodbc.Connection = Depends(limss_db),
):
    return _imprimir_etiqueta_estado_muestra(
        id_muestra, body, user, conn, ("aprobado", "aprobado_sin_dictamen"), "APROBADO", "etiqueta_aprobado",
    )


@router.post("/{id_muestra}/imprimir-rechazado", response_model=ImprimirDirectoResponse)
def imprimir_etiqueta_rechazado(
    id_muestra: int,
    body: ImprimirDirectoBody,
    user: dict = Depends(require_rol("analista_qc", "qa", "admin")),
    conn: pyodbc.Connection = Depends(limss_db),
):
    return _imprimir_etiqueta_estado_muestra(id_muestra, body, user, conn, ("rechazado",), "RECHAZADO", "etiqueta_rechazado")
