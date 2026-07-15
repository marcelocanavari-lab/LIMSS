from pydantic import BaseModel, Field
from typing import Optional
from datetime import date, datetime


# ── ERP (solo lectura) ────────────────────────────────────────

class ArticuloERP(BaseModel):
    IdM21: int
    CODART: str
    DESART: str
    unidad: Optional[str] = None


# ── Ensayos ────────────────────────────────────────────────────

class EnsayoCreate(BaseModel):
    orden: int
    nombre_ensayo: str = Field(..., min_length=1, max_length=100)
    metodologia: Optional[str] = Field(None, max_length=100)
    tipo_dato: str = Field(..., pattern=r"^(numerico|cualitativo)$")
    limite_inferior: Optional[float] = None
    limite_superior: Optional[float] = None
    unidad_medida: Optional[str] = Field(None, max_length=20)
    valor_requerido: Optional[str] = Field(None, max_length=200)
    obligatorio: bool = True
    observaciones: Optional[str] = Field(None, max_length=500)


class EnsayoResponse(EnsayoCreate):
    id_ensayo: int
    id_especificacion: int


# ── Especificaciones ───────────────────────────────────────────

class EspecificacionCreate(BaseModel):
    erp_IdM21: int
    erp_CODART: str = Field(..., min_length=1, max_length=20)
    erp_DESART: str = Field(..., min_length=1, max_length=100)
    tipo_material: str = Field(..., pattern=r"^(materia_prima|granel|semi_elaborado|producto_terminado)$")
    ensayos: list[EnsayoCreate] = Field(..., min_length=1)


class EspecificacionResponse(BaseModel):
    id_especificacion: int
    erp_IdM21: int
    erp_CODART: str
    erp_DESART: str
    tipo_material: str
    version: str
    vigente: bool
    id_usuario_carga: int
    fecha_carga: datetime


class EspecificacionDetalle(EspecificacionResponse):
    ensayos: list[EnsayoResponse]


class EspecificacionRevision(BaseModel):
    """Body para crear una nueva versión de una especificación vigente."""
    ensayos: list[EnsayoCreate] = Field(..., min_length=1)


# ── Testigos ───────────────────────────────────────────────────

class TestigoResponse(BaseModel):
    id_testigo: int
    codigo: str
    nombre: str
    nro_lote: str
    fecha_vencimiento: date
    stock_actual: float
    stock_minimo: float
    unidad_medida: Optional[str] = None
    pdf_certificado: Optional[str] = None
    activo: bool
    id_usuario_carga: int
    fecha_carga: datetime
    observaciones: Optional[str] = None
    vencido: bool
    por_vencer: bool
    stock_bajo: bool


class TestigoUpdate(BaseModel):
    nombre: str = Field(..., min_length=1, max_length=150)
    nro_lote: str = Field(..., min_length=1, max_length=50)
    fecha_vencimiento: date
    stock_minimo: float = Field(..., ge=0)
    unidad_medida: Optional[str] = Field(None, max_length=20)
    observaciones: Optional[str] = Field(None, max_length=500)


class TestigoMovimientoResponse(BaseModel):
    id_movimiento: int
    id_testigo: int
    id_envio: Optional[int] = None
    tipo: str
    cantidad: float
    stock_resultante: float
    id_usuario: int
    fecha_hora: datetime
    observaciones: Optional[str] = None


class TestigoAjusteStock(BaseModel):
    cantidad: float = Field(..., description="Puede ser positiva (ingreso) o negativa (egreso/merma)")
    observaciones: Optional[str] = Field(None, max_length=200)
