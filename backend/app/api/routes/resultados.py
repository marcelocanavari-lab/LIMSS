"""
Módulo II: Resultados Analíticos (REQ-RES-001 a 005).

Carga de resultados analíticos: registro de datos sin validación ni alertas
en tiempo real (el dictamen -- cumple / no cumple / cuarentena -- lo emite QA
después, en el Módulo III). Se calcula y persiste `dentro_especificacion` por
ensayo al guardar, para que el Módulo III lo consuma, pero no se muestra al
analista durante la carga. Incluye adjunto obligatorio del protocolo del
laboratorio externo en PDF.

La carga es POR ENVÍO, no por muestra: una muestra puede tener varios envíos
(a distintos laboratorios), cada uno con sus propios ensayos y su propio
protocolo -- por eso este router vive bajo /api/envios/{id_envio}/... en vez
de /api/muestras/{id_muestra}/... Guardar resultados de un envío ya NO cambia
el estado de la muestra (queda en 'en_análisis'): la aptitud para dictamen se
calcula dinámicamente en el Módulo III, no se guarda como transición de estado.
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
    EnvioParaCarga,
    EnvioPendienteResultados,
    GuardarResultadosResponse,
    ProtocoloResponse,
    ResultadoInput,
)
from app.services import audit, storage

router = APIRouter(prefix="/api/envios", tags=["Resultados Analíticos"])


# ── Helpers internos ─────────────────────────────────────────────

def _obtener_envio_o_404(cursor, id_envio: int):
    cursor.execute(
        """
        SELECT e.*, m.codigo_muestra, m.erp_CODART, m.erp_DESART, m.estado AS estado_muestra,
               lab.nombre AS laboratorio_nombre
        FROM lims_envios e
        INNER JOIN lims_muestras m ON m.id_muestra = e.id_muestra
        INNER JOIN lims_laboratorios lab ON lab.id_laboratorio = e.id_laboratorio
        WHERE e.id_envio = ?
        """,
        id_envio,
    )
    envio = cursor.fetchone()
    if not envio:
        raise HTTPException(status_code=404, detail="Envío no encontrado")
    return envio


def _obtener_envio_para_carga(cursor, envio) -> EnvioParaCarga:
    cursor.execute(
        """
        SELECT se.id_espec_ensayo, se.orden, m.nombre_ensayo, se.metodologia, se.tipo_dato,
               se.limite_inferior, se.limite_superior, se.unidad_medida, se.valor_requerido, se.obligatorio,
               r.valor_numerico, r.valor_cualitativo, r.dentro_especificacion
        FROM lims_envio_ensayos ee
        INNER JOIN lims_especificacion_ensayos se ON se.id_espec_ensayo = ee.id_espec_ensayo
        INNER JOIN lims_ensayos_maestro m ON m.id_ensayo_maestro = se.id_ensayo_maestro
        LEFT JOIN lims_resultados r ON r.id_espec_ensayo = ee.id_espec_ensayo AND r.id_envio = ee.id_envio
        WHERE ee.id_envio = ?
        ORDER BY se.orden
        """,
        envio.id_envio,
    )
    ensayos = [
        EnsayoParaCarga(
            id_espec_ensayo=e.id_espec_ensayo,
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

    cursor.execute("SELECT * FROM lims_protocolos WHERE id_envio = ? ORDER BY fecha_carga DESC", envio.id_envio)
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

    return EnvioParaCarga(
        id_envio=envio.id_envio,
        id_muestra=envio.id_muestra,
        codigo_muestra=envio.codigo_muestra,
        erp_CODART=envio.erp_CODART,
        erp_DESART=envio.erp_DESART,
        laboratorio_nombre=envio.laboratorio_nombre,
        estado_muestra=envio.estado_muestra,
        ensayos=ensayos,
        protocolo=protocolo,
    )


def _calcular_dentro_especificacion(ensayo_row, valor_numerico, valor_cualitativo) -> Optional[bool]:
    if ensayo_row.tipo_dato == "numerico":
        if valor_numerico is None:
            return None
        if ensayo_row.limite_inferior is None or ensayo_row.limite_superior is None:
            return None
        return float(ensayo_row.limite_inferior) <= valor_numerico <= float(ensayo_row.limite_superior)

    if not valor_cualitativo or not valor_cualitativo.strip():
        return None
    return valor_cualitativo.strip().lower() == "cumple"


def _tiene_valor(r: ResultadoInput) -> bool:
    return r.valor_numerico is not None or bool((r.valor_cualitativo or "").strip())


# ── Endpoints ──────────────────────────────────────────────────────

@router.get("/pendientes", response_model=list[EnvioPendienteResultados])
def listar_pendientes_resultados(
    user: dict = Depends(require_rol("analista_qc", "qa", "admin")),
    conn: pyodbc.Connection = Depends(limss_db),
):
    """Bandeja de Carga de Resultados (pantalla independiente de Envío de
    Muestras): envíos que ya están confirmados y todavía tienen algún ensayo
    sin resultado cargado."""
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT e.id_envio, e.fecha_despacho, m.codigo_muestra, m.erp_DESART,
               lab.nombre AS laboratorio_nombre, rem.nro_remito_interno,
               (SELECT COUNT(*) FROM lims_envio_ensayos ee
                LEFT JOIN lims_resultados r ON r.id_espec_ensayo = ee.id_espec_ensayo AND r.id_envio = ee.id_envio
                WHERE ee.id_envio = e.id_envio AND r.id_resultado IS NULL) AS ensayos_pendientes
        FROM lims_envios e
        INNER JOIN lims_muestras m ON m.id_muestra = e.id_muestra
        INNER JOIN lims_laboratorios lab ON lab.id_laboratorio = e.id_laboratorio
        OUTER APPLY (
            SELECT TOP 1 nro_remito_interno FROM lims_remitos r2
            WHERE r2.id_envio = e.id_envio ORDER BY r2.id_remito DESC
        ) rem
        WHERE m.estado = 'en_análisis'
          AND EXISTS (
              SELECT 1 FROM lims_envio_ensayos ee
              LEFT JOIN lims_resultados r ON r.id_espec_ensayo = ee.id_espec_ensayo AND r.id_envio = ee.id_envio
              WHERE ee.id_envio = e.id_envio AND r.id_resultado IS NULL
          )
        ORDER BY e.fecha_despacho ASC
        """
    )
    return [
        EnvioPendienteResultados(
            id_envio=r.id_envio,
            nro_remito_interno=r.nro_remito_interno,
            codigo_muestra=r.codigo_muestra,
            erp_DESART=r.erp_DESART,
            laboratorio_nombre=r.laboratorio_nombre,
            ensayos_pendientes=r.ensayos_pendientes,
            fecha_despacho=r.fecha_despacho,
        )
        for r in cursor.fetchall()
    ]


