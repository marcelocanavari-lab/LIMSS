from pydantic import BaseModel, Field
from typing import Literal, Optional
from datetime import date, datetime


# ── ERP (solo lectura) ────────────────────────────────────────

class ArticuloERP(BaseModel):
    IdM21: int
    CODART: str
    DESART: str
    unidad: Optional[str] = None


class ProveedorERP(BaseModel):
    id_proveedor: int
    codigo: str
    nombre: str


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
    cantidad_contramuestra: Optional[float] = None
    unidad_contramuestra: Optional[str] = Field(None, max_length=20)


class EspecificacionCantidades(BaseModel):
    """Body de PUT .../cantidades -- ver ese endpoint para el porqué de que
    estos 4 campos se editen aparte del resto de la especificación."""
    cantidad_muestra: Optional[float] = None
    unidad_muestra: Optional[str] = Field(None, max_length=20)
    cantidad_contramuestra: Optional[float] = None
    unidad_contramuestra: Optional[str] = Field(None, max_length=20)


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
    # Deprecados desde que existe lims_especificacion_muestras -- se
    # mantienen por compatibilidad pero ya no se cargan/editan.
    cantidad_muestra: Optional[float] = None
    unidad_muestra: Optional[str] = None
    cantidad_contramuestra: Optional[float] = None
    unidad_contramuestra: Optional[str] = None
    version: str
    vigente: bool
    id_usuario_carga: int
    fecha_carga: datetime
    # Indicadores para el listado -- solo GET /especificaciones los completa
    # de verdad (ver listar_especificaciones); el resto de los endpoints que
    # reusan _fila_a_especificacion los dejan en False por defecto.
    tiene_muestras: bool = False
    tiene_testigos: bool = False


class EspecificacionDetalle(EspecificacionResponse):
    ensayos: list[EspecificacionEnsayoResponse]


# ── Muestras definidas por especificación ─────────────────────────
#
# Reemplaza a los campos cantidad_muestra/unidad_muestra/cantidad_
# contramuestra/unidad_contramuestra de arriba: una especificación puede
# tener varias muestras (no solo "análisis" + "contramuestra" fijos), cada
# una con su propio laboratorio de destino y si genera etiqueta o no.

class EspecificacionMuestraCreate(BaseModel):
    tipo_muestra: str = Field(..., pattern=r"^(analisis|contramuestra|testigo)$")
    cantidad: float = Field(..., gt=0)
    unidad: str = Field(..., min_length=1, max_length=20)
    genera_etiqueta: bool = True
    id_laboratorio: Optional[int] = None


class EspecificacionMuestraResponse(BaseModel):
    id: int
    id_especificacion: int
    tipo_muestra: str
    cantidad: float
    unidad: str
    genera_etiqueta: bool
    id_laboratorio: Optional[int] = None
    laboratorio_nombre: Optional[str] = None
    orden: int


# ── Testigos asociados a una especificación ───────────────────────

class EspecificacionTestigoCreate(BaseModel):
    id_testigo: int


class EspecificacionTestigoResponse(BaseModel):
    id: int
    id_especificacion: int
    id_testigo: int
    codigo: str
    nombre: str
    fecha_vencimiento: Optional[date] = None
    stock_actual: Optional[float] = None
    unidad_medida: Optional[str] = None
    vencido: bool = False
    por_vencer: bool = False


# ── Testigos ───────────────────────────────────────────────────

class LaboratorioAsignado(BaseModel):
    id_laboratorio: int
    nombre: str
    consumo_estimado: Optional[float] = None
    unidad_consumo: Optional[Literal["mg", "ml"]] = None


class TestigoLaboratorioCreate(BaseModel):
    id_laboratorio: int
    consumo_estimado: Optional[float] = Field(None, ge=0)
    unidad_consumo: Optional[Literal["mg", "ml"]] = None


class TestigoLaboratorioConsumoUpdate(BaseModel):
    consumo_estimado: Optional[float] = Field(None, ge=0)
    unidad_consumo: Optional[Literal["mg", "ml"]] = None


class TestigoResponse(BaseModel):
    id_testigo: int
    codigo: str
    nombre: str
    nro_lote: str
    nro_ir: Optional[str] = None
    fecha_vencimiento: Optional[date] = None
    stock_actual: float
    stock_minimo: float
    unidad_medida: Literal["mg", "ml"] = "mg"
    pdf_certificado: Optional[str] = None
    activo: bool
    id_usuario_carga: int
    fecha_carga: datetime
    observaciones: Optional[str] = None
    vencido: bool
    por_vencer: bool
    stock_bajo: bool
    id_laboratorio: Optional[int] = None
    laboratorio_nombre: Optional[str] = None
    laboratorios: list[LaboratorioAsignado] = []
    origen: Optional[Literal["USP", "EP", "INAME"]] = None
    id_categoria: Optional[int] = None
    categoria_nombre: Optional[str] = None


class TestigoCategoriaCreate(BaseModel):
    codigo: str = Field(..., min_length=1, max_length=20)
    nombre: str = Field(..., min_length=1, max_length=100)


class TestigoCategoriaUpdate(BaseModel):
    codigo: str = Field(..., min_length=1, max_length=20)
    nombre: str = Field(..., min_length=1, max_length=100)
    activo: bool


class TestigoCategoriaResponse(BaseModel):
    id_categoria: int
    codigo: str
    nombre: str
    activo: bool


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
