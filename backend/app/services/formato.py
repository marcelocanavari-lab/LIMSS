from decimal import Decimal
from typing import Optional, Union


def formatear_cantidad(valor: Optional[Union[int, float, Decimal]]) -> str:
    if valor is None:
        return ""
    # Corta a 2 decimales y saca los ceros (y el punto) sobrantes: 5.00->5, 5.20->5.2, 5.25->5.25
    texto = f"{valor:.2f}".rstrip("0").rstrip(".")
    return texto if texto else "0"


def etiqueta_referencia(tipo_referencia: Optional[str]) -> str:
    """Etiqueta a imprimir junto al número de referencia de una muestra
    (lims_muestras.nro_referencia) según su tipo_referencia -- valores reales
    hoy en la base: 'ir' (Informe de Recepción, materia prima vía ERP) y
    'lote' (lote de producción interna, granel/semi-elaborado/terminado).
    Cualquier otro valor (NULL, o algo no contemplado como 'EBR_PREL') usa un
    texto neutro en vez de asumir "IR" por defecto."""
    if tipo_referencia == "ir":
        return "IR"
    if tipo_referencia == "lote":
        return "LOTE"
    return "Ref"
