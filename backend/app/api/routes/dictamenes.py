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
)
from app.services import audit
from app.services.recorrido import construir_recorrido

router = APIRouter(prefix="/api/dictamen", tags=["Dictamen y Liberación"])


# ── PARTE A: Bandeja de pendientes (REQ-DEC-001) ──────────────────
#
# Una muestra es apta para dictamen cuando TODOS los ensayos de TODOS sus
# envíos ya tienen resultado cargado -- no hay un estado guardado para eso,
# se calcula en el momento (NOT EXISTS: ningún envío con un ensayo sin
# resultado) sobre las muestras 'en_análisis' que todavía no tienen dictamen.

@router.get("/pendientes", response_model=list[DictamenPendienteResponse])
def listar_pendientes(
    user: dict = Depends(require_rol("qa", "admin")),
    conn: pyodbc.Connection = Depends(limss_db),
):
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT m.id_muestra, m.codigo_muestra, m.erp_CODART, m.erp_DESART, m.fecha_muestreo,
               (SELECT COUNT(*) FROM lims_envios e2 WHERE e2.id_muestra = m.id_muestra) AS cantidad_envios,
               (SELECT COUNT(*) FROM lims_resultados r
                WHERE r.id_muestra = m.id_muestra AND r.dentro_especificacion = 0) AS cantidad_oos
        FROM lims_muestras m
        WHERE NOT EXISTS (
            SELECT 1 FROM lims_envios e
            INNER JOIN lims_envio_ensayos ee ON ee.id_envio = e.id_envio
            LEFT JOIN lims_resultados r ON r.id_espec_ensayo = ee.id_espec_ensayo
              AND r.id_envio = ee.id_envio
            WHERE e.id_muestra = m.id_muestra
              AND r.id_resultado IS NULL
        )
        AND m.estado = 'en_análisis'
        AND NOT EXISTS (
            SELECT 1 FROM lims_dictamenes d WHERE d.id_muestra = m.id_muestra
        )
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
            cantidad_envios=r.cantidad_envios,
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
    recorrido = construir_recorrido(cursor, id_muestra)
    if not recorrido:
        raise HTTPException(status_code=404, detail="Muestra no encontrada")
    return recorrido


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
    if muestra.estado != "en_análisis":
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
