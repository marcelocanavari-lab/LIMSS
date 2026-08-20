from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


# ── Cajas ──────────────────────────────────────────────────────

class CajaCreate(BaseModel):
    codigo: str = Field(..., min_length=1, max_length=20)
    ubicacion: Optional[str] = Field(None, max_length=100)
    observaciones: Optional[str] = Field(None, max_length=500)


class CajaResponse(BaseModel):
    id_caja: int
    codigo: str
    ubicacion: Optional[str] = None
    estado: str
    fecha_apertura: datetime
    fecha_cierre: Optional[datetime] = None
    usuario_apertura_nombre: str
    usuario_cierre_nombre: Optional[str] = None
    observaciones: Optional[str] = None
    cantidad_muestras: int = 0


# ── Muestras dentro de una caja ──────────────────────────────────

class MuestraEnCajaResponse(BaseModel):
    id: int
    id_caja: int
    id_muestra: int
    codigo_muestra: str
    erp_CODART: str
    erp_DESART: str
    erp_nro_ir: Optional[str] = None
    fecha_ingreso: datetime
    usuario_ingreso_nombre: str
    fecha_retiro: Optional[datetime] = None
    usuario_retiro_nombre: Optional[str] = None


class CajaDetalleResponse(CajaResponse):
    muestras: list[MuestraEnCajaResponse] = []


# ── Contramuestras libres (sin caja activa) para agregar ──────────

class MuestraDisponibleResponse(BaseModel):
    id_muestra: int
    codigo_muestra: str
    erp_CODART: str
    erp_DESART: str
    erp_nro_ir: Optional[str] = None
    fecha_muestreo: datetime


# ── Alta múltiple de muestras en una caja ──────────────────────────

class AgregarMuestrasBody(BaseModel):
    id_muestras: list[int] = Field(..., min_length=1)


class MuestraRechazada(BaseModel):
    id_muestra: int
    codigo_muestra: Optional[str] = None
    motivo: str


class AgregarMuestrasResponse(BaseModel):
    agregadas: list[MuestraEnCajaResponse] = []
    # Normalmente vacío -- la pantalla solo ofrece contramuestras libres
    # para elegir, así que "ya está en otra caja" no debería poder pasar
    # desde acá. Puede darse por una condición de carrera (dos personas
    # cargando la misma muestra a la vez) o por muestras no encontradas.
    rechazadas: list[MuestraRechazada] = []


# ── Reporte 4.3: en qué cajas está un producto ───────────────────

class CajaDeProducto(BaseModel):
    id_caja: int
    codigo_caja: str
    estado_caja: str
    id_muestra: int
    codigo_muestra: str
    erp_CODART: str
    erp_DESART: str
    fecha_ingreso: datetime
