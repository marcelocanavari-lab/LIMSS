from pydantic import BaseModel, Field
from typing import Optional
from datetime import date, datetime


# ── ERP (solo lectura) ────────────────────────────────────────

class ArticuloERP(BaseModel):
    IdM21: int
    CODART: str
    DESART: str
    unidad: Optional[str] = None


# ── Ensayos: catálogo maestro ────────────────────────────────────

class EnsayoMaestroCreate(BaseModel):
    nombre_ensayo: str = Field(..., min_length=1, max_length=100)
    bibliografia: Optional[str] = Field(None, max_length=200)
    observaciones: Optional[str] = Field(None, max_length=500)


class EnsayoMaestroResponse(BaseModel):
    id_ensayo_maestro: int
    nombre_ensayo: str
    bibliografia: Optional[str] = None
    observaciones: Optional[str] = None
    cantidad_especificaciones: int = 0


# ── Ensayos: aplicación a una especificación ──────────────────────

class EspecificacionEnsayoCreate(BaseModel):
    id_ensayo_maestro: int
    orden: int
    metodologia: Optional[str] = Field(None, max_length=100)
    tipo_dato: str = Field(..., pattern=r"^(numerico|cualitativo)$")
    limite_inferior: Optional[float] = None
    limite_superior: Optional[float] = None
    unidad_medida: Optional[str] = Field(None, max_length=20)
    valor_requerido: Optional[str] = Field(None, max_length=200)
    especificacion_texto: Optional[str] = Field(None, max_length=500)
    obligatorio: bool = True
    requerido_por_defecto: bool = True
    id_laboratorio: Optional[int] = None


class EspecificacionEnsayoResponse(BaseModel):
    id_espec_ensayo: int
    id_especificacion: int
    id_ensayo_maestro: int
    nombre_ensayo: str
    orden: int
    metodologia: Optional[str] = None
    tipo_dato: str
    limite_inferior: Optional[float] = None
    limite_superior: Optional[float] = None
    unidad_medida: Optional[str] = None
    valor_requerido: Optional[str] = None
    especificacion_texto: Optional[str] = None
    obligatorio: bool
    requerido_por_defecto: bool
    id_laboratorio: Optional[int] = None
    laboratorio_nombre: Optional[str] = None


# ── Especificaciones ───────────────────────────────────────────

class EspecificacionCreate(BaseModel):
    erp_IdM21: int
    erp_CODART: str = Field(..., min_length=1, max_length=20)
    erp_DESART: str = Field(..., min_length=1, max_length=100)
    tipo_material: str = Field(..., pattern=r"^(materia_prima|granel|semi_elaborado|producto_terminado)$")
    cantidad_muestra: Optional[float] = None
    unidad_muestra: Optional[str] = Field(None, max_length=20)


class EspecificacionCopiar(BaseModel):
    """Body para crear una especificación nueva e independiente a partir de
    otra existente (distinto artículo/tipo posible) -- ver 'copiar'."""
    erp_IdM21: int
    erp_CODART: str = Field(..., min_length=1, max_length=20)
    erp_DESART: str = Field(..., min_length=1, max_length=100)
    tipo_material: str = Field(..., pattern=r"^(materia_prima|granel|semi_elaborado|producto_terminado)$")
    version: str = Field("1.0", max_length=10)


class EspecificacionResponse(BaseModel):
    id_especificacion: int
    erp_IdM21: int
    erp_CODART: str
    erp_DESART: str
    tipo_material: str
    cantidad_muestra: Optional[float] = None
    unidad_muestra: Optional[str] = None
    version: str
    vigente: bool
    id_usuario_carga: int
    fecha_carga: datetime


class EspecificacionDetalle(EspecificacionResponse):
    ensayos: list[EspecificacionEnsayoResponse]


# ── Testigos asociados a una especificación ───────────────────────

class EspecificacionTestigoCreate(BaseModel):
    id_testigo: int


class EspecificacionTestigoResponse(BaseModel):
    id: int
    id_especificacion: int
    id_testigo: int
    codigo: str
    nombre: str


# ── Testigos ───────────────────────────────────────────────────

class TestigoResponse(BaseModel):
    id_testigo: int
    codigo: str
    nombre: str
    nro_lote: str
    nro_ir: Optional[str] = None
    fecha_vencimiento: Optional[date] = None
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
