from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel


class LibroIngresosLinea(BaseModel):
    """Una fila del Libro de Ingresos -- una por muestra de Materia Prima o
    Material de Empaque con numero_analisis asignado (ver
    asignar_numero_analisis_si_corresponde en app/services/erp_materiales.py).
    Columnas en el orden pedido."""
    numero_analisis: int
    fecha_ingreso: Optional[date] = None
    nro_ir: Optional[str] = None
    # None si no hay fecha real cargada, o si es el sentinel del ERP
    # (1899-12-30) -- ver normalizar_fecha_sentinel en erp_ir.py.
    fecha_vencimiento: Optional[date] = None
    erp_codart: Optional[str] = None
    erp_desart: Optional[str] = None
    proveedor_nombre: Optional[str] = None
    fecha_factura_proveedor: Optional[date] = None
    numero_factura_proveedor: Optional[str] = None
    # "S/L" si la solicitud no tiene lote de proveedor cargado.
    lote_proveedor: str
    cantidad_texto: Optional[str] = None
    # "4 x 50 kg, 1 x 30 kg" (lims_solicitud_bultos) o "N bultos" sin
    # detalle por grupo -- ver _formatear_bultos_detalle.
    bultos_detalle: Optional[str] = None
    usuario_recibio: Optional[str] = None
    usuario_rotulo: Optional[str] = None
    observaciones: Optional[str] = None
    estado_muestra: Optional[str] = None
    usuario_muestreador: Optional[str] = None
    fecha_muestreo: Optional[datetime] = None
