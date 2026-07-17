"""
Módulo III: Dictamen y Liberación (REQ-DEC-001 a 005).

QA decide el destino final del lote: aprobado, rechazado o cuarentena. Si hay
resultados OOS, exige justificación (REQ-DEC-002). Toda emisión de dictamen
requiere reintroducir el PIN (REQ-SEG-002 / REQ-DEC-004) -- se aplica a las
tres resoluciones, no solo a "aprobado" (confirmado con el usuario en el
build original de este módulo).

Acceso restringido a qa/admin en las tres rutas (bandeja, detalle y emisión) --
"Pantalla exclusiva para QA" según el URS de esta etapa.

lims_aprobaciones_lote (REQ-DEC-005, puente hacia el eBR) es append-only real:
cada dictamen INSERTa una fila nueva, nunca se actualiza una existente. Hasta
esta etapa tenía una restricción UNIQUE(nro_referencia, erp_CODART) que forzaba
upsert; se eliminó (ver migrations_aprobaciones_lote_append_only.sql) porque
contradecía el comentario original del script de creación. El eBR (no se
toca su código) toma siempre la fila más reciente por fecha_hora para un
(nro_referencia, erp_CODART) dado.
"""
import pyodbc
from fastapi import APIRouter, Depends, HTTPException

from app.core.security import require_rol, verify_pin
from app.db.connections import limss_db
from app.schemas.dictamenes import (
    DictamenCreate,
    DictamenDetalleResponse,
    DictamenPendienteResponse,
    DictamenResponse,
    EnsayoResultado,
    EnvioInfo,
    ProtocoloInfo,
)
from app.services import audit

router = APIRouter(prefix="/api/dictamen", tags=["Dictamen y Liberación"])


# ── PARTE A: Bandeja de pendientes (REQ-DEC-001) ──────────────────

@router.get("/pendientes", response_model=list[DictamenPendienteResponse])
def listar_pendientes(
    user: dict = Depends(require_rol("qa", "admin")),
    conn: pyodbc.Connection = Depends(limss_db),
):
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT m.id_muestra, m.codigo_muestra, m.erp_CODART, m.erp_DESART, m.fecha_muestreo,
               lab.nombre AS laboratorio_nombre,
               (SELECT COUNT(*) FROM lims_resultados r
                WHERE r.id_muestra = m.id_muestra AND r.dentro_especificacion = 0) AS cantidad_oos
        FROM lims_muestras m
        INNER JOIN lims_envios e ON e.id_muestra = m.id_muestra
        INNER JOIN lims_laboratorios lab ON lab.id_laboratorio = e.id_laboratorio
        WHERE m.estado = 'pendiente_dictamen'
        ORDER BY m.fecha_muestreo ASC
        """
    )
    return [
        DictamenPendienteResponse(
            id_muestra=r.id_muestra,
            codigo_muestra=r.codigo_muestra,
            erp_CODART=r.erp_CODART,
            erp_DESART=r.erp_DESART,
            fecha_muestreo=r.fecha_muestreo,
            laboratorio_nombre=r.laboratorio_nombre,
            cantidad_oos=r.cantidad_oos,
        )
        for r in cursor.fetchall()
    ]


# ── PARTE B: Visualización y dictamen (REQ-DEC-002 a 004) ─────────

@router.get("/{id_muestra}", response_model=DictamenDetalleResponse)
def detalle_para_dictamen(
    id_muestra: int,
    user: dict = Depends(require_rol("qa", "admin")),
    conn: pyodbc.Connection = Depends(limss_db),
):
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT m.*, u.nombre + ' ' + u.apellido AS usuario_muestreo_nombre
        FROM lims_muestras m
        INNER JOIN lims_usuarios u ON u.id_usuario = m.id_usuario_muestreo
        WHERE m.id_muestra = ?
        """,
        id_muestra,
    )
    muestra = cursor.fetchone()
    if not muestra:
        raise HTTPException(status_code=404, detail="Muestra no encontrada")

    cursor.execute(
        """
        SELECT e.id_ensayo, e.orden, e.nombre_ensayo, e.metodologia, e.tipo_dato,
               e.limite_inferior, e.limite_superior, e.unidad_medida, e.valor_requerido, e.obligatorio,
               r.valor_numerico, r.valor_cualitativo, r.dentro_especificacion
        FROM lims_ensayos e
        LEFT JOIN lims_resultados r ON r.id_ensayo = e.id_ensayo AND r.id_muestra = ?
        WHERE e.id_especificacion = ?
        ORDER BY e.orden
        """,
        id_muestra, muestra.id_especificacion,
    )
    ensayos = [
        EnsayoResultado(
            id_ensayo=e.id_ensayo,
            orden=e.orden,
            nombre_ensayo=e.nombre_ensayo,
            metodologia=e.metodologia,
            tipo_dato=e.tipo_dato,
            limite_inferior=float(e.limite_inferior) if e.limite_inferior is not None else None,
            limite_superior=float(e.limite_superior) if e.limite_superior is not None else None,
            unidad_medida=e.unidad_medida,
            valor_requerido=e.valor_requerido,
            obligatorio=bool(e.obligatorio),
            valor_numerico=float(e.valor_numerico) if e.valor_numerico is not None else None,
            valor_cualitativo=e.valor_cualitativo,
            dentro_especificacion=bool(e.dentro_especificacion) if e.dentro_especificacion is not None else None,
        )
        for e in cursor.fetchall()
    ]
    hay_oos = any(en.dentro_especificacion is False for en in ensayos)

    cursor.execute(
        """
        SELECT TOP 1 nro_protocolo_ext, fecha_emision, pdf_nombre_original
        FROM lims_protocolos WHERE id_muestra = ? ORDER BY fecha_carga DESC
        """,
        id_muestra,
    )
    p = cursor.fetchone()
    protocolo = (
        ProtocoloInfo(
            nro_protocolo_ext=p.nro_protocolo_ext,
            fecha_emision=p.fecha_emision,
            pdf_nombre_original=p.pdf_nombre_original,
        )
        if p
        else None
    )

    cursor.execute(
        """
        SELECT e.id_envio, e.fecha_despacho, lab.nombre AS laboratorio_nombre,
               t.codigo AS testigo_codigo, t.nombre AS testigo_nombre
        FROM lims_envios e
        INNER JOIN lims_laboratorios lab ON lab.id_laboratorio = e.id_laboratorio
        LEFT JOIN lims_testigos t ON t.id_testigo = e.id_testigo
        WHERE e.id_muestra = ?
        """,
        id_muestra,
    )
    ev = cursor.fetchone()
    envio = (
        EnvioInfo(
            id_envio=ev.id_envio,
            laboratorio_nombre=ev.laboratorio_nombre,
            fecha_despacho=ev.fecha_despacho,
            testigo_codigo=ev.testigo_codigo,
            testigo_nombre=ev.testigo_nombre,
        )
        if ev
        else None
    )

    return DictamenDetalleResponse(
        id_muestra=muestra.id_muestra,
        codigo_muestra=muestra.codigo_muestra,
        erp_CODART=muestra.erp_CODART,
        erp_DESART=muestra.erp_DESART,
        tipo_referencia=muestra.tipo_referencia,
        nro_referencia=muestra.nro_referencia,
        fecha_muestreo=muestra.fecha_muestreo,
        usuario_muestreo_nombre=muestra.usuario_muestreo_nombre,
        estado=muestra.estado,
        ensayos=ensayos,
        hay_oos=hay_oos,
        protocolo=protocolo,
        envio=envio,
    )


