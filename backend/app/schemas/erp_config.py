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


class SubarticuloConfig(BaseModel):
    """Una fila por CODSAR del catálogo GIT59SAR del ERP (universo chico de
    subartículos, no confundir con GIM21ART -- los artículos individuales,
    miles de filas), combinada con su estado de configuración en LIMSS si
    ya existe (ver GET /api/erp-config/subarticulos)."""
    erp_codsar: str
    erp_dessar: Optional[str] = None
    configurado: bool
    requiere_muestreo: bool
    id: Optional[int] = None
    fecha_carga: Optional[datetime] = None
    id_usuario_carga: Optional[int] = None


class SubarticuloUpsert(BaseModel):
    requiere_muestreo: bool
