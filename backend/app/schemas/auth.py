from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


class LoginRequest(BaseModel):
    codigo: str = Field(..., min_length=1, max_length=20, description="Código de usuario")
    pin: str = Field(..., min_length=4, max_length=6, description="PIN numérico")


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    id_usuario: int
    nombre: str
    apellido: str
    rol: str
    expira_en_minutos: int


class UsuarioCreate(BaseModel):
    codigo: str = Field(..., min_length=1, max_length=20)
    nombre: str = Field(..., min_length=1, max_length=100)
    apellido: str = Field(..., min_length=1, max_length=100)
    pin: str = Field(..., min_length=4, max_length=6, pattern=r"^\d+$")
    rol: str = Field(..., pattern=r"^(muestreador|analista_qc|qa|admin)$")


class UsuarioResponse(BaseModel):
    id_usuario: int
    codigo: str
    nombre: str
    apellido: str
    rol: str
    activo: bool
    fecha_creacion: datetime
