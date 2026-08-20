"""
Imagen de referencia (arte aprobado) de un artículo de Material de Empaque
-- ver migrations_comparacion_ia_empaque.sql. Se sube desde la pantalla de
la especificación del artículo; la usa Carga de Resultados (ver
app/api/routes/resultados.py, endpoint .../comparar-etiqueta) para la
comparación con IA.

Soft-delete al reemplazar: subir una referencia nueva para el mismo
erp_CODART marca la anterior activo=0 en vez de pisarla, se conserva el
historial de versiones de arte aprobado. Un índice único filtrado
(UQ_empaque_referencia_activa, WHERE activo = 1) garantiza a nivel de base
que haya como máximo una activa por artículo -- mismo patrón que
lims_caja_muestras (ver app/api/routes/cajas.py).
"""
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
import pyodbc

from app.core.security import require_rol
from app.db.connections import limss_db
from app.schemas.empaque_ia import ReferenciaEmpaqueResponse
from app.services import audit, storage

router = APIRouter(prefix="/api/empaque-referencia", tags=["Comparación de Etiquetas con IA"])

_ROLES = ("analista_qc", "qa", "admin")

_SELECT_REFERENCIA = """
    SELECT r.*, u.nombre + ' ' + u.apellido AS usuario_carga_nombre
    FROM lims_empaque_referencia r
    INNER JOIN lims_usuarios u ON u.id_usuario = r.id_usuario_carga
"""


def _fila_a_referencia(row) -> ReferenciaEmpaqueResponse:
    return ReferenciaEmpaqueResponse(
        id_referencia=row.id_referencia, erp_CODART=row.erp_CODART, nombre_original=row.nombre_original,
        fecha_carga=row.fecha_carga, usuario_carga_nombre=row.usuario_carga_nombre,
    )


def obtener_referencia_activa(cursor, erp_codart: str):
    """Fila cruda (no el schema Pydantic) de la referencia activa de un
    artículo, o None -- para uso interno de otros routers (ver
    resultados.py, comparar_etiqueta)."""
    cursor.execute(
        "SELECT TOP 1 * FROM lims_empaque_referencia WHERE erp_CODART = ? AND activo = 1 ORDER BY fecha_carga DESC",
        erp_codart.strip(),
    )
    return cursor.fetchone()


@router.get("/{erp_codart}", response_model=ReferenciaEmpaqueResponse)
def obtener_referencia(
    erp_codart: str,
    user: dict = Depends(require_rol(*_ROLES)),
    conn: pyodbc.Connection = Depends(limss_db),
):
    cursor = conn.cursor()
    cursor.execute(_SELECT_REFERENCIA + " WHERE r.erp_CODART = ? AND r.activo = 1", erp_codart.strip())
    row = cursor.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Este artículo no tiene una imagen de referencia cargada")
    return _fila_a_referencia(row)


@router.get("/{erp_codart}/imagen")
def descargar_imagen_referencia(
    erp_codart: str,
    user: dict = Depends(require_rol(*_ROLES)),
    conn: pyodbc.Connection = Depends(limss_db),
):
    cursor = conn.cursor()
    row = obtener_referencia_activa(cursor, erp_codart)
    if not row:
        raise HTTPException(status_code=404, detail="Este artículo no tiene una imagen de referencia cargada")
    return FileResponse(storage.ruta_absoluta(row.imagen_path), filename=row.nombre_original)


@router.post("", response_model=ReferenciaEmpaqueResponse, status_code=201)
def subir_referencia(
    erp_CODART: str = Form(..., min_length=1, max_length=20),
    imagen: UploadFile = File(...),
    user: dict = Depends(require_rol(*_ROLES)),
    conn: pyodbc.Connection = Depends(limss_db),
):
    cursor = conn.cursor()
    codart = erp_CODART.strip()

    ruta = storage.guardar_imagen_referencia_empaque(imagen, codart)

    cursor.execute("UPDATE lims_empaque_referencia SET activo = 0 WHERE erp_CODART = ? AND activo = 1", codart)
    cursor.execute(
        """
        INSERT INTO lims_empaque_referencia (erp_CODART, imagen_path, nombre_original, activo, id_usuario_carga, fecha_carga)
        VALUES (?, ?, ?, 1, ?, GETDATE())
        """,
        codart, ruta, imagen.filename, user["id_usuario"],
    )
    cursor.execute("SELECT @@IDENTITY AS id")
    id_referencia = int(cursor.fetchone().id)

    audit.registrar(
        conn, entidad="empaque_referencia", accion="subir", id_usuario=user["id_usuario"], id_entidad=id_referencia,
        valor_nuevo={"erp_CODART": codart, "nombre_original": imagen.filename},
    )

    cursor.execute(_SELECT_REFERENCIA + " WHERE r.id_referencia = ?", id_referencia)
    return _fila_a_referencia(cursor.fetchone())
