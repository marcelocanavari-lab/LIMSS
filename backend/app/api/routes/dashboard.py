"""
Dashboard de inicio: resumen agregado del estado del sistema (contadores +
alertas), pantalla de aterrizaje que reemplaza al menú principal.

Los conteos reutilizan exactamente los mismos filtros que ya usan sus
pantallas de origen (bandeja de envío, bandeja de dictamen, etc.) para que
el número de la card y lo que aparece al hacer clic siempre coincidan.
"""
from datetime import date, datetime

import pyodbc
from fastapi import APIRouter, Depends, Query

from app.api.routes.dictamenes import WHERE_MUESTRA_PENDIENTE_DICTAMEN
from app.api.routes.maestros import (
    ESTADOS_TESTIGO_VALIDOS,
    cumple_filtro_estado_testigo,
    fila_a_testigo,
    ordenar_por_fecha_vencimiento,
    select_testigos_sql,
)
from app.core.security import get_current_user
from app.db.connections import limss_db
from app.schemas.dashboard import DashboardResumenResponse, MuestreadorActivoItem, SolicitudSinEjecutarItem
from app.schemas.maestros import TestigoResponse

router = APIRouter(prefix="/api/dashboard", tags=["Dashboard"])


def _a_fecha(valor) -> date | None:
    """El driver ODBC no devuelve un tipo consistente para columnas DATE en
    este entorno (a veces date/datetime, a veces str); se normaliza siempre
    a date antes de operar (mismo patrón que maestros.py)."""
    if valor is None:
        return None
    if isinstance(valor, datetime):
        return valor.date()
    if isinstance(valor, date):
        return valor
    return date.fromisoformat(str(valor))


@router.get("/resumen", response_model=DashboardResumenResponse)
def resumen(
    user: dict = Depends(get_current_user),
    conn: pyodbc.Connection = Depends(limss_db),
):
    cursor = conn.cursor()

    cursor.execute("SELECT COUNT(*) AS c FROM lims_solicitudes_muestreo WHERE estado = 'pendiente'")
    solicitudes_pendientes = cursor.fetchone().c

    cursor.execute(
        "SELECT COUNT(*) AS c FROM lims_muestras WHERE estado IN ('pendiente_envio', 'en_análisis')"
    )
    muestras_en_proceso = cursor.fetchone().c

    # Mismo EXISTS que /api/muestras/laboratorios... (listar_pendientes_resultados
    # en resultados.py): un envío "pendiente" es el que tiene algún ensayo
    # solicitado sin resultado cargado todavía.
    cursor.execute(
        """
        SELECT COUNT(*) AS c
        FROM lims_envios e
        INNER JOIN lims_muestras m ON m.id_muestra = e.id_muestra
        WHERE m.estado = 'en_análisis'
          AND EXISTS (
              SELECT 1 FROM lims_envio_ensayos ee
              LEFT JOIN lims_resultados r ON r.id_espec_ensayo = ee.id_espec_ensayo AND r.id_envio = ee.id_envio
              WHERE ee.id_envio = e.id_envio AND r.id_resultado IS NULL
          )
        """
    )
    resultados_pendientes = cursor.fetchone().c

    # dictamenes_pendientes queda en 0 para roles sin acceso a la bandeja de
    # QA -- el frontend igual no muestra esa card salvo qa/admin.
    dictamenes_pendientes = 0
    if user["rol"] in ("qa", "admin"):
        cursor.execute(f"SELECT COUNT(*) AS c FROM lims_muestras m WHERE {WHERE_MUESTRA_PENDIENTE_DICTAMEN}")
        dictamenes_pendientes = cursor.fetchone().c

    return DashboardResumenResponse(
        solicitudes_pendientes=solicitudes_pendientes,
        muestras_en_proceso=muestras_en_proceso,
        resultados_pendientes=resultados_pendientes,
        dictamenes_pendientes=dictamenes_pendientes,
    )


