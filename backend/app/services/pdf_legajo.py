"""
"Legajo completo" de una muestra: el Recorrido de Muestra (ver
pdf_recorrido.py) seguido de los documentos adjuntos reales que el usuario
haya elegido incluir (protocolo del proveedor, protocolo del laboratorio
externo por cada envío, factura/remito del proveedor) -- todo combinado en
un único PDF descargable, con una página separadora antes de cada adjunto
para identificar de qué documento se trata (se están concatenando archivos
de origen distinto).

Reutiliza reportlab (ya usado en todo el proyecto) para dibujar las páginas
separadoras y para convertir a PDF los adjuntos que se cargaron como imagen
(jpg/png) -- reportlab.lib.utils.ImageReader ya trae ese soporte via Pillow,
que ya es una dependencia transitiva instalada (no hace falta sumar nada al
requirements.txt). pypdf (también ya usado, ver pdf_remito_testigo.py) hace
el merge final página a página.
"""
import io
import os
from dataclasses import dataclass
from typing import Optional

from pypdf import PdfReader, PdfWriter
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

from app.schemas.recorrido import RecorridoResponse
from app.services.pdf_recorrido import generar_pdf_recorrido

_EXTENSIONES_IMAGEN = {".jpg", ".jpeg", ".png"}


@dataclass
class AdjuntoLegajo:
    titulo: str
    ruta_absoluta: str
    nombre_original: Optional[str] = None


def _dibujar_separador(titulo: str, nombre_original: Optional[str]) -> bytes:
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    ancho_pagina, alto_pagina = A4
    c.setFont("Helvetica", 10)
    c.drawString(1.5 * cm, alto_pagina - 1.8 * cm, "Laboratorio Lamar SRL — Legajo completo")
    c.setFont("Helvetica-Bold", 18)
    c.drawCentredString(ancho_pagina / 2, alto_pagina / 2 + 0.4 * cm, titulo)
    if nombre_original:
        c.setFont("Helvetica", 10)
        c.drawCentredString(ancho_pagina / 2, alto_pagina / 2 - 0.5 * cm, nombre_original)
    c.showPage()
    c.save()
    return buffer.getvalue()


def imagen_a_pdf(ruta_absoluta: str) -> bytes:
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    ancho_pagina, alto_pagina = A4
    margen = 1.5 * cm
    max_ancho = ancho_pagina - 2 * margen
    max_alto = alto_pagina - 2 * margen

    img = ImageReader(ruta_absoluta)
    ancho_img, alto_img = img.getSize()
    escala = min(max_ancho / ancho_img, max_alto / alto_img)
    ancho_final = ancho_img * escala
    alto_final = alto_img * escala
    x = (ancho_pagina - ancho_final) / 2
    y = (alto_pagina - alto_final) / 2
    c.drawImage(img, x, y, width=ancho_final, height=alto_final, preserveAspectRatio=True, anchor="c")
    c.showPage()
    c.save()
    return buffer.getvalue()


def paginas_de_adjunto(ruta_absoluta: str) -> list:
    """Lista de páginas (pypdf) de un adjunto -- convierte a PDF primero si
    es una imagen. Devuelve [] si el archivo no existe o no se puede leer
    (adjunto corrupto/ilegible): no debe impedir generar el resto del
    legajo, ver el criterio ya usado en generar_pdf_remito_testigo. Público
    porque también lo reutiliza generar_remito (envios.py) para adjuntar el
    COAS del proveedor a la copia del remito que va al laboratorio."""
    if not os.path.exists(ruta_absoluta):
        return []
    extension = os.path.splitext(ruta_absoluta)[1].lower()
    try:
        if extension in _EXTENSIONES_IMAGEN:
            return list(PdfReader(io.BytesIO(imagen_a_pdf(ruta_absoluta))).pages)
        return list(PdfReader(ruta_absoluta).pages)
    except Exception:
        return []


def generar_pdf_legajo(recorrido: RecorridoResponse, adjuntos: list[AdjuntoLegajo]) -> bytes:
    """El Recorrido de Muestra siempre va primero y siempre se incluye; los
    `adjuntos` son las secciones opcionales ya resueltas por el caller
    (endpoint) según qué checkboxes tildó el usuario -- acá no se decide
    qué incluir, solo se arma el PDF final con lo que llega."""
    writer = PdfWriter()
    for page in PdfReader(io.BytesIO(generar_pdf_recorrido(recorrido))).pages:
        writer.add_page(page)

    for adjunto in adjuntos:
        paginas = paginas_de_adjunto(adjunto.ruta_absoluta)
        if not paginas:
            continue
        for page in PdfReader(io.BytesIO(_dibujar_separador(adjunto.titulo, adjunto.nombre_original))).pages:
            writer.add_page(page)
        for page in paginas:
            writer.add_page(page)

    salida = io.BytesIO()
    writer.write(salida)
    return salida.getvalue()
