from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class NovedadEmpaqueCreate(BaseModel):
    erp_CODART: str = Field(..., min_length=1, max_length=20)
    titulo: str = Field(..., min_length=1, max_length=200)
    descripcion: str = Field(..., min_length=1, max_length=2000)


class NovedadEmpaqueResolver(BaseModel):
    # Anotación manual de qué se verificó/en qué contexto -- texto libre,
    # sin vincular a ninguna solicitud/muestra puntual (ver módulo de
    # Novedades: standalone, sin cruce con el resto del sistema).
    observaciones_resolucion: Optional[str] = Field(None, max_length=1000)


class NovedadEmpaqueResponse(BaseModel):
    id_novedad: int
    erp_CODART: str
    # Resuelto contra el ERP (GIM21ART) al listar, no se guarda en la tabla
    # -- puede venir None si el artículo ya no existe o cambió de código.
    erp_DESART: Optional[str] = None
    titulo: str
    descripcion: str
    estado: str
    usuario_carga_nombre: str
    fecha_carga: datetime
    usuario_resolucion_nombre: Optional[str] = None
    fecha_resolucion: Optional[datetime] = None
    observaciones_resolucion: Optional[str] = None
