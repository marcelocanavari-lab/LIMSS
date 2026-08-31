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
# envíos Y de su Orden de Trabajo (Solicitud de Muestreo, si tiene) ya
# tienen resultado cargado -- no hay un estado guardado para eso, se calcula
# en el momento sobre las muestras 'en_análisis' que todavía no tienen
# dictamen. Se exige que exista AL MENOS un envío o una solicitud vinculada
# (si no, los NOT EXISTS de completitud son ciertos por vacuidad y la
# muestra aparecería como "pendiente" sin tener ningún análisis real
# cargado).
#
# Especificaciones sin NINGÚN ensayo de categoría con momento 'analisis'
# (solo checklist de categorías con momento 'muestreo' -- ver
# app/services/especificaciones.py) son un caso aparte: no
# hay envío ni protocolo posible, así que la condición de completitud de
# arriba (envíos + OT) no aplica -- para esas, alcanza con que el checklist
# de 'muestreo' (lims_resultados_muestreo) esté completo. La rama "normal"
# de abajo queda idéntica a como estaba antes de este cambio.

# Filtro de "apta para dictamen" -- reutilizado tal cual por el conteo del
# dashboard (dashboard.py) para no duplicar esta lógica de completitud.
# Incluye 'aprobado_sin_dictamen' además de 'en_análisis': esas muestras ya
# pasaron el filtro de completitud de abajo automáticamente al guardar
# resultados (ver guardar_resultados en resultados.py) y siguen esperando
# el dictamen FORMAL -- no hay que perderlas de la bandeja de QA solo
# porque ya se les dejó imprimir la etiqueta de Aprobado.
WHERE_MUESTRA_PENDIENTE_DICTAMEN = """
    m.estado IN ('en_análisis', 'aprobado_sin_dictamen')
      AND NOT EXISTS (
          SELECT 1 FROM lims_dictamenes d WHERE d.id_muestra = m.id_muestra
      )
      AND (
          (
              EXISTS (
                  SELECT 1 FROM lims_especificacion_ensayos see_a
                  INNER JOIN lims_categorias_ensayo cat_a ON cat_a.id_categoria = see_a.id_categoria
                  WHERE see_a.id_especificacion = m.id_especificacion AND cat_a.momento = 'analisis' AND see_a.activo = 1
              )
              AND NOT EXISTS (
                  SELECT 1 FROM lims_envios e
                  INNER JOIN lims_envio_ensayos ee ON ee.id_envio = e.id_envio
                  LEFT JOIN lims_resultados r ON r.id_espec_ensayo = ee.id_espec_ensayo
                    AND r.id_envio = ee.id_envio
                  WHERE e.id_muestra = m.id_muestra
                    AND r.id_resultado IS NULL
              )
              AND NOT EXISTS (
                  -- Ensayos de la Orden de Trabajo (filtrados por el laboratorio
                  -- elegido al crear la solicitud, igual que ensayos-para-orden).
                  -- Excluye los id_espec_ensayo que ya tienen resultado por la vía
                  -- de un envío de esta misma muestra: si la solicitud y un envío
                  -- coinciden en el mismo laboratorio (mismo id_espec_ensayo
                  -- asignado a ambos caminos), el resultado que ya llegó por envío
                  -- cuenta como cumplido -- no hay que cargarlo dos veces. Bug real
                  -- confirmado con la muestra SAMP-2026-0026 (id_muestra=87):
                  -- quedaba con el envío 100% completo pero nunca elegible para
                  -- Dictamen porque este NOT EXISTS exigía además un resultado en
                  -- lims_orden_trabajo_resultados para el mismo ensayo, tabla que
                  -- hoy no tiene ningún INSERT/UPDATE en todo el backend.
                  SELECT 1 FROM lims_solicitudes_muestreo s
                  INNER JOIN lims_especificacion_ensayos se ON se.id_especificacion = s.id_especificacion
                    AND se.id_laboratorio = s.id_laboratorio AND se.activo = 1
                  LEFT JOIN lims_orden_trabajo_resultados otr ON otr.id_espec_ensayo = se.id_espec_ensayo
                    AND otr.id_solicitud = s.id_solicitud
                  WHERE s.id_muestra = m.id_muestra
                    AND otr.id_resultado IS NULL
                    AND NOT EXISTS (
                        SELECT 1 FROM lims_envios e4
                        INNER JOIN lims_envio_ensayos ee4 ON ee4.id_envio = e4.id_envio
                          AND ee4.id_espec_ensayo = se.id_espec_ensayo
                        INNER JOIN lims_resultados r4 ON r4.id_espec_ensayo = ee4.id_espec_ensayo
                          AND r4.id_envio = ee4.id_envio
                        WHERE e4.id_muestra = m.id_muestra
                    )
              )
              AND (
                  EXISTS (SELECT 1 FROM lims_envios e3 WHERE e3.id_muestra = m.id_muestra)
                  OR EXISTS (SELECT 1 FROM lims_solicitudes_muestreo s3 WHERE s3.id_muestra = m.id_muestra)
              )
          )
          OR
          (
              m.id_especificacion IS NOT NULL
              AND NOT EXISTS (
                  SELECT 1 FROM lims_especificacion_ensayos see_b
                  INNER JOIN lims_categorias_ensayo cat_b ON cat_b.id_categoria = see_b.id_categoria
                  WHERE see_b.id_especificacion = m.id_especificacion AND cat_b.momento = 'analisis' AND see_b.activo = 1
              )
              AND EXISTS (
                  SELECT 1 FROM lims_especificacion_ensayos see_c
                  INNER JOIN lims_categorias_ensayo cat_c ON cat_c.id_categoria = see_c.id_categoria
                  WHERE see_c.id_especificacion = m.id_especificacion AND cat_c.momento = 'muestreo' AND see_c.activo = 1
              )
              AND NOT EXISTS (
                  SELECT 1 FROM lims_especificacion_ensayos see_d
                  INNER JOIN lims_categorias_ensayo cat_d ON cat_d.id_categoria = see_d.id_categoria
                  LEFT JOIN lims_resultados_muestreo rm ON rm.id_espec_ensayo = see_d.id_espec_ensayo AND rm.id_muestra = m.id_muestra
                  WHERE see_d.id_especificacion = m.id_especificacion AND cat_d.momento = 'muestreo' AND see_d.activo = 1
                    AND rm.id_resultado IS NULL
              )
          )
      )
"""


