from pydantic import BaseModel, Field
from typing import Optional
from datetime import date, datetime


class EnsayoParaCarga(BaseModel):
    id_ensayo: int
    orden: int
    nombre_ensayo: str
    metodologia: Optional[str] = None
    tipo_dato: str
    limite_inferior: Optional[float] = None
    limite_superior: Optional[float] = None
    unidad_medida: Optional[str] = None
    valor_requerido: Optional[str] = None
    obligatorio: bool
    # Valor ya guardado, si lo hay (resumir una carga o vista de solo lectura)
    valor_numerico: Optional[float] = None
    valor_cualitativo: Optional[str] = None
    dentro_especificacion: Optional[bool] = None


class ProtocoloResponse(BaseModel):
    id_protocolo: int
    nro_protocolo_ext: str
    fecha_emision: date
    pdf_nombre_original: str
    fecha_carga: datetime


class MuestraParaCarga(BaseModel):
    id_muestra: int
    codigo_muestra: str
    erp_CODART: str
    erp_DESART: str
    estado: str
    ensayos: list[EnsayoParaCarga]
    protocolo: Optional[ProtocoloResponse] = None


class ResultadoInput(BaseModel):
    id_ensayo: int
    valor_numerico: Optional[float] = None
    valor_cualitativo: Optional[str] = None


class GuardarResultadosResponse(BaseModel):
    id_muestra: int
    estado: str
    hay_oos: bool
