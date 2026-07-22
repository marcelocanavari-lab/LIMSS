from pydantic import BaseModel, Field
from typing import Optional
from datetime import date, datetime


# ── ERP: líneas de un IR (solo lectura) ───────────────────────

class LineaIR(BaseModel):
    N01Id: int
    NUMCOMO: str
    IdM21: int
    CODART: str
    DESART: str
    CANTID: float
    unidad: Optional[str] = None
    proveedor: Optional[str] = None
    advertencia: Optional[str] = None


# ── Materiales (búsqueda unificada por tipo: IR o lote) ──────────

class MaterialEncontrado(BaseModel):
    referencia: str
    IdM21: int
    CODART: str
    DESART: str
    cantidad: Optional[float] = None
    unidad: Optional[str] = None
    proveedor: Optional[str] = None
    advertencia: Optional[str] = None


# ── Muestras ───────────────────────────────────────────────────

class MuestraCreate(BaseModel):
    tipo_referencia: str = Field(..., pattern=r"^(ir|lote)$")
    nro_referencia: str = Field(..., min_length=1, max_length=50)
    erp_IdM21: int
    erp_CODART: str = Field(..., min_length=1, max_length=20)
    erp_DESART: str = Field(..., min_length=1, max_length=100)
    erp_cantidad_lote: Optional[float] = None
    erp_proveedor: Optional[str] = Field(None, max_length=100)
    cantidad_enviada: Optional[float] = None
    unidad_enviada: Optional[str] = Field(None, max_length=20)
    observaciones: Optional[str] = Field(None, max_length=500)


class MuestraResponse(BaseModel):
    id_muestra: int
    codigo_muestra: str
    tipo_referencia: str
    nro_referencia: str
    erp_IdM21: int
    erp_CODART: str
    erp_DESART: str
    erp_cantidad_lote: Optional[float] = None
    erp_proveedor: Optional[str] = None
    cantidad_enviada: Optional[float] = None
    unidad_enviada: Optional[str] = None
    id_especificacion: Optional[int] = None
    estado: str
    id_usuario_muestreo: int
    usuario_muestreo_nombre: str
    fecha_muestreo: datetime
    observaciones: Optional[str] = None


# ── Laboratorios ───────────────────────────────────────────────

class LaboratorioCreate(BaseModel):
    nombre: str = Field(..., min_length=1, max_length=150)
    direccion: Optional[str] = Field(None, max_length=200)
    contacto: Optional[str] = Field(None, max_length=100)
    email: Optional[str] = Field(None, max_length=100)
    telefono: Optional[str] = Field(None, max_length=30)


class LaboratorioResponse(LaboratorioCreate):
    id_laboratorio: int
    activo: bool


class LaboratorioUpdate(BaseModel):
    nombre: str = Field(..., min_length=1, max_length=150)
    direccion: Optional[str] = Field(None, max_length=200)
    contacto: Optional[str] = Field(None, max_length=100)
    email: Optional[str] = Field(None, max_length=100)
    telefono: Optional[str] = Field(None, max_length=30)
    activo: bool


# ── Envíos ─────────────────────────────────────────────────────

class TestigoEnvioItem(BaseModel):
    id_testigo: int


class EnvioCreate(BaseModel):
    id_laboratorio: int
    testigos: list[TestigoEnvioItem] = []
    temperatura_transporte: Optional[str] = Field(None, max_length=50)
    nro_remito: Optional[str] = Field(None, max_length=50)
    transportista: Optional[str] = Field(None, max_length=100)
    analisis_solicitados: Optional[str] = Field(None, max_length=500)
    protocolo_utilizar: Optional[str] = Field(None, max_length=100)
    id_espec_ensayo: Optional[list[int]] = None


class EnsayoSolicitado(BaseModel):
    id_espec_ensayo: int
    nombre_ensayo: str
    requerido_por_defecto: bool
    id_laboratorio: Optional[int] = None
    laboratorio_nombre: Optional[str] = None


class TestigoEnviado(BaseModel):
    id_testigo: int
    codigo: str
    nombre: str
    nro_ir: Optional[str] = None


class TestigoRemito(BaseModel):
    id_testigo: int
    codigo: str
    nombre: str
    nro_ir: Optional[str] = None
    nro_lote: Optional[str] = None
    fecha_vencimiento: Optional[date] = None


class EnvioResponse(BaseModel):
    id_envio: int
    id_muestra: int
    id_laboratorio: int
    testigos: list[TestigoEnviado] = []
    fecha_despacho: datetime
    temperatura_transporte: Optional[str] = None
    nro_remito: Optional[str] = None
    transportista: Optional[str] = None
    analisis_solicitados: Optional[str] = None
    protocolo_utilizar: Optional[str] = None
    id_usuario_envio: int
    alerta_testigo_por_vencer: bool = False
    alerta_reorden: bool = False
    ensayos_solicitados: list[EnsayoSolicitado] = []


class RemitoResponse(BaseModel):
    id_envio: int
    codigo_muestra: str
    tipo_referencia: str
    nro_referencia: str
    erp_CODART: str
    erp_DESART: str
    fecha_muestreo: datetime
    usuario_muestreo_nombre: str
    cantidad_enviada: Optional[float] = None
    unidad_enviada: Optional[str] = None
    laboratorio_nombre: str
    laboratorio_direccion: Optional[str] = None
    laboratorio_contacto: Optional[str] = None
    fecha_despacho: datetime
    temperatura_transporte: Optional[str] = None
    nro_remito: Optional[str] = None
    transportista: Optional[str] = None
    analisis_solicitados: Optional[str] = None
    protocolo_utilizar: Optional[str] = None
    ensayos_solicitados: list[EnsayoSolicitado] = []
    testigos: list[TestigoRemito] = []


# ── Etiquetas (REQ-ENV-003) ───────────────────────────────────────

class EtiquetaResponse(BaseModel):
    id_etiqueta: int
    id_muestra: int
    codigo_muestra: str
    erp_CODART: str
    erp_DESART: str
    tipo_referencia: str
    nro_referencia: str
    fecha_muestreo: datetime
    usuario_muestreo_nombre: str
    es_reimpresion: bool
    id_usuario_impresion: int
    fecha_hora: datetime
