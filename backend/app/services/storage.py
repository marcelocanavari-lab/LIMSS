"""
Almacenamiento de archivos PDF (certificados de testigos, protocolos, etc.)

Sin patrón previo en eBR para esto — se diseña desde cero según REQ-TEC-002:
los archivos se renombran bajo un estándar estricto (LIMS_<codigo>_<TIPO>_<timestamp>.pdf)
y se guardan en la ruta configurada en STORAGE_PATH (por defecto, un share de red
con permisos de acceso restringidos administrados fuera de esta app).
"""
import os
from datetime import datetime
from fastapi import HTTPException, UploadFile

from app.core.config import get_settings

settings = get_settings()

MAX_PDF_SIZE_BYTES = 10 * 1024 * 1024  # 10 MB


def _sanitizar(codigo: str) -> str:
    return codigo.replace("/", "-").replace("\\", "-").replace(" ", "_")


def _guardar_bytes(contenido: bytes, subdir: str, nombre_archivo: str) -> str:
    """Escribe bytes ya validados bajo `{storage_path}/{subdir}/{nombre_archivo}`.
    Devuelve la ruta relativa a persistir en la base."""
    ruta_relativa = os.path.join(subdir, nombre_archivo)
    directorio = os.path.join(settings.storage_path, subdir)
    os.makedirs(directorio, exist_ok=True)

    with open(os.path.join(settings.storage_path, ruta_relativa), "wb") as f:
        f.write(contenido)

    return ruta_relativa


def _guardar_pdf(upload_file: UploadFile, subdir: str, nombre_archivo: str) -> str:
    """Valida un PDF subido por el usuario y lo guarda. Devuelve la ruta
    relativa a persistir en la base."""
    if upload_file.content_type != "application/pdf":
        raise HTTPException(status_code=400, detail="El archivo debe ser un PDF")

    contenido = upload_file.file.read()
    if not contenido:
        raise HTTPException(status_code=400, detail="El PDF está vacío")
    if len(contenido) > MAX_PDF_SIZE_BYTES:
        raise HTTPException(status_code=400, detail="El PDF no puede superar los 10 MB")

    return _guardar_bytes(contenido, subdir, nombre_archivo)


def guardar_pdf_testigo(upload_file: UploadFile, codigo_testigo: str) -> str:
    """Certificado analítico de un testigo (REQ-MAS-003)."""
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    nombre_archivo = f"LIMS_{_sanitizar(codigo_testigo)}_CERT_{timestamp}.pdf"
    return _guardar_pdf(upload_file, "testigos", nombre_archivo)


def guardar_pdf_protocolo(upload_file: UploadFile, codigo_muestra: str) -> str:
    """Protocolo analítico del laboratorio externo (REQ-RES-004)."""
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    nombre_archivo = f"LIMS_{_sanitizar(codigo_muestra)}_PROT_{timestamp}.pdf"
    return _guardar_pdf(upload_file, "protocolos", nombre_archivo)


_EXTENSIONES_PROTOCOLO_PROVEEDOR = {
    "application/pdf": "pdf",
    "image/jpeg": "jpg",
    "image/jpg": "jpg",
    "image/png": "png",
}


def guardar_protocolo_proveedor(upload_file: UploadFile, nro_solicitud: str) -> str:
    """Protocolo que entrega el PROVEEDOR junto con el lote (foto o PDF),
    adjuntado por QA al generar la solicitud de muestreo -- antes de que
    exista ningún envío. No confundir con guardar_pdf_protocolo (protocolo
    del laboratorio de análisis, ligado a un envío, solo PDF)."""
    extension = _EXTENSIONES_PROTOCOLO_PROVEEDOR.get(upload_file.content_type)
    if extension is None:
        raise HTTPException(
            status_code=400,
            detail="El protocolo del proveedor debe ser una imagen (JPG/PNG) o un PDF",
        )

    contenido = upload_file.file.read()
    if not contenido:
        raise HTTPException(status_code=400, detail="El archivo está vacío")
    if len(contenido) > MAX_PDF_SIZE_BYTES:
        raise HTTPException(status_code=400, detail="El archivo no puede superar los 10 MB")

    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    nombre_archivo = f"LIMS_{_sanitizar(nro_solicitud)}_PROTPROV_{timestamp}.{extension}"
    return _guardar_bytes(contenido, "protocolos_proveedor", nombre_archivo)