@router.get("/pendientes", response_model=list[DictamenPendienteResponse])
def listar_pendientes(
    user: dict = Depends(require_rol("qa", "admin")),
    conn: pyodbc.Connection = Depends(limss_db),
):
    cursor = conn.cursor()
    cursor.execute(
        f"""
        SELECT m.id_muestra, m.codigo_muestra, m.erp_CODART, m.erp_DESART, m.fecha_muestreo,
               (SELECT COUNT(*) FROM lims_envios e2 WHERE e2.id_muestra = m.id_muestra) AS cantidad_envios,
               (SELECT COUNT(*) FROM lims_resultados r
                WHERE r.id_muestra = m.id_muestra AND r.dentro_especificacion = 0)
               +
               (SELECT COUNT(*) FROM lims_orden_trabajo_resultados otr
                INNER JOIN lims_solicitudes_muestreo s2 ON s2.id_solicitud = otr.id_solicitud
                WHERE s2.id_muestra = m.id_muestra AND otr.dentro_especificacion = 0)
               +
               (SELECT COUNT(*) FROM lims_resultados_muestreo rm2
                WHERE rm2.id_muestra = m.id_muestra AND rm2.dentro_especificacion = 0) AS cantidad_oos
        FROM lims_muestras m
        WHERE {WHERE_MUESTRA_PENDIENTE_DICTAMEN}
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
    # 'aprobado_sin_dictamen' (ver guardar_resultados en resultados.py) sigue
    # necesitando el dictamen FORMAL más adelante -- ese estado solo evita
    # esperar el papeleo para poder imprimir la etiqueta e ir a por él
    # físicamente, no lo reemplaza. Se acepta como punto de partida acá
    # igual que 'en_análisis'.
    if muestra.estado not in ("en_análisis", "aprobado_sin_dictamen"):
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
