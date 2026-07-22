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


def guardar_pdf_remito(contenido: bytes, nro_remito_interno: str) -> str:
    """Remito de envío generado por el sistema (REQ-ENV-004)."""
    nombre_archivo = f"LIMSS_{_sanitizar(nro_remito_interno)}.pdf"
    return _guardar_bytes(contenido, "remitos", nombre_archivo)


def guardar_pdf_remito_testigo(contenido: bytes, nro_remito: str) -> str:
    """Remito de envío de testigos/estándares a laboratorio externo."""
    nombre_archivo = f"LIMSS_{_sanitizar(nro_remito)}.pdf"
    return _guardar_bytes(contenido, "remitos_testigos", nombre_archivo)


def guardar_pdf_copia_firmada(upload_file: UploadFile, nro_remito: str) -> str:
    """Copia del remito de testigos firmada por el laboratorio como constancia
    de recepción, escaneada y subida por el usuario."""
    nombre_archivo = f"LIMSS_{_sanitizar(nro_remito)}_FIRMADO.pdf"
    return _guardar_pdf(upload_file, os.path.join("remitos", "firmados"), nombre_archivo)


def ruta_absoluta(ruta_relativa: str) -> str:
    return os.path.join(settings.storage_path, ruta_relativa)
