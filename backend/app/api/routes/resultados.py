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

from app.api.routes import empaque_ia
from app.core.security import get_current_user, require_rol
from app.db.connections import limss_db
from app.schemas.empaque_ia import CompararEtiquetaResponse
from app.schemas.resultados import (
    EnsayoParaCarga,
    EnvioParaCarga,
    EnvioPendienteResultados,
    GuardarResultadosResponse,
    ProtocoloResponse,
    ResultadoInput,
)
from app.services import audit, comparacion_empaque_ia, storage

router = APIRouter(prefix="/api/envios", tags=["Resultados Analíticos"])


# ── Helpers internos ─────────────────────────────────────────────

def _obtener_envio_o_404(cursor, id_envio: int):
    cursor.execute(
        """
        SELECT e.*, m.codigo_muestra, m.erp_CODART, m.erp_DESART, m.estado AS estado_muestra,
               m.tipo_material AS tipo_material_muestra, lab.nombre AS laboratorio_nombre
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
               se.limite_inferior, se.limite_superior, se.unidad_medida, se.valor_requerido,
               se.especificacion_texto, se.obligatorio,
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
            especificacion_texto=e.especificacion_texto,
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
        tipo_material=envio.tipo_material_muestra,
        ensayos=ensayos,
        protocolo=protocolo,
        observacion_ia=envio.observacion_ia,
        tiene_imagen_comparacion=envio.imagen_comparacion_path is not None,
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


def _guardar_protocolo(cursor, envio, nro_protocolo_ext: str, fecha_emision: date, protocolo_pdf: UploadFile, id_usuario: int) -> ProtocoloResponse:
    """Alta/reemplazo del protocolo de un envío -- un protocolo por envío
    (upsert por id_envio). Usado tanto por el guardado conjunto en
    guardar_resultados (si se manda protocolo en la misma request) como por
    el endpoint dedicado guardar_protocolo (subida por separado, cuando el
    protocolo llega después que los resultados)."""
    ruta_pdf = storage.guardar_pdf_protocolo(protocolo_pdf, envio.codigo_muestra)

    cursor.execute("SELECT id_protocolo FROM lims_protocolos WHERE id_envio = ?", envio.id_envio)
    existente = cursor.fetchone()
    if existente:
        cursor.execute(
            """
            UPDATE lims_protocolos
            SET nro_protocolo_ext = ?, fecha_emision = ?, pdf_path = ?, pdf_nombre_original = ?,
                id_usuario_carga = ?, fecha_carga = GETDATE()
            WHERE id_envio = ?
            """,
            nro_protocolo_ext, str(fecha_emision), ruta_pdf, protocolo_pdf.filename, id_usuario, envio.id_envio,
        )
        id_protocolo = existente.id_protocolo
    else:
        cursor.execute(
            """
            INSERT INTO lims_protocolos
                (id_muestra, id_envio, nro_protocolo_ext, fecha_emision, pdf_path, pdf_nombre_original, id_usuario_carga)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            envio.id_muestra, envio.id_envio, nro_protocolo_ext, str(fecha_emision), ruta_pdf, protocolo_pdf.filename, id_usuario,
        )
        cursor.execute("SELECT @@IDENTITY AS id")
        id_protocolo = int(cursor.fetchone().id)

    cursor.execute("SELECT fecha_carga FROM lims_protocolos WHERE id_protocolo = ?", id_protocolo)
    fecha_carga = cursor.fetchone().fecha_carga

    return ProtocoloResponse(
        id_protocolo=id_protocolo,
        nro_protocolo_ext=nro_protocolo_ext,
        fecha_emision=fecha_emision,
        pdf_nombre_original=protocolo_pdf.filename,
        fecha_carga=fecha_carga,
    )


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
                WHERE ee.id_envio = e.id_envio AND r.id_resultado IS NULL) AS ensayos_pendientes,
               (SELECT COUNT(*) FROM lims_envio_ensayos ee WHERE ee.id_envio = e.id_envio) AS total_ensayos
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
            total_ensayos=r.total_ensayos,
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
    resultados: str = Form(..., description="JSON de list[ResultadoInput] -- pueden venir solo algunos con valor, el resto se ignora (guardado parcial)"),
    nro_protocolo_ext: Optional[str] = Form(None, min_length=1, max_length=50),
    fecha_emision: Optional[date] = Form(None),
    protocolo_pdf: Optional[UploadFile] = File(None),
    imagen_comparacion_path: Optional[str] = Form(
        None, description="Resultado provisorio de POST .../comparar-etiqueta, si se corrió -- recién se persiste acá"
    ),
    observacion_ia: Optional[str] = Form(None),
    user: dict = Depends(require_rol("analista_qc", "qa", "admin")),
    conn: pyodbc.Connection = Depends(limss_db),
):
    """Guardado parcial: cada ensayo con valor se guarda (INSERT/UPDATE
    independiente por id_espec_ensayo), los que vienen sin valor simplemente
    no se tocan -- no hace falta completar todos los ensayos del envío en la
    misma llamada, el laboratorio suele informar resultados de a poco. La
    completitud (todos los ensayos con valor) recién se exige más adelante,
    al habilitar el dictamen (ver WHERE_MUESTRA_PENDIENTE_DICTAMEN en
    dictamenes.py) -- acá no se bloquea nada por ensayos faltantes.

    El protocolo del laboratorio es independiente de esto: es opcional en
    esta misma llamada (si ya se tiene a mano, se puede mandar junto) pero
    también se puede cargar después, sin resultados, vía POST
    .../protocolo -- ver guardar_protocolo más abajo."""
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

    if protocolo_pdf is not None and (not nro_protocolo_ext or not fecha_emision):
        raise HTTPException(
            status_code=400,
            detail="Si se adjunta el protocolo hacen falta también el número de protocolo y la fecha de emisión",
        )

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

    if protocolo_pdf is not None:
        _guardar_protocolo(cursor, envio, nro_protocolo_ext, fecha_emision, protocolo_pdf, user["id_usuario"])

    # Comparación de etiqueta (Material de Empaque): provisoria hasta acá --
    # POST .../comparar-etiqueta ya no escribe en lims_envios (ver ese
    # endpoint), así que recién queda persistida en este mismo guardado.
    # Si no se corrió ninguna comparación en esta sesión de carga, no se
    # manda nada y no se toca la fila (no se fuerza a NULL).
    if imagen_comparacion_path is not None:
        cursor.execute(
            "UPDATE lims_envios SET imagen_comparacion_path = ?, observacion_ia = ? WHERE id_envio = ?",
            imagen_comparacion_path, observacion_ia, id_envio,
        )

    audit.registrar(
        conn, entidad="resultados", accion="guardar",
        id_usuario=user["id_usuario"], id_entidad=id_envio,
        valor_nuevo={"hay_oos": hay_oos, "nro_protocolo_ext": nro_protocolo_ext},
    )

    return GuardarResultadosResponse(id_envio=id_envio, hay_oos=hay_oos)


