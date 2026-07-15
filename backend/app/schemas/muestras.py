from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


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


# ── Materiales (búsqueda unificada por tipo: IR o lote) ──────────

class MaterialEncontrado(BaseModel):
    referencia: str
    IdM21: int
    CODART: str
    DESART: str
    cantidad: Optional[float] = None
    unidad: Optional[str] = None
    proveedor: Optional[str] = None


# ── Muestras ───────────────────────────────────────────────────

class MuestraCreate(BaseModel):
    tipo_referencia: str = Field(..., pattern=r"^(ir|lote)$")
    nro_referencia: str = Field(..., min_length=1, max_length=50)
    erp_IdM21: int
    erp_CODART: str = Field(..., min_length=1, max_length=20)
    erp_DESART: str = Field(..., min_length=1, max_length=100)
    erp_cantidad_lote: Optional[float] = None
    erp_proveedor: Optional[str] = Field(None, max_length=100)
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

class EnvioCreate(BaseModel):
    id_laboratorio: int
    id_testigo: Optional[int] = None
    cantidad_testigo: Optional[float] = Field(None, gt=0)
    temperatura_transporte: Optional[str] = Field(None, max_length=50)
    nro_remito: Optional[str] = Field(None, max_length=50)
    transportista: Optional[str] = Field(None, max_length=100)
    analisis_solicitados: Optional[str] = Field(None, max_length=500)
    protocolo_utilizar: Optional[str] = Field(None, max_length=100)


class EnvioResponse(BaseModel):
    id_envio: int
    id_muestra: int
    id_laboratorio: int
    id_testigo: Optional[int] = None
    cantidad_testigo: Optional[float] = None
    fecha_despacho: datetime
    temperatura_transporte: Optional[str] = None
    nro_remito: Optional[str] = None
    transportista: Optional[str] = None
    analisis_solicitados: Optional[str] = None
    protocolo_utilizar: Optional[str] = None
    id_usuario_envio: int
    alerta_testigo_por_vencer: bool = False
    alerta_reorden: bool = False


class RemitoResponse(BaseModel):
    codigo_muestra: str
    tipo_referencia: str
    nro_referencia: str
    erp_CODART: str
    erp_DESART: str
    fecha_muestreo: datetime
    laboratorio_nombre: str
    laboratorio_direccion: Optional[str] = None
    fecha_despacho: datetime
    temperatura_transporte: Optional[str] = None
    nro_remito: Optional[str] = None
    transportista: Optional[str] = None
    analisis_solicitados: Optional[str] = None
    protocolo_utilizar: Optional[str] = None
    testigo_codigo: Optional[str] = None
    testigo_nombre: Optional[str] = None
    cantidad_testigo: Optional[float] = None
