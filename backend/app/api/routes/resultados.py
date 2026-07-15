"""
Módulo II: Resultados Analíticos (REQ-RES-001 a 005).

Carga de resultados contra la especificación maestra con validación OOS, y
adjunto obligatorio del protocolo del laboratorio externo en PDF. Deja la
muestra en 'pendiente_dictamen', lista para el Módulo III (QA) — no implementado
todavía.
"""
import json
import os
from datetime import date
from typing import Optional

import pyodbc
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import ValidationError

from app.core.security import get_current_user, require_rol
from app.db.connections import limss_db
from app.schemas.resultados import (
    EnsayoParaCarga,
    GuardarResultadosResponse,
    MuestraParaCarga,
    ProtocoloResponse,
    ResultadoInput,
)
from app.services import audit, storage

router = APIRouter(prefix="/api/resultados", tags=["Resultados Analíticos"])


# ── Helpers internos ─────────────────────────────────────────────

def _obtener_muestra_para_carga(cursor, muestra) -> MuestraParaCarga:
    cursor.execute(
        """
        SELECT e.*, r.valor_numerico, r.valor_cualitativo, r.dentro_especificacion
        FROM lims_ensayos e
        LEFT JOIN lims_resultados r ON r.id_ensayo = e.id_ensayo AND r.id_muestra = ?
        WHERE e.id_especificacion = ?
        ORDER BY e.orden
        """,
        muestra.id_muestra, muestra.id_especificacion,
    )
    ensayos = [
        EnsayoParaCarga(
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

    cursor.execute("SELECT * FROM lims_protocolos WHERE id_muestra = ?", muestra.id_muestra)
    p = cursor.fetchone()
    protocolo = (
        ProtocoloResponse(
            id_protocolo=p.id_protocolo,
            nro_protocolo_ext=p.nro_protocolo_ext,
            fecha_emision=p.fecha_emision,
            pdf_nombre_original=p.pdf_nombre_original,
            fecha_carga=p.fecha_carga,
        )
        if p
        else None
    )

    return MuestraParaCarga(
        id_muestra=muestra.id_muestra,
        codigo_muestra=muestra.codigo_muestra,
        erp_CODART=muestra.erp_CODART,
        erp_DESART=muestra.erp_DESART,
        estado=muestra.estado,
        ensayos=ensayos,
        protocolo=protocolo,
    )


def _calcular_dentro_especificacion(ensayo_row, valor_numerico, valor_cualitativo) -> Optional[bool]:
    if ensayo_row.tipo_dato == "numerico":
        if valor_numerico is None:
            return None
        if ensayo_row.limite_inferior is not None and valor_numerico < float(ensayo_row.limite_inferior):
            return False
        if ensayo_row.limite_superior is not None and valor_numerico > float(ensayo_row.limite_superior):
            return False
        return True

    if not valor_cualitativo:
        return None
    return valor_cualitativo.strip() == (ensayo_row.valor_requerido or "").strip()


def _tiene_valor(r: ResultadoInput) -> bool:
    return r.valor_numerico is not None or bool((r.valor_cualitativo or "").strip())


# ── Endpoints ──────────────────────────────────────────────────────

@router.get("/muestras/{id_muestra}", response_model=MuestraParaCarga)
def detalle_para_carga(
    id_muestra: int,
    user: dict = Depends(get_current_user),
    conn: pyodbc.Connection = Depends(limss_db),
):
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM lims_muestras WHERE id_muestra = ?", id_muestra)
    muestra = cursor.fetchone()
    if not muestra:
        raise HTTPException(status_code=404, detail="Muestra no encontrada")
    if not muestra.id_especificacion:
        raise HTTPException(
            status_code=400,
            detail="La muestra no tiene una especificación vigente asociada. Cargá una en Datos Maestros primero.",
        )
    return _obtener_muestra_para_carga(cursor, muestra)


@router.post("/muestras/{id_muestra}/iniciar", response_model=MuestraParaCarga)
def iniciar_carga(
    id_muestra: int,
    user: dict = Depends(require_rol("analista_qc", "qa", "admin")),
    conn: pyodbc.Connection = Depends(limss_db),
):
    """REQ-RES-001: selecciona la muestra para carga y la pasa a 'en_carga_resultados'.
    Idempotente: si ya está en carga, no vuelve a transicionar (permite resumir)."""
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM lims_muestras WHERE id_muestra = ?", id_muestra)
    muestra = cursor.fetchone()
    if not muestra:
        raise HTTPException(status_code=404, detail="Muestra no encontrada")
    if muestra.estado not in ("en_transito", "en_carga_resultados"):
        raise HTTPException(
            status_code=409,
            detail=f"La muestra está en estado '{muestra.estado}', no se pueden cargar resultados",
        )
    if not muestra.id_especificacion:
        raise HTTPException(
            status_code=400,
            detail="La muestra no tiene una especificación vigente asociada. Cargá una en Datos Maestros primero.",
        )

    if muestra.estado == "en_transito":
        cursor.execute("UPDATE lims_muestras SET estado = 'en_carga_resultados' WHERE id_muestra = ?", id_muestra)
        audit.registrar(
            conn, entidad="muestra", accion="iniciar_carga_resultados",
            id_usuario=user["id_usuario"], id_entidad=id_muestra,
        )
        cursor.execute("SELECT * FROM lims_muestras WHERE id_muestra = ?", id_muestra)
        muestra = cursor.fetchone()

    return _obtener_muestra_para_carga(cursor, muestra)


@router.post("/muestras/{id_muestra}/guardar", response_model=GuardarResultadosResponse)
def guardar_resultados(
    id_muestra: int,
    resultados: str = Form(..., description="JSON de list[ResultadoInput]"),
    nro_protocolo_ext: str = Form(..., min_length=1, max_length=50),
    fecha_emision: date = Form(...),
    protocolo_pdf: UploadFile = File(...),
    user: dict = Depends(require_rol("analista_qc", "qa", "admin")),
    conn: pyodbc.Connection = Depends(limss_db),
):
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM lims_muestras WHERE id_muestra = ?", id_muestra)
    muestra = cursor.fetchone()
    if not muestra:
        raise HTTPException(status_code=404, detail="Muestra no encontrada")
    if muestra.estado != "en_carga_resultados":
        raise HTTPException(
            status_code=409,
            detail=f"La muestra está en estado '{muestra.estado}', no se pueden guardar resultados",
        )

    try:
        resultados_parsed = [ResultadoInput(**r) for r in json.loads(resultados)]
    except (json.JSONDecodeError, ValidationError, TypeError) as e:
        raise HTTPException(status_code=400, detail=f"Resultados inválidos: {e}")
    resultados_por_ensayo = {r.id_ensayo: r for r in resultados_parsed}

    cursor.execute("SELECT * FROM lims_ensayos WHERE id_especificacion = ?", muestra.id_especificacion)
    ensayos = {e.id_ensayo: e for e in cursor.fetchall()}

    # REQ-MAS-002: los ensayos marcados obligatorios deben tener valor.
    faltantes = [
        e.nombre_ensayo
        for e in ensayos.values()
        if e.obligatorio and not _tiene_valor(resultados_por_ensayo.get(e.id_ensayo, ResultadoInput(id_ensayo=e.id_ensayo)))
    ]
    if faltantes:
        raise HTTPException(status_code=400, detail=f"Faltan resultados obligatorios: {', '.join(faltantes)}")

    # REQ-RES-004: sin PDF válido no se guarda nada — falla rápido, antes de escribir resultados.
    ruta_pdf = storage.guardar_pdf_protocolo(protocolo_pdf, muestra.codigo_muestra)

    hay_oos = False
    for id_ensayo, r in resultados_por_ensayo.items():
        ensayo = ensayos.get(id_ensayo)
        if not ensayo or not _tiene_valor(r):
            continue

        dentro = _calcular_dentro_especificacion(ensayo, r.valor_numerico, r.valor_cualitativo)
        if dentro is False:
            hay_oos = True

        cursor.execute("SELECT 1 FROM lims_resultados WHERE id_muestra = ? AND id_ensayo = ?", id_muestra, id_ensayo)
        if cursor.fetchone():
            cursor.execute(
                """
                UPDATE lims_resultados
                SET valor_numerico = ?, valor_cualitativo = ?, dentro_especificacion = ?,
                    id_usuario_carga = ?, fecha_carga = GETDATE()
                WHERE id_muestra = ? AND id_ensayo = ?
                """,
                r.valor_numerico, r.valor_cualitativo, dentro, user["id_usuario"], id_muestra, id_ensayo,
            )
        else:
            cursor.execute(
                """
                INSERT INTO lims_resultados
                    (id_muestra, id_ensayo, valor_numerico, valor_cualitativo, dentro_especificacion, id_usuario_carga)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                id_muestra, id_ensayo, r.valor_numerico, r.valor_cualitativo, dentro, user["id_usuario"],
            )

    cursor.execute("SELECT 1 FROM lims_protocolos WHERE id_muestra = ?", id_muestra)
    if cursor.fetchone():
        cursor.execute(
            """
            UPDATE lims_protocolos
            SET nro_protocolo_ext = ?, fecha_emision = ?, pdf_path = ?, pdf_nombre_original = ?,
                id_usuario_carga = ?, fecha_carga = GETDATE()
            WHERE id_muestra = ?
            """,
            nro_protocolo_ext, fecha_emision, ruta_pdf, protocolo_pdf.filename, user["id_usuario"], id_muestra,
        )
    else:
        cursor.execute(
            """
            INSERT INTO lims_protocolos
                (id_muestra, nro_protocolo_ext, fecha_emision, pdf_path, pdf_nombre_original, id_usuario_carga)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            id_muestra, nro_protocolo_ext, fecha_emision, ruta_pdf, protocolo_pdf.filename, user["id_usuario"],
        )

    cursor.execute("UPDATE lims_muestras SET estado = 'pendiente_dictamen' WHERE id_muestra = ?", id_muestra)

    audit.registrar(
        conn, entidad="resultados", accion="guardar",
        id_usuario=user["id_usuario"], id_entidad=id_muestra,
        valor_nuevo={"hay_oos": hay_oos, "nro_protocolo_ext": nro_protocolo_ext},
    )

    return GuardarResultadosResponse(id_muestra=id_muestra, estado="pendiente_dictamen", hay_oos=hay_oos)


@router.get("/muestras/{id_muestra}/protocolo")
def descargar_protocolo(
    id_muestra: int,
    user: dict = Depends(get_current_user),
    conn: pyodbc.Connection = Depends(limss_db),
):
    cursor = conn.cursor()
    cursor.execute("SELECT pdf_path FROM lims_protocolos WHERE id_muestra = ?", id_muestra)
    row = cursor.fetchone()
    if not row or not row.pdf_path:
        raise HTTPException(status_code=404, detail="Protocolo no encontrado")

    ruta = storage.ruta_absoluta(row.pdf_path)
    if not os.path.exists(ruta):
        raise HTTPException(status_code=404, detail="El archivo no se encuentra en el servidor")

    return FileResponse(ruta, media_type="application/pdf", filename=os.path.basename(ruta))
