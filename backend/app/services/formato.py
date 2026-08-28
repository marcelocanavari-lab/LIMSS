from decimal import Decimal
from typing import Optional, Union


def formatear_cantidad(valor: Optional[Union[int, float, Decimal]]) -> str:
    if valor is None:
        return ""
    # Corta a 2 decimales y saca los ceros (y el punto) sobrantes: 5.00->5, 5.20->5.2, 5.25->5.25
    texto = f"{valor:.2f}".rstrip("0").rstrip(".")
    return texto if texto else "0"


def formatear_decimal_significativo(valor: Optional[Union[int, float, Decimal]]) -> str:
    """Formatea un valor numérico (límites/valores requeridos de ensayos)
    dejando el último dígito significativo (distinto de cero) seguido de
    exactamente UN cero más -- no se agrega ni se quita nada si el valor ya
    tiene 2 o más decimales significativos. Ejemplos reales de
    lims_especificacion_ensayos (columna DECIMAL(18,4), siempre 4
    decimales aunque el valor sea conceptualmente entero):
        5.100000 -> "5.10"   (1 decimal significativo -> se completa a 2)
        5.125    -> "5.125"  (ya tiene 3, no se toca)
        5.10500  -> "5.105"  (se recortan los ceros de más al final, sin
                              agregar uno nuevo porque ya termina en un
                              dígito distinto de cero)
        5.0000   -> "5.0"    (entero exacto -- caso confirmado con el
                              usuario, un solo cero decimal)
    Sin valor (None), devuelve "—" -- mismo criterio que _texto()."""
    if valor is None:
        return "—"
    entero, _, frac = f"{Decimal(str(valor)):f}".partition(".")
    frac = frac.rstrip("0")
    if frac == "":
        return f"{entero}.0"
    if len(frac) < 2:
        frac = frac.ljust(2, "0")
    return f"{entero}.{frac}"


def normalizar_unidad(valor: Optional[str]) -> Optional[str]:
    """Unidades de medida siempre en minúsculas ("g", "kg", "ml", no "G",
    "KG", "ML") -- se cargan a mano en varios formularios de Datos Maestros
    (especificaciones, testigos, grupos de bultos) y también llegan tal
    cual las tiene el ERP (lims_solicitudes_muestreo.unidad_cantidad, desde
    linea.unidad), que las guarda en mayúsculas. Se normaliza acá, en el
    único lugar donde escribe cada INSERT/UPDATE de estas columnas, en vez
    de en cada pantalla que las muestra, para que el dato quede consistente
    también en exports/reportes que leen directo de la base."""
    if valor is None:
        return None
    limpio = valor.strip()
    return limpio.lower() if limpio else None


def titulo_etiqueta_por_tipo(tipo_muestra: Optional[str]) -> str:
    """Título de la etiqueta de muestra según el tipo confirmado
    (lims_solicitud_muestras.tipo_muestra) -- mismo texto en el PDF
    (pdf_solicitud_muestreo.py) y en la etiqueta SBPL (impresion_sato.py),
    para que ambas versiones se vean como la misma etiqueta. Cualquier tipo
    no contemplado (hoy solo existe 'contramuestra' además de los dos de
    abajo) cae en el texto genérico "CONTRAMUESTRA", igual que ya hacía el
    PDF antes de esta unificación."""
    if tipo_muestra == "analisis":
        return "MUESTRA PARA ANÁLISIS"
    if tipo_muestra == "testigo":
        return "TESTIGO"
    return "CONTRAMUESTRA"


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
