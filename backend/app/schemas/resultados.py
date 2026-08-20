from pydantic import BaseModel, Field
from typing import Optional
from datetime import date, datetime


class EnsayoParaCarga(BaseModel):
    id_espec_ensayo: int
    orden: int
    nombre_ensayo: str
    metodologia: Optional[str] = None
    tipo_dato: str
    limite_inferior: Optional[float] = None
    limite_superior: Optional[float] = None
    unidad_medida: Optional[str] = None
    valor_requerido: Optional[str] = None
    # Criterio concreto de qué hay que verificar en este punto puntual (ej.
    # "debe decir XYZ en el dorso", "el código de barras debe corresponder
    # al artículo") -- visible junto al ensayo mientras se completa el
    # resultado, para no obligar a ir a buscarlo aparte. Opcional, igual
    # que en el resto del sistema (Especificaciones).
    especificacion_texto: Optional[str] = None
    obligatorio: bool
    # Valor ya guardado, si lo hay (resumir una carga o vista de solo lectura)
    valor_numerico: Optional[float] = None
    valor_cualitativo: Optional[str] = None
    dentro_especificacion: Optional[bool] = None


class ProtocoloResponse(BaseModel):
    id_protocolo: int
    nro_protocolo_ext: str
    fecha_emision: date
    pdf_nombre_original: str
    fecha_carga: datetime


class EnvioParaCarga(BaseModel):
    id_envio: int
    id_muestra: int
    codigo_muestra: str
    erp_CODART: str
    erp_DESART: str
    laboratorio_nombre: str
    estado_muestra: str
    # De lims_muestras.tipo_material -- gatea si la pantalla ofrece la
    # comparación de etiquetas con IA (solo Material de Empaque).
    tipo_material: Optional[str] = None
    ensayos: list[EnsayoParaCarga]
    protocolo: Optional[ProtocoloResponse] = None
    # Comparación de etiquetas con IA (solo Material de Empaque) -- UNA sola
    # foto y observación por ENVÍO, no por ensayo: varios ensayos de un
    # mismo envío (texto legal, colores, código de barras) se verifican
    # todos contra la misma foto de la etiqueta recibida. Ver
    # app/services/comparacion_empaque_ia.py.
    observacion_ia: Optional[str] = None
    tiene_imagen_comparacion: bool = False


class EnvioPendienteResultados(BaseModel):
    id_envio: int
    nro_remito_interno: Optional[str] = None
    codigo_muestra: str
    erp_DESART: str
    laboratorio_nombre: str
    ensayos_pendientes: int
    total_ensayos: int
    fecha_despacho: datetime


class ResultadoInput(BaseModel):
    id_espec_ensayo: int
    valor_numerico: Optional[float] = None
    valor_cualitativo: Optional[str] = None


class GuardarResultadosResponse(BaseModel):
    id_envio: int
    hay_oos: bool