def guardar_documentacion_proveedor(upload_file: UploadFile, nro_solicitud: str) -> str:
    """Documentación del proveedor (remito y/o factura combinados en un solo
    archivo, foto o PDF) -- a diferencia del protocolo del proveedor, es
    OPCIONAL y se puede adjuntar en el momento de crear la solicitud o
    después, editándola (ver POST /{id_solicitud}/documentacion-proveedor).
    Mismo criterio de validación de formato que guardar_protocolo_proveedor."""
    extension = _EXTENSIONES_PROTOCOLO_PROVEEDOR.get(upload_file.content_type)
    if extension is None:
        raise HTTPException(
            status_code=400,
            detail="La documentación del proveedor debe ser una imagen (JPG/PNG) o un PDF",
        )

    contenido = upload_file.file.read()
    if not contenido:
        raise HTTPException(status_code=400, detail="El archivo está vacío")
    if len(contenido) > MAX_PDF_SIZE_BYTES:
        raise HTTPException(status_code=400, detail="El archivo no puede superar los 10 MB")

    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    nombre_archivo = f"LIMS_{_sanitizar(nro_solicitud)}_DOCPROV_{timestamp}.{extension}"
    return _guardar_bytes(contenido, "documentacion_proveedor", nombre_archivo)


def guardar_pdf_remito(contenido: bytes, nro_remito_interno: str) -> str:
    """Remito de envío generado por el sistema (REQ-ENV-004)."""
    nombre_archivo = f"LIMSS_{_sanitizar(nro_remito_interno)}.pdf"
    return _guardar_bytes(contenido, "remitos", nombre_archivo)


def guardar_pdf_remito_testigo(contenido: bytes, nro_remito: str) -> str:
    """Remito de envío de testigos/estándares a laboratorio externo."""
    nombre_archivo = f"LIMSS_{_sanitizar(nro_remito)}.pdf"
    return _guardar_bytes(contenido, "remitos_testigos", nombre_archivo)


def guardar_pdf_copia_firmada(upload_file: UploadFile, nro_remito: str) -> str:
    """Copia de un remito (de muestra o de testigos, mismo nombrado -- cada
    uno usa su propio prefijo de numeración: REM-YYYY-NNNN vs REM-TEST-YYYY-NNN,
    así que no chocan aunque compartan carpeta) firmada por el laboratorio
    como constancia de recepción, escaneada y subida por el usuario."""
    nombre_archivo = f"LIMSS_{_sanitizar(nro_remito)}_FIRMADO.pdf"
    return _guardar_pdf(upload_file, os.path.join("remitos", "firmados"), nombre_archivo)


def ruta_absoluta(ruta_relativa: str) -> str:
    return os.path.join(settings.storage_path, ruta_relativa)


_EXTENSIONES_IMAGEN_O_PDF = {
    "application/pdf": "pdf",
    "image/jpeg": "jpg",
    "image/jpg": "jpg",
    "image/png": "png",
}

_EXTENSIONES_SOLO_IMAGEN = {"image/jpeg": "jpg", "image/jpg": "jpg", "image/png": "png"}


def guardar_imagen_referencia_empaque(upload_file: UploadFile, erp_codart: str) -> str:
    """Imagen de referencia (arte aprobado) de un artículo de Material de
    Empaque -- foto o PDF de una sola página, ver lims_empaque_referencia.
    El soft-delete de la referencia anterior (activo=0) lo maneja el router,
    esta función solo guarda el archivo nuevo."""
    extension = _EXTENSIONES_IMAGEN_O_PDF.get(upload_file.content_type)
    if extension is None:
        raise HTTPException(status_code=400, detail="La imagen de referencia debe ser una imagen (JPG/PNG) o un PDF")

    contenido = upload_file.file.read()
    if not contenido:
        raise HTTPException(status_code=400, detail="El archivo está vacío")
    if len(contenido) > MAX_PDF_SIZE_BYTES:
        raise HTTPException(status_code=400, detail="El archivo no puede superar los 10 MB")

    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    nombre_archivo = f"LIMS_{_sanitizar(erp_codart)}_REF_{timestamp}.{extension}"
    return _guardar_bytes(contenido, "empaque_referencia", nombre_archivo)


def guardar_imagen_comparacion(upload_file: UploadFile, codigo_muestra: str) -> str:
    """Foto de la etiqueta recibida en una inspección puntual, para comparar
    contra la referencia activa del artículo -- solo imagen (a diferencia de
    la referencia, acá siempre es una foto tomada en el momento, no un PDF)."""
    extension = _EXTENSIONES_SOLO_IMAGEN.get(upload_file.content_type)
    if extension is None:
        raise HTTPException(status_code=400, detail="La foto de la etiqueta debe ser una imagen (JPG/PNG)")

    contenido = upload_file.file.read()
    if not contenido:
        raise HTTPException(status_code=400, detail="El archivo está vacío")
    if len(contenido) > MAX_PDF_SIZE_BYTES:
        raise HTTPException(status_code=400, detail="El archivo no puede superar los 10 MB")

    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    nombre_archivo = f"LIMS_{_sanitizar(codigo_muestra)}_COMPIA_{timestamp}.{extension}"
    return _guardar_bytes(contenido, "comparaciones_ia", nombre_archivo)
