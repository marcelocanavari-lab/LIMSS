from pydantic import BaseModel, Field
from typing import Optional
from datetime import date, datetime


# ── Bandeja de pendientes (REQ-DEC-001) ───────────────────────────

class DictamenPendienteResponse(BaseModel):
    id_muestra: int
    codigo_muestra: str
    erp_CODART: str
    erp_DESART: str
    fecha_muestreo: datetime
    laboratorio_nombre: str
    cantidad_oos: int


# ── Detalle para revisión (REQ-DEC-002) ───────────────────────────

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


class ProtocoloInfo(BaseModel):
    nro_protocolo_ext: str
    fecha_emision: date
    pdf_nombre_original: str


class EnvioInfo(BaseModel):
    id_envio: int
    laboratorio_nombre: str
    fecha_despacho: datetime
    testigo_codigo: Optional[str] = None
    testigo_nombre: Optional[str] = None


class DictamenDetalleResponse(BaseModel):
    id_muestra: int
    codigo_muestra: str
    erp_CODART: str
    erp_DESART: str
    tipo_referencia: str
    nro_referencia: str
    fecha_muestreo: datetime
    usuario_muestreo_nombre: str
    estado: str
    ensayos: list[EnsayoResultado]
    hay_oos: bool
    protocolo: Optional[ProtocoloInfo] = None
    envio: Optional[EnvioInfo] = None


# ── Emisión del dictamen (REQ-DEC-003/004) ────────────────────────

class DictamenCreate(BaseModel):
    estado_dictamen: str = Field(..., pattern=r"^(aprobado|rechazado|cuarentena)$")
    justificacion_oos: Optional[str] = Field(None, max_length=1000)
    observaciones: Optional[str] = Field(None, max_length=500)
    pin_confirmacion: str = Field(..., min_length=4, max_length=6)


class DictamenResponse(BaseModel):
    id_dictamen: int
    id_muestra: int
    estado_dictamen: str
    justificacion_oos: Optional[str] = None
    observaciones: Optional[str] = None
    id_usuario_qa: int
    fecha_dictamen: datetime
