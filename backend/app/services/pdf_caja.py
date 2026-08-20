"""
Etiqueta de caja del Archivo de Contramuestras -- a diferencia de las
etiquetas de muestra (chicas, varias por hoja A4 en grilla, ver
pdf_solicitud_muestreo.py), esta es UNA etiqueta por hoja A4 completa: se
pega en la caja física y tiene que leerse de lejos, no ahorrar papel.

Mismo patrón de dibujo directo con reportlab (canvas), sin Platypus,
consistente con el resto del proyecto. El QR usa el soporte nativo de
reportlab (reportlab.graphics.barcode.qr), igual que las etiquetas de
muestra -- no hace falta una librería aparte.
"""
import io
from datetime import datetime

from reportlab.graphics import renderPDF
from reportlab.graphics.barcode.qr import QrCodeWidget
from reportlab.graphics.shapes import Drawing
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas

_FUENTE_CODIGO_MAX = 72
_FUENTE_CODIGO_MIN = 24


def _dibujar_qr(c: canvas.Canvas, valor: str, x: float, y: float, tamano: float) -> None:
    qr_widget = QrCodeWidget(valor)
    x0, y0, x1, y1 = qr_widget.getBounds()
    w, h = x1 - x0, y1 - y0
    d = Drawing(tamano, tamano, transform=[tamano / w, 0, 0, tamano / h, 0, 0])
    d.add(qr_widget)
    renderPDF.draw(d, c, x, y)


def _tamano_fuente_codigo(texto: str, ancho_max: float) -> int:
    """El código de caja no tiene longitud fija (el campo es editable) --
    en vez de truncarlo (perdería legibilidad, justo lo que esta etiqueta
    necesita) se achica la fuente hasta que entre en el ancho disponible,
    mismo criterio de "medir con stringWidth" que _truncar_a_ancho en
    pdf_solicitud_muestreo.py, pero ajustando tamaño en vez de texto."""
    tam = _FUENTE_CODIGO_MAX
    while tam > _FUENTE_CODIGO_MIN and stringWidth(texto, "Helvetica-Bold", tam) > ancho_max:
        tam -= 2
    return tam


def _dibujar_etiqueta_caja(c: canvas.Canvas, caja) -> None:
    ancho, alto = A4
    margen = 2 * cm

    c.setFont("Helvetica-Bold", 16)
    c.drawCentredString(ancho / 2, alto - 3 * cm, "ARCHIVO DE CONTRAMUESTRAS")
    c.setLineWidth(1)
    c.line(margen, alto - 3.4 * cm, ancho - margen, alto - 3.4 * cm)

    fuente_codigo = _tamano_fuente_codigo(caja.codigo, ancho - 2 * margen)
    c.setFont("Helvetica-Bold", fuente_codigo)
    c.drawCentredString(ancho / 2, alto / 2 + 1 * cm, caja.codigo)

    qr_tamano = 5 * cm
    _dibujar_qr(c, caja.codigo, ancho / 2 - qr_tamano / 2, alto / 2 - 7 * cm, qr_tamano)

    c.setFont("Helvetica", 14)
    y = alto / 2 - 8 * cm
    c.drawCentredString(ancho / 2, y, f"Ubicación: {caja.ubicacion or '(sin especificar)'}")
    y -= 0.9 * cm
    c.drawCentredString(ancho / 2, y, f"Apertura: {caja.fecha_apertura.strftime('%d/%m/%Y')}")

    c.setFont("Helvetica", 9)
    c.drawCentredString(ancho / 2, 1.5 * cm, f"Etiqueta generada el {datetime.now().strftime('%d/%m/%Y %H:%M')}")


def generar_pdf_etiquetas_cajas(cajas: list) -> bytes:
    """Una página A4 por caja -- al revés del criterio de "menos páginas"
    de otros reportes: acá el objetivo es que se lea bien de lejos, no
    ahorrar papel, así que nunca se aprietan varias etiquetas en una hoja."""
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    for i, caja in enumerate(cajas):
        if i > 0:
            c.showPage()
        _dibujar_etiqueta_caja(c, caja)
    c.save()
    return buffer.getvalue()
