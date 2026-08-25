"""
Integraciones server-to-server con el eBR Veterinario (sistema hermano,
mismo servidor): crear una muestra directamente desde un paso de PREL de
tipo "Toma de Muestra" -- muestreo en proceso de producción -- sin pasar por
el flujo normal de Solicitud de Muestreo, que es solo para inspección de
materia prima entrante.

Autenticación por API key compartida (header X-API-Key, ver
verificar_acceso_ebr en app/core/security.py): no hay sesión de usuario
LIMSS del lado del eBR, es el backend de eBR llamando directo, no una
persona navegando. Misma EBR_SYNC_API_KEY que ya usa la sincronización de
usuarios (GET /api/auth/usuarios-ebr) -- un solo secreto compartido para
toda la integración server-to-server con el eBR, no uno por endpoint.
"""
import json
from datetime import date, datetime, timedelta
from typing import Optional

import pyodbc
from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.routes.solicitudes_muestreo import generar_codigo_muestra
from app.core.security import require_rol, verificar_acceso_ebr
from app.db.connections import limss_db
from app.schemas.agente_muestreo import AgenteEvaluacion, AgenteLogEntry
from app.schemas.integraciones import (
    DictamenEstadoInfo,
    EnvioEstadoInfo,
    MuestraEstadoResponse,
    MuestraIntegracionCreate,
    MuestraIntegracionResponse,
    ProtocoloEstadoInfo,
)
from app.services import agente_muestreo, audit
from app.services.erp_materiales import asignar_numero_analisis_si_corresponde, tiene_numero_analisis

router = APIRouter(prefix="/api/integraciones", tags=["Integraciones eBR"])


@router.post("/muestras", response_model=MuestraIntegracionResponse, status_code=201)
def crear_muestra_desde_integracion(
    body: MuestraIntegracionCreate,
    _: None = Depends(verificar_acceso_ebr),
    conn: pyodbc.Connection = Depends(limss_db),
):
    """Toma de muestra en proceso de producción disparada desde un PREL del
    eBR. erp_nro_ir queda NULL a propósito -- este canal no tiene IR, la
    trazabilidad hacia el origen viaja en tipo_referencia/nro_referencia."""
    cursor = conn.cursor()

    codart = body.erp_CODART.strip()
    cursor.execute(
        "SELECT id_especificacion, erp_DESART FROM lims_especificaciones WHERE erp_CODART = ? AND vigente = 1",
        codart,
    )
    espec = cursor.fetchone()
    if not espec:
        raise HTTPException(
            status_code=422,
            detail=f"No hay especificación vigente en LIMSS para este producto ('{codart}')",
        )

    cursor.execute("SELECT 1 FROM lims_usuarios WHERE id_usuario = ? AND activo = 1", body.id_usuario_limss)
    if not cursor.fetchone():
        raise HTTPException(
            status_code=422,
            detail="El usuario LIMSS indicado (id_usuario_limss) no existe o está inactivo",
        )

    codigo_muestra = generar_codigo_muestra(cursor)

    # numero_analisis (Libro de Ingresos): correlativo exclusivo de Materia
    # Prima/Material de Empaque -- este canal es para muestreo EN PROCESO de
    # producción (ver docstring del módulo), así que en la práctica casi
    # nunca va a corresponder, pero se evalúa igual por erp_codsar (mismo
    # criterio que el resto de los flujos, ver
    # asignar_numero_analisis_si_corresponde) en vez de asumir que nunca
    # aplica acá.
    if tiene_numero_analisis(cursor):
        numero_analisis = asignar_numero_analisis_si_corresponde(conn, espec.id_especificacion)
        cursor.execute(
            """
            INSERT INTO lims_muestras
                (codigo_muestra, erp_nro_ir, erp_IdM21, erp_CODART, erp_DESART, id_especificacion,
                 estado, id_usuario_muestreo, fecha_muestreo, datos_muestreo_pendientes, tipo_referencia,
                 nro_referencia, observaciones, cantidad_enviada, unidad_enviada, numero_analisis)
            VALUES (?, NULL, ?, ?, ?, ?, 'pendiente_envio', ?, GETDATE(), 0, ?, ?, ?, ?, ?, ?)
            """,
            codigo_muestra, body.erp_IdM21, codart, espec.erp_DESART, espec.id_especificacion,
            body.id_usuario_limss, body.tipo_referencia, body.nro_referencia,
            body.observaciones, body.cantidad_enviada, body.unidad_enviada, numero_analisis,
        )
    else:
        cursor.execute(
            """
            INSERT INTO lims_muestras
                (codigo_muestra, erp_nro_ir, erp_IdM21, erp_CODART, erp_DESART, id_especificacion,
                 estado, id_usuario_muestreo, fecha_muestreo, datos_muestreo_pendientes, tipo_referencia,
                 nro_referencia, observaciones, cantidad_enviada, unidad_enviada)
            VALUES (?, NULL, ?, ?, ?, ?, 'pendiente_envio', ?, GETDATE(), 0, ?, ?, ?, ?, ?)
            """,
            codigo_muestra, body.erp_IdM21, codart, espec.erp_DESART, espec.id_especificacion,
            body.id_usuario_limss, body.tipo_referencia, body.nro_referencia,
            body.observaciones, body.cantidad_enviada, body.unidad_enviada,
        )
    cursor.execute("SELECT @@IDENTITY AS id")
    id_muestra = int(cursor.fetchone().id)

    # entidad="muestra" (no "lims_muestras") -- mismo nombre de entidad que
    # usa el resto del audit trail para esta tabla (ver confirmar_orden_
    # trabajo/crear_muestra), para que quede consistente y filtrable junto
    # con el resto de los registros de creación de muestras.
    audit.registrar(
        conn, entidad="muestra", accion="creado_via_integracion_ebr",
        id_usuario=body.id_usuario_limss, id_entidad=id_muestra,
        valor_nuevo={
            "codigo_muestra": codigo_muestra, "erp_CODART": codart,
            "tipo_referencia": body.tipo_referencia, "nro_referencia": body.nro_referencia,
        },
    )

    return MuestraIntegracionResponse(id_muestra=id_muestra, codigo_muestra=codigo_muestra, estado="pendiente_envio")


