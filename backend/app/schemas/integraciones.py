"""
Esquemas para las integraciones server-to-server con el eBR Veterinario
(ver app/api/routes/integraciones.py) -- no confundir con los esquemas del
flujo normal de Solicitud de Muestreo, que son para inspección de materia
prima entrante, no para muestreo en proceso de producción.
"""
from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, Field


class MuestraIntegracionCreate(BaseModel):
    erp_CODART: str = Field(..., min_length=1, max_length=20)
    erp_IdM21: int
    cantidad_enviada: Optional[float] = None
    unidad_enviada: Optional[str] = Field(None, max_length=20)
    # Libre (no ir/lote como en el flujo normal): identifica el origen del
    # muestreo dentro del eBR -- ej. "EBR_PREL".
    tipo_referencia: str = Field(..., min_length=1, max_length=10)
    # Trazabilidad hacia el PREL/orden de eBR que originó la toma de muestra
    # (ej. lote + id de ejecución de PREL).
    nro_referencia: str = Field(..., min_length=1, max_length=50)
    id_usuario_limss: int
    observaciones: Optional[str] = Field(None, max_length=500)


class MuestraIntegracionResponse(BaseModel):
    id_muestra: int
    codigo_muestra: str
    estado: str


class EnvioEstadoInfo(BaseModel):
    id_envio: int
    laboratorio: str
    nro_remito: Optional[str] = None
    fecha_despacho: datetime


class ProtocoloEstadoInfo(BaseModel):
    nro_protocolo_ext: str
    fecha_emision: date
    pdf_path: str


class DictamenEstadoInfo(BaseModel):
    estado_dictamen: str
    fecha_dictamen: datetime
    observaciones: Optional[str] = None


class MuestraEstadoResponse(BaseModel):
    id_muestra: int
    codigo_muestra: str
    estado: str
    envios: list[EnvioEstadoInfo] = []
    protocolos: list[ProtocoloEstadoInfo] = []
    dictamen: Optional[DictamenEstadoInfo] = None