@router.get("/{id_envio}/resultados", response_model=EnvioParaCarga)
def detalle_para_carga(
    id_envio: int,
    user: dict = Depends(get_current_user),
    conn: pyodbc.Connection = Depends(limss_db),
):
    cursor = conn.cursor()
    envio = _obtener_envio_o_404(cursor, id_envio)
    return _obtener_envio_para_carga(cursor, envio)


@router.post("/{id_envio}/resultados", response_model=GuardarResultadosResponse)
def guardar_resultados(
    id_envio: int,
    resultados: str = Form(..., description="JSON de list[ResultadoInput]"),
    nro_protocolo_ext: str = Form(..., min_length=1, max_length=50),
    fecha_emision: date = Form(...),
    protocolo_pdf: UploadFile = File(...),
    user: dict = Depends(require_rol("analista_qc", "qa", "admin")),
    conn: pyodbc.Connection = Depends(limss_db),
):
    cursor = conn.cursor()
    envio = _obtener_envio_o_404(cursor, id_envio)
    if envio.estado_muestra != "en_análisis":
        raise HTTPException(
            status_code=409,
            detail=f"La muestra está en estado '{envio.estado_muestra}', no se pueden guardar resultados",
        )

    try:
        resultados_parsed = [ResultadoInput(**r) for r in json.loads(resultados)]
    except (json.JSONDecodeError, ValidationError, TypeError) as e:
        raise HTTPException(status_code=400, detail=f"Resultados inválidos: {e}")
    resultados_por_ensayo = {r.id_espec_ensayo: r for r in resultados_parsed}

    cursor.execute(
        """
        SELECT se.*, m.nombre_ensayo
        FROM lims_envio_ensayos ee
        INNER JOIN lims_especificacion_ensayos se ON se.id_espec_ensayo = ee.id_espec_ensayo
        INNER JOIN lims_ensayos_maestro m ON m.id_ensayo_maestro = se.id_ensayo_maestro
        WHERE ee.id_envio = ?
        """,
        id_envio,
    )
    ensayos = {e.id_espec_ensayo: e for e in cursor.fetchall()}

    # REQ-MAS-002: los ensayos marcados obligatorios deben tener valor -- solo
    # se exigen los de ESTE envío, no los de toda la especificación.
    faltantes = [
        e.nombre_ensayo
        for e in ensayos.values()
        if e.obligatorio and not _tiene_valor(resultados_por_ensayo.get(e.id_espec_ensayo, ResultadoInput(id_espec_ensayo=e.id_espec_ensayo)))
    ]
    if faltantes:
        raise HTTPException(status_code=400, detail=f"Faltan resultados obligatorios: {', '.join(faltantes)}")

    # REQ-RES-004: sin PDF válido no se guarda nada — falla rápido, antes de escribir resultados.
    ruta_pdf = storage.guardar_pdf_protocolo(protocolo_pdf, envio.codigo_muestra)

    hay_oos = False
    for id_espec_ensayo, r in resultados_por_ensayo.items():
        ensayo = ensayos.get(id_espec_ensayo)
        if not ensayo or not _tiene_valor(r):
            continue

        dentro = _calcular_dentro_especificacion(ensayo, r.valor_numerico, r.valor_cualitativo)
        if dentro is False:
            hay_oos = True

        cursor.execute("SELECT 1 FROM lims_resultados WHERE id_envio = ? AND id_espec_ensayo = ?", id_envio, id_espec_ensayo)
        if cursor.fetchone():
            cursor.execute(
                """
                UPDATE lims_resultados
                SET valor_numerico = ?, valor_cualitativo = ?, dentro_especificacion = ?,
                    id_usuario_carga = ?, fecha_carga = GETDATE()
                WHERE id_envio = ? AND id_espec_ensayo = ?
                """,
                r.valor_numerico, r.valor_cualitativo, dentro, user["id_usuario"], id_envio, id_espec_ensayo,
            )
        else:
            cursor.execute(
                """
                INSERT INTO lims_resultados
                    (id_muestra, id_envio, id_espec_ensayo, valor_numerico, valor_cualitativo, dentro_especificacion, id_usuario_carga)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                envio.id_muestra, id_envio, id_espec_ensayo, r.valor_numerico, r.valor_cualitativo, dentro, user["id_usuario"],
            )

    cursor.execute("SELECT 1 FROM lims_protocolos WHERE id_envio = ?", id_envio)
    if cursor.fetchone():
        cursor.execute(
            """
            UPDATE lims_protocolos
            SET nro_protocolo_ext = ?, fecha_emision = ?, pdf_path = ?, pdf_nombre_original = ?,
                id_usuario_carga = ?, fecha_carga = GETDATE()
            WHERE id_envio = ?
            """,
            nro_protocolo_ext, str(fecha_emision), ruta_pdf, protocolo_pdf.filename, user["id_usuario"], id_envio,
        )
    else:
        cursor.execute(
            """
            INSERT INTO lims_protocolos
                (id_muestra, id_envio, nro_protocolo_ext, fecha_emision, pdf_path, pdf_nombre_original, id_usuario_carga)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            envio.id_muestra, id_envio, nro_protocolo_ext, str(fecha_emision), ruta_pdf, protocolo_pdf.filename, user["id_usuario"],
        )

    audit.registrar(
        conn, entidad="resultados", accion="guardar",
        id_usuario=user["id_usuario"], id_entidad=id_envio,
        valor_nuevo={"hay_oos": hay_oos, "nro_protocolo_ext": nro_protocolo_ext},
    )

    return GuardarResultadosResponse(id_envio=id_envio, hay_oos=hay_oos)


@router.get("/{id_envio}/protocolo")
def descargar_protocolo(
    id_envio: int,
    user: dict = Depends(get_current_user),
    conn: pyodbc.Connection = Depends(limss_db),
):
    cursor = conn.cursor()
    cursor.execute("SELECT pdf_path FROM lims_protocolos WHERE id_envio = ?", id_envio)
    row = cursor.fetchone()
    if not row or not row.pdf_path:
        raise HTTPException(status_code=404, detail="Protocolo no encontrado")

    ruta = storage.ruta_absoluta(row.pdf_path)
    if not os.path.exists(ruta):
        raise HTTPException(status_code=404, detail="El archivo no se encuentra en el servidor")

    return FileResponse(ruta, media_type="application/pdf", filename=os.path.basename(ruta))
