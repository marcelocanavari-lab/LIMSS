"""
Módulo III: Dictamen y Liberación (REQ-DEC-001 a 005).

QA decide el destino final del lote: aprobado, rechazado o cuarentena. Si hay
resultados OOS, exige justificación (REQ-DEC-002). Toda emisión de dictamen
requiere reintroducir el PIN (REQ-SEG-002 / REQ-DEC-004) -- se aplica a las tres
resoluciones, no solo a "aprobado": REQ-SEG-002 exige reautenticación para
"dictamen final" en general, y REQ-DEC-004 remarca el caso de aprobación como el
más crítico, sin aislarlo de los demás (confirmado con el usuario).

Al emitir el dictamen se actualiza lims_aprobaciones_lote (REQ-DEC-005, el puente
hacia el eBR). Esa tabla tiene una restricción UNIQUE(nro_referencia, erp_CODART)
que contradice el comentario del propio script de creación ("no se borra, se
agrega una fila nueva si cambia") -- con DELETE prohibido (REQ-SEG-003) y esa
UNIQUE, la única forma coherente de sostenerla es con upsert (actualiza la fila
existente si ya hay una para esa referencia+material, inserta si no). El
historial completo de dictámenes queda preservado en lims_dictamenes (una fila
por muestra, nunca se pisa) y en lims_audit_trail -- lims_aprobaciones_lote
funciona como "estado vigente del lote" para el eBR, no como bitácora histórica.

nro_referencia reemplaza a erp_nro_ir como clave del puente: Materia Prima usa
el IR, Granel/Semi-Elaborado/Producto Terminado usan su número de lote interno
-- ambos casos quedan cubiertos con la misma columna.
"""
import pyodbc
from fastapi import APIRouter, Depends, HTTPException

from app.core.security import get_current_user, require_rol, verify_pin
from app.db.connections import limss_db
from app.schemas.dictamenes import DictamenCreate, DictamenResponse
from app.services import audit

router = APIRouter(prefix="/api/dictamenes", tags=["Dictamen y Liberación"])


def _fila_a_dictamen(row) -> DictamenResponse:
    return DictamenResponse(
        id_dictamen=row.id_dictamen,
        id_muestra=row.id_muestra,
        estado_dictamen=row.estado_dictamen,
        justificacion_oos=row.justificacion_oos,
        observaciones=row.observaciones,
        id_usuario_qa=row.id_usuario_qa,
        fecha_dictamen=row.fecha_dictamen,
    )


@router.get("/muestras/{id_muestra}", response_model=DictamenResponse)
def obtener_dictamen(
    id_muestra: int,
    user: dict = Depends(get_current_user),
    conn: pyodbc.Connection = Depends(limss_db),
):
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM lims_dictamenes WHERE id_muestra = ?", id_muestra)
    row = cursor.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Esta muestra todavía no tiene dictamen")
    return _fila_a_dictamen(row)


@router.post("/muestras/{id_muestra}", response_model=DictamenResponse, status_code=201)
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
    if not fila_usuario or not verify_pin(body.pin, fila_usuario.pin_hash):
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

    cursor.execute("UPDATE lims_muestras SET estado = ? WHERE id_muestra = ?", body.estado_dictamen, id_muestra)

    # REQ-DEC-005: puente hacia el eBR -- upsert por (nro_referencia, erp_CODART).
    cursor.execute(
        "SELECT 1 FROM lims_aprobaciones_lote WHERE nro_referencia = ? AND erp_CODART = ?",
        muestra.nro_referencia, muestra.erp_CODART,
    )
    if cursor.fetchone():
        cursor.execute(
            """
            UPDATE lims_aprobaciones_lote
            SET estado = ?, id_dictamen = ?, fecha_hora = GETDATE()
            WHERE nro_referencia = ? AND erp_CODART = ?
            """,
            body.estado_dictamen, id_dictamen, muestra.nro_referencia, muestra.erp_CODART,
        )
    else:
        cursor.execute(
            """
            INSERT INTO lims_aprobaciones_lote (nro_referencia, erp_CODART, estado, id_dictamen)
            VALUES (?, ?, ?, ?)
            """,
            muestra.nro_referencia, muestra.erp_CODART, body.estado_dictamen, id_dictamen,
        )

    audit.registrar(
        conn, entidad="dictamen", accion="emitir",
        id_usuario=user["id_usuario"], id_entidad=id_dictamen,
        valor_nuevo={"id_muestra": id_muestra, "estado_dictamen": body.estado_dictamen},
        motivo=body.justificacion_oos,
    )

    cursor.execute("SELECT * FROM lims_dictamenes WHERE id_dictamen = ?", id_dictamen)
    return _fila_a_dictamen(cursor.fetchone())