@router.get("/muestras/{id_muestra}/estado", response_model=MuestraEstadoResponse)
def estado_muestra_integracion(
    id_muestra: int,
    _: None = Depends(verificar_acceso_ebr),
    conn: pyodbc.Connection = Depends(limss_db),
):
    """Resumen de solo lectura para que el eBR lo consulte en vivo cada vez
    que alguien mira el paso de PREL correspondiente -- no guarda copia
    propia del lado del eBR, así que esto no modifica nada en LIMSS."""
    cursor = conn.cursor()
    cursor.execute("SELECT id_muestra, codigo_muestra, estado FROM lims_muestras WHERE id_muestra = ?", id_muestra)
    muestra = cursor.fetchone()
    if not muestra:
        raise HTTPException(status_code=404, detail="Muestra no encontrada")

    # El número real de remito lo genera el sistema (lims_remitos.nro_remito_
    # interno) -- lims_envios.nro_remito es un campo manual que casi siempre
    # queda vacío (mismo bug ya visto y corregido en Facturación/Consulta de
    # Muestras); un envío puede tener más de un remito, se toma el más
    # reciente.
    cursor.execute(
        """
        SELECT e.id_envio, lab.nombre AS laboratorio, e.fecha_despacho,
               rem.nro_remito_interno AS nro_remito
        FROM lims_envios e
        INNER JOIN lims_laboratorios lab ON lab.id_laboratorio = e.id_laboratorio
        OUTER APPLY (
            SELECT TOP 1 r.nro_remito_interno
            FROM lims_remitos r
            WHERE r.id_envio = e.id_envio
            ORDER BY r.id_remito DESC
        ) rem
        WHERE e.id_muestra = ?
        ORDER BY e.id_envio
        """,
        id_muestra,
    )
    envios = [
        EnvioEstadoInfo(
            id_envio=r.id_envio, laboratorio=r.laboratorio,
            nro_remito=r.nro_remito, fecha_despacho=r.fecha_despacho,
        )
        for r in cursor.fetchall()
    ]

    cursor.execute(
        """
        SELECT p.nro_protocolo_ext, p.fecha_emision, p.pdf_path
        FROM lims_protocolos p
        INNER JOIN lims_envios e ON e.id_envio = p.id_envio
        WHERE e.id_muestra = ?
        ORDER BY p.fecha_carga
        """,
        id_muestra,
    )
    protocolos = [
        ProtocoloEstadoInfo(nro_protocolo_ext=r.nro_protocolo_ext, fecha_emision=r.fecha_emision, pdf_path=r.pdf_path)
        for r in cursor.fetchall()
    ]

    cursor.execute(
        """
        SELECT TOP 1 estado_dictamen, fecha_dictamen, observaciones
        FROM lims_dictamenes WHERE id_muestra = ? ORDER BY fecha_dictamen DESC
        """,
        id_muestra,
    )
    d = cursor.fetchone()
    dictamen = (
        DictamenEstadoInfo(
            estado_dictamen=d.estado_dictamen, fecha_dictamen=d.fecha_dictamen, observaciones=d.observaciones,
        )
        if d else None
    )

    return MuestraEstadoResponse(
        id_muestra=muestra.id_muestra, codigo_muestra=muestra.codigo_muestra, estado=muestra.estado,
        envios=envios, protocolos=protocolos, dictamen=dictamen,
    )


# ── Agente de detección automática de IR (RF-08, RF-09) ────────────────────
#
# A diferencia de los endpoints de arriba, estos son de uso interno del
# equipo (QA/admin logueados en LIMSS) -- requieren la autenticación normal
# de sesión, no la API key de eBR. Quedan bajo /api/integraciones porque
# conceptualmente es otra integración server-to-server (LIMSS <-> ERP GI_LX),
# aunque el consumidor acá sea la propia UI de LIMSS y no un sistema externo.

