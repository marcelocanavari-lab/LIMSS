"""
Esquemas compartidos para el "recorrido" completo de una muestra: datos de
cabecera + todos sus envíos (cada uno con sus propios ensayos/resultados,
testigos y protocolo) + el dictamen final si ya se emitió.

Lo usan tanto GET /api/muestras/{id}/recorrido (Consulta de Muestras,
cualquier rol) como GET /api/dictamen/{id_muestra} (bandeja de QA) -- ambos
necesitan exactamente la misma agregación, ver app/services/recorrido.py.
"""
from pydantic import BaseModel
from typing import Optional
from datetime import date, datetime


class EnsayoResultado(BaseModel):
    id_espec_ensayo: int
    orden: int
    nombre_ensayo: str
    metodologia: Optional[str] = None
    tipo_dato: str
    limite_inferior: Optional[float] = None
    limite_superior: Optional[float] = None
    unidad_medida: Optional[str] = None
    valor_requerido: Optional[str] = None
    obligatorio: bool
    valor_numerico: Optional[float] = None
    valor_cualitativo: Optional[str] = None
    dentro_especificacion: Optional[bool] = None


class TestigoEnvioInfo(BaseModel):
    id_testigo: int
    codigo: str
    nombre: str


class ProtocoloEnvioInfo(BaseModel):
    nro_protocolo_ext: str
    fecha_emision: date
    pdf_nombre_original: str


class EnvioDetalleInfo(BaseModel):
    id_envio: int
    laboratorio_nombre: str
    fecha_despacho: datetime
    nro_remito: Optional[str] = None
    testigos: list[TestigoEnvioInfo] = []
    protocolo: Optional[ProtocoloEnvioInfo] = None
    ensayos: list[EnsayoResultado] = []
    completo: bool


class DictamenInfo(BaseModel):
    estado_dictamen: str
    usuario_qa_nombre: str
    fecha_dictamen: datetime
    justificacion_oos: Optional[str] = None
    observaciones: Optional[str] = None


class RecorridoResponse(BaseModel):
    id_muestra: int
    codigo_muestra: str
    erp_CODART: str
    erp_DESART: str
    tipo_referencia: str
    nro_referencia: str
    fecha_muestreo: datetime
    usuario_muestreo_nombre: str
    estado: str
    envios: list[EnvioDetalleInfo] = []
    dictamen: Optional[DictamenInfo] = None
    hay_oos: bool = False
