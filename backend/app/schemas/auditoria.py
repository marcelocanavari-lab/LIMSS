from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class AuditoriaRegistro(BaseModel):
    id_audit: int
    fecha_hora: datetime
    usuario_nombre: Optional[str] = None
    accion: str
    detalle: str
    valor_anterior: Optional[str] = None
    valor_nuevo: Optional[str] = None


class AuditoriaListado(BaseModel):
    total: int
    registros: list[AuditoriaRegistro]


class AuditoriaUsuario(BaseModel):
    id_usuario: int
    nombre_completo: str