@router.post("/{id_muestra}", response_model=DictamenResponse, status_code=201)
def emitir_dictamen(
    id_muestra: int,
    body: DictamenCreate,
    user: dict = Depends(require_rol("qa", "admin")),
    conn: pyodbc.Connection = Depends(limss_db),
):
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM lims_muestras WHERE id_muestra = ?", id_muestra)
    muestra = cursor.fetchone()
    if not muestra:
        raise HTTPException(status_code=404, detail="Muestra no encontrada")
    if muestra.estado != "pendiente_dictamen":
        raise HTTPException(
            status_code=409,
            detail=f"La muestra está en estado '{muestra.estado}', no está pendiente de dictamen",
        )

    # REQ-SEG-002 / REQ-DEC-004: firma electrónica -- reintroducir el PIN.
    cursor.execute("SELECT pin_hash FROM lims_usuarios WHERE id_usuario = ?", user["id_usuario"])
    fila_usuario = cursor.fetchone()
    if not fila_usuario or not verify_pin(body.pin_confirmacion, fila_usuario.pin_hash):
        raise HTTPException(status_code=401, detail="PIN incorrecto")

    # REQ-DEC-002: si hay algún resultado OOS, la justificación es obligatoria.
    cursor.execute(
        "SELECT COUNT(*) AS n FROM lims_resultados WHERE id_muestra = ? AND dentro_especificacion = 0",
        id_muestra,
    )
    hay_oos = cursor.fetchone().n > 0
    if hay_oos and not (body.justificacion_oos or "").strip():
        raise HTTPException(
            status_code=400,
            detail="Hay resultados fuera de especificación (OOS): la justificación es obligatoria",
        )

    cursor.execute(
        """
        INSERT INTO lims_dictamenes
            (id_muestra, estado_dictamen, justificacion_oos, observaciones, id_usuario_qa)
        VALUES (?, ?, ?, ?, ?)
        """,
        id_muestra, body.estado_dictamen, body.justificacion_oos, body.observaciones, user["id_usuario"],
    )
    cursor.execute("SELECT @@IDENTITY AS id")
    id_dictamen = int(cursor.fetchone().id)

    estado_anterior = muestra.estado
    cursor.execute("UPDATE lims_muestras SET estado = ? WHERE id_muestra = ?", body.estado_dictamen, id_muestra)

    # PARTE C / REQ-DEC-005: puente hacia el eBR -- append-only, siempre INSERT.
    cursor.execute(
        """
        INSERT INTO lims_aprobaciones_lote (nro_referencia, erp_CODART, estado, id_dictamen)
        VALUES (?, ?, ?, ?)
        """,
        muestra.nro_referencia, muestra.erp_CODART, body.estado_dictamen, id_dictamen,
    )

    audit.registrar(
        conn, entidad="muestra", accion="dictaminar",
        id_usuario=user["id_usuario"], id_entidad=id_muestra,
        valor_anterior={"estado": estado_anterior}, valor_nuevo={"estado": body.estado_dictamen},
        motivo=body.justificacion_oos,
    )
    audit.registrar(
        conn, entidad="dictamen", accion="emitir",
        id_usuario=user["id_usuario"], id_entidad=id_dictamen,
        valor_nuevo={
            "id_muestra": id_muestra,
            "estado_dictamen": body.estado_dictamen,
            "justificacion_oos": body.justificacion_oos,
            "observaciones": body.observaciones,
        },
    )

    cursor.execute("SELECT * FROM lims_dictamenes WHERE id_dictamen = ?", id_dictamen)
    row = cursor.fetchone()
    return DictamenResponse(
        id_dictamen=row.id_dictamen,
        id_muestra=row.id_muestra,
        estado_dictamen=row.estado_dictamen,
        justificacion_oos=row.justificacion_oos,
        observaciones=row.observaciones,
        id_usuario_qa=row.id_usuario_qa,
        fecha_dictamen=row.fecha_dictamen,
    )
