"""
Comparación de etiquetas de Material de Empaque (asistencia visual) -- ver
migrations_comparacion_ia_empaque.sql.

Principio central: esto es una ayuda para quien inspecciona, no reemplaza
su criterio. El motor NUNCA decide Cumple/No cumple -- solo describe
diferencias de texto entre la imagen de referencia (arte aprobado) y la
foto de la etiqueta recibida en esta inspección puntual. El Cumple/No
cumple lo completa y firma la persona, igual que siempre (ver
app/api/routes/resultados.py).

Motor actual: OCR local con Tesseract (pytesseract) + diff de texto con
difflib -- gratuito, corre en el propio servidor, sin depender de una API
key paga. Antes se usaba la API de Claude (comparación multimodal
imagen-contra-imagen); si el volumen de diferencias mal detectadas por OCR
resulta alto, se puede volver a esa implementación.

comparar_etiquetas() es el ÚNICO punto que hay que tocar para cambiar de
motor -- recibe las rutas de las dos imágenes ya guardadas en disco (mismo
dato que ya maneja resultados.py) y devuelve el texto de observacion_ia a
guardar, o None si el motor no está disponible en absoluto (Tesseract no
instalado/no encontrado -- análogo al caso "sin API key" de la versión con
Claude). El resto del sistema (endpoint, columnas de base, logging,
comportamiento no bloqueante, frontend) no cambia según qué motor haya
atrás de esta función.
"""
import logging
from typing import Optional

from app.core.config import get_settings

logger = logging.getLogger("comparacion_empaque_ia")

# Ruta al ejecutable de Tesseract: se lee UNA sola vez, al importar el
# módulo, y se configura acá -- tesseract_cmd es un global del lado de la
# librería pytesseract, repetirlo en cada llamada no aporta nada. Se lee de
# Settings (app/core/config.py, campo tesseract_path) igual que el resto de
# la configuración del proyecto -- NO con os.getenv() directo, para que
# quede centralizada en un solo lugar validado al arrancar. Si no está
# configurada, se deja el comportamiento por defecto de pytesseract (buscar
# "tesseract" en el PATH del sistema) como respaldo -- no rompe si alguien
# no configuró la variable, pero la ruta explícita es preferible: no
# depende de que el PATH del servidor esté bien armado (ver .env.example).
try:
    import pytesseract

    _TESSERACT_PATH = get_settings().tesseract_path
    if _TESSERACT_PATH:
        pytesseract.pytesseract.tesseract_cmd = _TESSERACT_PATH
except ImportError:
    # pytesseract no instalado -- comparar_etiquetas() lo reintenta más
    # abajo y cae al camino de "motor no disponible" (None, logueado).
    pass

# Menos de esta cantidad de palabras reconocidas en cualquiera de las dos
# imágenes se considera "el OCR no pudo leer nada útil" (foto borrosa, mal
# enfocada, con poca luz) -- en vez de comparar basura contra basura.
_MIN_PALABRAS_LEGIBLES = 3

# Umbral de similitud (difflib.SequenceMatcher.ratio(), 0 a 1) por encima
# del cual se considera que el texto leído coincide -- no exige una
# igualdad exacta porque el OCR nunca es perfecto letra por letra.
_UMBRAL_COINCIDENCIA = 0.97

_MAX_PALABRAS_EN_RESUMEN = 15


def _extraer_texto(ruta_imagen: str) -> str:
    from PIL import Image
    import pytesseract

    with Image.open(ruta_imagen) as imagen:
        return pytesseract.image_to_string(imagen, lang="spa")


def _normalizar_palabras(texto: str) -> list[str]:
    return [p.strip(".,;:()[]\"'-").lower() for p in texto.split() if p.strip(".,;:()[]\"'-")]


def _resumen_diferencias(palabras_ref: list[str], palabras_nueva: list[str]) -> str:
    import difflib

    ratio = difflib.SequenceMatcher(None, palabras_ref, palabras_nueva).ratio()
    if ratio >= _UMBRAL_COINCIDENCIA:
        return "El texto leído en ambas etiquetas coincide -- no se detectaron diferencias relevantes."

    faltantes = sorted(set(palabras_ref) - set(palabras_nueva))
    nuevas = sorted(set(palabras_nueva) - set(palabras_ref))

    if not faltantes and not nuevas:
        # Mismas palabras pero en otro orden/repetición -- el ratio bajó
        # igual (ej. layout distinto), se avisa sin listar nada puntual.
        return (
            "El texto leído en ambas etiquetas usa las mismas palabras pero con diferencias de "
            "orden o repetición -- revisar manualmente."
        )

    partes = ["Posibles diferencias de texto entre la etiqueta recibida y la referencia:"]
    if faltantes:
        listado = ", ".join(faltantes[:_MAX_PALABRAS_EN_RESUMEN])
        partes.append(f"en la referencia pero NO en la etiqueta nueva: {listado}.")
    if nuevas:
        listado = ", ".join(nuevas[:_MAX_PALABRAS_EN_RESUMEN])
        partes.append(f"en la etiqueta nueva pero NO en la referencia: {listado}.")
    return " ".join(partes)


def comparar_etiquetas(imagen_referencia_path: str, imagen_nueva_path: str, contexto: str = "") -> Optional[str]:
    """Devuelve el texto de observacion_ia a guardar, o None si el motor de
    OCR no está disponible en absoluto (Tesseract no instalado, ejecutable
    no encontrado, librería faltante). Cualquier otro resultado (sin
    diferencias, diferencias encontradas, o advertencia de imagen
    ilegible) se devuelve como texto -- nunca bloquea la carga del
    resultado, y cualquier excepción real queda logueada acá.

    `contexto` es solo para el log de error (ej. "envio=123 espec_ensayo=45").
    """
    try:
        texto_ref = _extraer_texto(imagen_referencia_path)
        texto_nueva = _extraer_texto(imagen_nueva_path)
    except Exception as e:
        # Deliberadamente amplio: pytesseract no instalado, Tesseract.exe no
        # encontrado en TESSERACT_PATH, imagen corrupta/formato no soportado,
        # etc. -- degrada a "sin observación", nunca bloquea la carga del
        # resultado, pero SÍ queda logueado acá para poder diagnosticar.
        logger.error("Error en comparación de etiqueta con OCR (%s): %s", contexto, e, exc_info=True)
        return None

    palabras_ref = _normalizar_palabras(texto_ref)
    palabras_nueva = _normalizar_palabras(texto_nueva)

    if len(palabras_ref) < _MIN_PALABRAS_LEGIBLES or len(palabras_nueva) < _MIN_PALABRAS_LEGIBLES:
        logger.warning(
            "Comparación de etiqueta (%s): OCR leyó muy poco texto (referencia=%d palabras, nueva=%d palabras)",
            contexto, len(palabras_ref), len(palabras_nueva),
        )
        return (
            "No se pudo leer texto claro en una de las imágenes (foto borrosa, mal enfocada o con "
            "poca luz) -- revisá la comparación manualmente."
        )

    return _resumen_diferencias(palabras_ref, palabras_nueva)