_SELECT_CONTROL = """
    SELECT c.*, s.nro_solicitud AS nro_solicitud_generada
    FROM lims_agente_control c
    LEFT JOIN lims_solicitudes_muestreo s ON s.id_solicitud = c.id_solicitud_generada
"""


def _logs_de_control(cursor, id_control: int) -> list[AgenteLogEntry]:
    cursor.execute(
        "SELECT * FROM lims_agente_log WHERE id_control = ? ORDER BY fecha_hora DESC",
        id_control,
    )
    return [
        AgenteLogEntry(
            id=l.id, fecha_hora=l.fecha_hora,
            datos_consultados=json.loads(l.datos_consultados) if l.datos_consultados else None,
            decision=l.decision, justificacion=l.justificacion, error_detalle=l.error_detalle,
        )
        for l in cursor.fetchall()
    ]


def _fila_a_evaluacion(cursor, row) -> AgenteEvaluacion:
    return AgenteEvaluacion(
        id=row.id, id_comprobante_erp=row.id_comprobante_erp, erp_idm21=row.erp_idm21,
        erp_codart=row.erp_codart, erp_codsar=row.erp_codsar, erp_desart=row.erp_desart,
        nro_ir=row.nro_ir, fecha_evaluacion=row.fecha_evaluacion,
        resultado=row.resultado, id_solicitud_generada=row.id_solicitud_generada,
        nro_solicitud_generada=row.nro_solicitud_generada, reintentos=row.reintentos,
        logs=_logs_de_control(cursor, row.id),
    )


@router.get("/agente/evaluaciones", response_model=list[AgenteEvaluacion])
def listar_evaluaciones_agente(
    id_comprobante_erp: Optional[int] = Query(None),
    resultado: Optional[str] = Query(
        None, pattern=r"^(solicitud_generada|ir_ya_tiene_solicitud|no_requiere_muestreo|subarticulo_no_configurado|error)$",
    ),
    desde: Optional[date] = Query(None, description="Fecha de evaluación desde (inclusive)"),
    hasta: Optional[date] = Query(None, description="Fecha de evaluación hasta (inclusive)"),
    user: dict = Depends(require_rol("qa", "admin")),
    conn: pyodbc.Connection = Depends(limss_db),
):
    cursor = conn.cursor()
    condiciones = []
    params: list = []
    if id_comprobante_erp is not None:
        condiciones.append("c.id_comprobante_erp = ?")
        params.append(id_comprobante_erp)
    if resultado:
        condiciones.append("c.resultado = ?")
        params.append(resultado)
    if desde:
        condiciones.append("c.fecha_evaluacion >= ?")
        params.append(datetime.combine(desde, datetime.min.time()))
    if hasta:
        condiciones.append("c.fecha_evaluacion < ?")
        params.append(datetime.combine(hasta + timedelta(days=1), datetime.min.time()))

    where = ("WHERE " + " AND ".join(condiciones)) if condiciones else ""
    cursor.execute(_SELECT_CONTROL + f" {where} ORDER BY c.fecha_evaluacion DESC", *params)
    controles = cursor.fetchall()
    return [_fila_a_evaluacion(cursor, c) for c in controles]


@router.post("/agente/reprocesar/{id_comprobante_erp}", response_model=AgenteEvaluacion)
def reprocesar_comprobante_agente(
    id_comprobante_erp: int,
    user: dict = Depends(require_rol("qa", "admin")),
    conn: pyodbc.Connection = Depends(limss_db),
):
    """Reevalúa un comprobante IR puntual (por N01Id), ignorando el control
    existente -- útil para casos de 'error' o cuando se acaba de configurar
    un subartículo que antes no estaba. evaluar_y_registrar_comprobante hace
    upsert por id_comprobante_erp, así que no importa si ya tenía fila."""
    agente_muestreo.evaluar_y_registrar_comprobante(id_comprobante_erp)

    cursor = conn.cursor()
    cursor.execute(_SELECT_CONTROL + " WHERE c.id_comprobante_erp = ?", id_comprobante_erp)
    row = cursor.fetchone()
    if not row:
        raise HTTPException(
            status_code=404,
            detail=f"No se encontró el comprobante N01Id={id_comprobante_erp} en el ERP, o no se pudo evaluar",
        )
    return _fila_a_evaluacion(cursor, row)


@router.post("/agente/ejecutar-ahora")
def ejecutar_ciclo_agente_ahora(
    user: dict = Depends(require_rol("qa", "admin")),
):
    """Dispara un ciclo de polling completo fuera del intervalo programado --
    pensado para pruebas manuales (ver 'Prueba manual al terminar' en la
    especificación del agente), no para uso rutinario."""
    return agente_muestreo.ciclo_polling()
