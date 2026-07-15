from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


class DictamenCreate(BaseModel):
    estado_dictamen: str = Field(..., pattern=r"^(aprobado|rechazado|cuarentena)$")
    justificacion_oos: Optional[str] = Field(None, max_length=1000)
    observaciones: Optional[str] = Field(None, max_length=500)
    pin: str = Field(..., min_length=4, max_length=6)


class DictamenResponse(BaseModel):
    id_dictamen: int
    id_muestra: int
    estado_dictamen: str
    justificacion_oos: Optional[str] = None
    observaciones: Optional[str] = None
    id_usuario_qa: int
    fecha_dictamen: datetime
