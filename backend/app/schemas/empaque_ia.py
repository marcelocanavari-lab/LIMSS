from datetime import datetime

from pydantic import BaseModel
from typing import Optional


class ReferenciaEmpaqueResponse(BaseModel):
    id_referencia: int
    erp_CODART: str
    nombre_original: str
    fecha_carga: datetime
    usuario_carga_nombre: str


class CompararEtiquetaResponse(BaseModel):
    # Una sola comparación por ENVÍO (no por ensayo) -- varios ensayos de un
    # mismo envío se verifican todos contra la misma foto de etiqueta.
    #
    # Provisorio hasta que se guardan los resultados: este endpoint NO
    # escribe en lims_envios (ver comparar_etiqueta en resultados.py) --
    # devuelve imagen_comparacion_path/observacion_ia para que el frontend
    # los guarde en estado local y los reenvíe recién en POST
    # .../resultados (guardar_resultados), que es quien los persiste.
    id_envio: int
    imagen_comparacion_path: Optional[str] = None
    observacion_ia: Optional[str] = None
    # False cuando el motor no está configurado, la llamada falló, o la
    # referencia activa no es una imagen soportada (ej. PDF) -- para que el
    # frontend distinga "sin diferencias encontradas" de "no se pudo
    # comparar" y muestre el mensaje correcto (ver Carga de Resultados).
    ia_disponible: bool