@router.post("/{id_envio}/protocolo", response_model=ProtocoloResponse)
def guardar_protocolo(
    id_envio: int,
    nro_protocolo_ext: str = Form(..., min_length=1, max_length=50),
    fecha_emision: date = Form(...),
    protocolo_pdf: UploadFile = File(...),
    user: dict = Depends(require_rol("analista_qc", "qa", "admin")),
    conn: pyodbc.Connection = Depends(limss_db),
):
    """Carga (o reemplazo) del protocolo del laboratorio, independiente de
    guardar_resultados -- para cuando el protocolo formal llega en un
    momento distinto al de los valores (antes, después, o nunca en la misma
    sesión). No toca lims_resultados."""
    cursor = conn.cursor()
    envio = _obtener_envio_o_404(cursor, id_envio)
    if envio.estado_muestra != "en_análisis":
        raise HTTPException(
            status_code=409,
            detail=f"La muestra está en estado '{envio.estado_muestra}', no se puede cargar el protocolo",
        )

    respuesta = _guardar_protocolo(cursor, envio, nro_protocolo_ext, fecha_emision, protocolo_pdf, user["id_usuario"])

    audit.registrar(
        conn, entidad="protocolo", accion="guardar",
        id_usuario=user["id_usuario"], id_entidad=id_envio,
        valor_nuevo={"nro_protocolo_ext": nro_protocolo_ext},
    )

    return respuesta


@router.post("/{id_envio}/comparar-etiqueta", response_model=CompararEtiquetaResponse)
def comparar_etiqueta(
    id_envio: int,
    imagen: UploadFile = File(..., description="Foto de la etiqueta recibida en esta inspección"),
    user: dict = Depends(require_rol("analista_qc", "qa", "admin")),
    conn: pyodbc.Connection = Depends(limss_db),
):
    """Comparación con IA -- asistencia visual, no reemplaza el criterio de
    quien inspecciona (ver app/services/comparacion_empaque_ia.py). UNA
    sola foto y observación por ENVÍO (no por ensayo): varios ensayos de un
    mismo envío (texto legal, colores, código de barras) se verifican
    todos contra la misma etiqueta recibida, así que se sube y se compara
    una sola vez acá, no repetido por cada uno.

    Provisorio hasta guardar: este endpoint sube la imagen a disco y corre
    el OCR, pero NO escribe en lims_envios -- si el usuario sale de la
    pantalla sin guardar los resultados, no debe quedar nada grabado (el
    archivo puede quedar huérfano en disco, no se limpia automáticamente).
    El frontend guarda la respuesta en estado local y la reenvía recién en
    POST .../resultados (guardar_resultados), que es quien persiste."""
    cursor = conn.cursor()
    envio = _obtener_envio_o_404(cursor, id_envio)
    if envio.tipo_material_muestra != "material_empaque":
        raise HTTPException(status_code=400, detail="La comparación con IA solo está disponible para Material de Empaque")

    referencia = empaque_ia.obtener_referencia_activa(cursor, envio.erp_CODART)
    if not referencia:
        raise HTTPException(
            status_code=400,
            detail=f"El artículo '{envio.erp_CODART.strip()}' no tiene una imagen de referencia cargada -- subila primero en la especificación",
        )

    ruta_comparacion = storage.guardar_imagen_comparacion(imagen, envio.codigo_muestra)

    observacion = comparacion_empaque_ia.comparar_etiquetas(
        imagen_referencia_path=storage.ruta_absoluta(referencia.imagen_path),
        imagen_nueva_path=storage.ruta_absoluta(ruta_comparacion),
        contexto=f"envio={id_envio}",
    )

    audit.registrar(
        conn, entidad="comparacion_etiqueta_ia", accion="comparar", id_usuario=user["id_usuario"], id_entidad=id_envio,
        valor_nuevo={"ia_disponible": observacion is not None},
    )

    return CompararEtiquetaResponse(
        id_envio=id_envio, imagen_comparacion_path=ruta_comparacion,
        observacion_ia=observacion, ia_disponible=observacion is not None,
    )


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