@router.get("/solicitudes-pendientes", response_model=list[SolicitudSinEjecutarItem])
def solicitudes_pendientes_dashboard(
    id_muestreador: int = Query(0, description="0 o ausente = todos los muestreadores"),
    user: dict = Depends(get_current_user),
    conn: pyodbc.Connection = Depends(limss_db),
):
    """Sección "Solicitudes sin ejecutar" del dashboard, con filtro por
    muestreador interactivo. Todas las pendientes, sin filtro de antigüedad
    -- la card de resumen ya cuenta "solicitudes_pendientes" en total, así
    que sin filtro esta lista tiene que coincidir con ese número."""
    cursor = conn.cursor()
    if id_muestreador:
        cursor.execute(
            """
            SELECT s.id_solicitud, s.nro_solicitud, s.erp_DESART, s.fecha_solicitud,
                   um.nombre + ' ' + um.apellido AS muestreador_nombre
            FROM lims_solicitudes_muestreo s
            LEFT JOIN lims_usuarios um ON um.id_usuario = s.id_muestreador
            WHERE s.estado = 'pendiente' AND s.id_muestreador = ?
            ORDER BY s.fecha_solicitud ASC
            """,
            id_muestreador,
        )
    else:
        cursor.execute(
            """
            SELECT s.id_solicitud, s.nro_solicitud, s.erp_DESART, s.fecha_solicitud,
                   um.nombre + ' ' + um.apellido AS muestreador_nombre
            FROM lims_solicitudes_muestreo s
            LEFT JOIN lims_usuarios um ON um.id_usuario = s.id_muestreador
            WHERE s.estado = 'pendiente'
            ORDER BY s.fecha_solicitud ASC
            """
        )
    ahora = datetime.now()
    return [
        SolicitudSinEjecutarItem(
            id_solicitud=r.id_solicitud,
            nro_solicitud=r.nro_solicitud,
            erp_DESART=r.erp_DESART,
            muestreador_nombre=r.muestreador_nombre,
            dias_pendiente=(ahora - r.fecha_solicitud).days,
        )
        for r in cursor.fetchall()
    ]


@router.get("/muestreadores-activos", response_model=list[MuestreadorActivoItem])
def muestreadores_activos_dashboard(
    user: dict = Depends(get_current_user),
    conn: pyodbc.Connection = Depends(limss_db),
):
    """Para poblar el dropdown de filtro de la sección "Solicitudes sin
    ejecutar" -- solo muestreadores que tienen al menos una solicitud
    pendiente ahora mismo."""
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT DISTINCT u.id_usuario, u.nombre, u.apellido
        FROM lims_solicitudes_muestreo s
        INNER JOIN lims_usuarios u ON u.id_usuario = s.id_muestreador
        WHERE s.estado = 'pendiente'
        ORDER BY u.apellido, u.nombre
        """
    )
    return [
        MuestreadorActivoItem(id_usuario=r.id_usuario, nombre_completo=f"{r.nombre} {r.apellido}")
        for r in cursor.fetchall()
    ]


@router.get("/testigos", response_model=list[TestigoResponse])
def testigos_dashboard(
    estados: str = Query("", description="Lista separada por comas: vencido,por_vencer,normal,sin_vencimiento,stock_bajo. Vacío/ausente = todos los testigos, sin filtro de estado."),
    orden: str = Query("vencimiento_asc", pattern=r"^(vencimiento_asc|vencimiento_desc|nombre_asc|codigo_asc)$"),
    limite: int = Query(100, ge=1, le=500),
    fecha_ref: date | None = Query(None, description="Fecha de referencia para calcular vencido/por_vencer; por defecto, hoy"),
    dias_anticipacion: int = Query(30, ge=0, description="Días de anticipación para considerar 'por vencer'"),
    user: dict = Depends(get_current_user),
    conn: pyodbc.Connection = Depends(limss_db),
):
    """Sección "Testigos por vencer" del dashboard, con filtro de estados y
    orden interactivos -- misma clasificación (fecha_ref/dias_anticipacion
    configurables) que usa TestigosPage (ver _fila_a_testigo/_select_testigos_sql
    en maestros.py, reexportados para no duplicar esa lógica acá). Sin ningún
    estado seleccionado no hay filtro (se devuelven todos los activos); con
    estados seleccionados, stock_bajo se combina con AND sobre el OR de los
    de vencimiento (ver _cumple_filtro_estado_testigo)."""
    estados_pedidos = {e.strip() for e in estados.split(",") if e.strip()} & ESTADOS_TESTIGO_VALIDOS

    cursor = conn.cursor()
    cursor.execute(select_testigos_sql(cursor) + "WHERE t.activo = 1")
    testigos = [fila_a_testigo(r, fecha_ref=fecha_ref, dias_anticipacion=dias_anticipacion, cursor=cursor) for r in cursor.fetchall()]
    if estados_pedidos:
        testigos = [t for t in testigos if cumple_filtro_estado_testigo(t, estados_pedidos)]

    if orden == "vencimiento_asc":
        testigos = ordenar_por_fecha_vencimiento(testigos, reverse=False)
    elif orden == "vencimiento_desc":
        testigos = ordenar_por_fecha_vencimiento(testigos, reverse=True)
    elif orden == "nombre_asc":
        testigos = sorted(testigos, key=lambda t: t.nombre)
    elif orden == "codigo_asc":
        testigos = sorted(testigos, key=lambda t: t.codigo)

    return testigos[:limite]
