from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


class ErpConfig(BaseModel):
    id: int
    clave: str
    valor: str
    descripcion: Optional[str] = None
    editable: bool
    fecha_modificacion: Optional[datetime] = None
    id_usuario_modificacion: Optional[int] = None


class ErpConfigUpdate(BaseModel):
    valor: str = Field(..., min_length=1, max_length=100)
    descripcion: Optional[str] = Field(None, max_length=200)
