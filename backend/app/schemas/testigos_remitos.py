from pydantic import BaseModel, Field
from typing import Optional
from datetime import date, datetime


class TestigoEnvioRemito(BaseModel):
    id_testigo: int
    cantidad_enviada: float = Field(..., gt=0)
    unidad: str = Field(..., min_length=1, max_length=20)


class RemitoTestigoCreate(BaseModel):
    id_laboratorio: int
    fecha_envio: date
    observaciones: Optional[str] = Field(None, max_length=500)
    testigos: list[TestigoEnvioRemito] = Field(..., min_length=1)


class RemitoTestigoResponse(BaseModel):
    id_remito: int
    nro_remito: str
    id_laboratorio: int
    laboratorio_nombre: str
    fecha_envio: date
    observaciones: Optional[str] = None
    cantidad_testigos: int
    id_usuario: int
    fecha_creacion: datetime
    tiene_copia_firmada: bool = False
    fecha_recepcion: Optional[date] = None
    recibido_por: Optional[str] = None


class TestigoEnRemito(BaseModel):
    id_testigo: int
    codigo: str
    nombre: str
    nro_lote: str
    nro_ir: Optional[str] = None
    fecha_vencimiento: Optional[date] = None
    cantidad_enviada: float
    unidad: str


class RemitoTestigoDetalle(BaseModel):
    id_remito: int
    nro_remito: str
    id_laboratorio: int
    laboratorio_nombre: str
    laboratorio_direccion: Optional[str] = None
    laboratorio_contacto: Optional[str] = None
    fecha_envio: date
    observaciones: Optional[str] = None
    id_usuario: int
    usuario_nombre: str
    fecha_creacion: datetime
    tiene_copia_firmada: bool = False
    fecha_recepcion: Optional[date] = None
    recibido_por: Optional[str] = None
    testigos: list[TestigoEnRemito]


class HistorialEnvioTestigo(BaseModel):
    id_remito: int
    nro_remito: str
    fecha_envio: date
    laboratorio_nombre: str
    cantidad_enviada: float
    unidad: str
