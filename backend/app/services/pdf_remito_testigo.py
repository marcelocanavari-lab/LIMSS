"""
Generación del PDF del remito de envío de testigos/estándares a laboratorio
externo para recertificación (distinto del remito de muestra -- ver
pdf_remito.py). Mismo enfoque de dibujo directo con reportlab (canvas), sin
Platypus, consistente con el resto del proyecto.

El PDF final se arma en dos etapas: primero reportlab dibuja el remito (dos
copias, ORIGINAL y DUPLICADO), después pypdf concatena a continuación el
certificado analítico de cada testigo enviado que tenga uno cargado.
"""
import io
import os
from datetime import date
from typing import Optional

from pypdf import PdfReader, PdfWriter
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.pdfgen import canvas

from app.services import storage


def _fmt_fecha(valor) -> str:
    if not valor:
        return "—"
    if isinstance(valor, str):
        valor = date.fromisoformat(valor)
    return valor.strftime("%d/%m/%Y")


def _texto(valor) -> str:
    if valor in (None, ""):
        return "—"
    return str(valor)


def _dibujar_copia(c: canvas.Canvas, laboratorio, remito, nro_remito: str, testigos: list, etiqueta_copia: str, contacto=None):
    _, height = A4
    x = 2 * cm
    y = height - 2 * cm

    def titulo(texto: str, tam: int = 14):
        nonlocal y
        c.setFont("Helvetica-Bold", tam)
        c.drawString(x, y, texto)
        y -= 0.7 * cm

    def subtitulo(texto: str):
        nonlocal y
        y -= 0.25 * cm
        c.setFont("Helvetica-Bold", 11)
        c.drawString(x, y, texto)
        y -= 0.15 * cm
        c.line(x, y, x + 17 * cm, y)
        y -= 0.5 * cm

    def campo(etiqueta: str, valor: Optional[str]):
        nonlocal y
        c.setFont("Helvetica-Bold", 9)
        c.drawString(x, y, f"{etiqueta}:")
        c.setFont("Helvetica", 9)
        c.drawString(x + 4.5 * cm, y, valor)
        y -= 0.5 * cm

    titulo("Laboratorio Lamar SRL", 13)
    titulo("Remito de Envío de Estándares", 13)
    c.setFont("Helvetica-Bold", 10)
    c.drawString(x, y, etiqueta_copia)
    y -= 0.6 * cm
    c.setFont("Helvetica", 10)
    c.drawString(x, y, f"N° {nro_remito}")
    y -= 0.9 * cm

    subtitulo("Laboratorio destino")
    campo("Nombre", _texto(laboratorio.nombre))
    campo("Contacto", _texto(laboratorio.contacto))
    campo("Dirección", _texto(laboratorio.direccion))
    campo("Email", _texto(laboratorio.email))
    campo("Teléfono", _texto(laboratorio.telefono))
    if contacto is not None:
        valor_aa = contacto.nombre
        if contacto.cargo:
            valor_aa += f" — {contacto.cargo}"
        campo("A/A", valor_aa)
    campo("Fecha de envío", _fmt_fecha(remito.fecha_envio))
    if remito.observaciones:
        campo("Observaciones", _texto(remito.observaciones))

    subtitulo("Testigos enviados")

    columnas = [
        ("N° IR", x, 3 * cm),
        ("Nombre", x + 3 * cm, 6 * cm),
        ("Lote", x + 9 * cm, 3 * cm),
        ("Vencimiento", x + 12 * cm, 2.5 * cm),
        ("Cantidad enviada", x + 14.5 * cm, 2.5 * cm),
    ]
    c.setFont("Helvetica-Bold", 8)
    for etiqueta, cx, _ in columnas:
        c.drawString(cx, y, etiqueta)
    y -= 0.15 * cm
    c.line(x, y, x + 17 * cm, y)
    y -= 0.45 * cm

    c.setFont("Helvetica", 8)
    for item, testigo in testigos:
        if y < 3 * cm:
            c.showPage()
            y = height - 2 * cm
            c.setFont("Helvetica", 8)
        valores = [
            _texto(testigo.nro_ir),
            _texto(testigo.nombre),
            _texto(testigo.nro_lote),
            _fmt_fecha(testigo.fecha_vencimiento),
            f"{item.cantidad_enviada} {item.unidad}",
        ]
        for (etiqueta, cx, ancho), valor in zip(columnas, valores):
            c.drawString(cx, y, valor[: int(ancho / 0.17)])
        y -= 0.45 * cm

    y -= 0.3 * cm
    c.line(x, y, x + 17 * cm, y)

    y -= 3 * cm
    c.line(x, y, x + 8 * cm, y)
    y -= 0.4 * cm
    c.setFont("Helvetica", 9)
    c.drawString(x, y, "Firma y aclaración")
    y -= 0.5 * cm
    c.drawString(x, y, "Fecha: ___/___/______")

    c.showPage()


def generar_pdf_remito_testigo(laboratorio, remito, nro_remito: str, testigos: list, contacto=None) -> bytes:
    """`laboratorio`: fila de lims_laboratorios. `remito`: RemitoTestigoCreate.
    `testigos`: lista de tuplas (item: TestigoEnvioRemito, testigo: fila de lims_testigos).
    `contacto`: fila de lims_laboratorio_contactos si se eligió uno, o None.

    El PDF resultante trae, en orden: copia ORIGINAL, copia DUPLICADO, y
    después una página por cada certificado analítico (pdf_certificado) de
    los testigos incluidos que tengan uno cargado."""
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    _dibujar_copia(c, laboratorio, remito, nro_remito, testigos, "ORIGINAL - Para el laboratorio", contacto)
    _dibujar_copia(c, laboratorio, remito, nro_remito, testigos, "DUPLICADO - Para archivo interno", contacto)
    c.save()

    writer = PdfWriter()
    for page in PdfReader(io.BytesIO(buffer.getvalue())).pages:
        writer.add_page(page)

    for _, testigo in testigos:
        if not testigo.pdf_certificado:
            continue
        ruta_abs = storage.ruta_absoluta(testigo.pdf_certificado)
        if not os.path.exists(ruta_abs):
            continue
        try:
            for page in PdfReader(ruta_abs).pages:
                writer.add_page(page)
        except Exception:
            # Certificado ilegible/corrupto: no debe impedir generar el remito.
            continue

    salida = io.BytesIO()
    writer.write(salida)
    return salida.getvalue()
