from datetime import date, datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field


class FacturaCreate(BaseModel):
    id_laboratorio: int
    nro_factura: str = Field(..., min_length=1, max_length=50)
    fecha_factura: date
    fecha_recepcion: Optional[date] = None
    monto: float = Field(..., ge=0)
    moneda: Literal["ARS", "USD", "EUR"] = "ARS"
    descripcion: Optional[str] = Field(None, max_length=500)
    id_envios: list[int] = []


class FacturaUpdate(BaseModel):
    nro_factura: str = Field(..., min_length=1, max_length=50)
    fecha_factura: date
    fecha_recepcion: Optional[date] = None
    monto: float = Field(..., ge=0)
    moneda: Literal["ARS", "USD", "EUR"] = "ARS"
    descripcion: Optional[str] = Field(None, max_length=500)
    id_envios: list[int] = []


class FacturaPagoUpdate(BaseModel):
    fecha_pago: date
    nro_comprobante_pago: Optional[str] = Field(None, max_length=50)
    observaciones: Optional[str] = Field(None, max_length=500)


class FacturaAnularUpdate(BaseModel):
    observaciones: Optional[str] = Field(None, max_length=500)


class EnvioFacturaItem(BaseModel):
    id_envio: int
    nro_remito: Optional[str] = None
    codigo_muestra: Optional[str] = None
    fecha_despacho: datetime
    erp_CODART: Optional[str] = None
    erp_DESART: Optional[str] = None
    erp_nro_ir: Optional[str] = None
    cantidad_ensayos: int = 0


class FacturaResponse(BaseModel):
    id_factura: int
    id_laboratorio: int
    laboratorio_nombre: Optional[str] = None
    nro_factura: str
    fecha_factura: date
    fecha_recepcion: Optional[date] = None
    monto: float
    moneda: str
    descripcion: Optional[str] = None
    estado_pago: Literal["pendiente", "pagado", "anulado"]
    fecha_pago: Optional[date] = None
    nro_comprobante_pago: Optional[str] = None
    observaciones: Optional[str] = None
    id_usuario: int
    fecha_carga: datetime
    cantidad_envios: int = 0
    envios: list[EnvioFacturaItem] = []


class FacturaDetalleResponse(FacturaResponse):
    pass


class EnvioSinFacturar(BaseModel):
    id_envio: int
    nro_remito: Optional[str] = None
    codigo_muestra: Optional[str] = None
    fecha_despacho: datetime
    id_laboratorio: int
    laboratorio_nombre: str
    erp_CODART: Optional[str] = None
    erp_DESART: Optional[str] = None
    erp_nro_ir: Optional[str] = None
    cantidad_ensayos: int = 0
