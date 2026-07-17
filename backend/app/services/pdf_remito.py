"""
Generación del PDF del remito de envío a laboratorio externo (REQ-ENV-004).

Dibujo directo con reportlab (canvas), sin Platypus/tablas: el remito es un
documento corto de campos clave-valor, no necesita un motor de layout
complejo. Se eligió reportlab sobre weasyprint porque es puro Python
(instalable con pip sin dependencias nativas de Cairo/Pango), más simple de
desplegar en un servidor Windows.
"""
import io
from typing import Optional

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.pdfgen import canvas


def _fmt_fecha(valor) -> str:
    if not valor:
        return "—"
    return valor.strftime("%d/%m/%Y")


def _fmt_fecha_hora(valor) -> str:
    if not valor:
        return "—"
    return valor.strftime("%d/%m/%Y %H:%M")


def _texto(valor) -> str:
    if valor in (None, ""):
        return "—"
    return str(valor)


def generar_pdf_remito(datos, nro_remito_interno: str) -> bytes:
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    _, height = A4
    x = 2 * cm
    y = height - 2 * cm

    def titulo(texto: str):
        nonlocal y
        c.setFont("Helvetica-Bold", 15)
        c.drawString(x, y, texto)
        y -= 0.8 * cm

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

    titulo("REMITO DE ENVÍO A LABORATORIO EXTERNO")
    c.setFont("Helvetica", 10)
    c.drawString(x, y, f"N° {nro_remito_interno}")
    y -= 0.9 * cm

    subtitulo("Laboratorio destino")
    campo("Nombre", _texto(datos.laboratorio_nombre))
    campo("Dirección", _texto(datos.laboratorio_direccion))
    campo("Contacto", _texto(datos.laboratorio_contacto))

    subtitulo("Muestra")
    campo("ID de Muestra", _texto(datos.codigo_muestra))
    campo("Material", f"{datos.erp_CODART} - {datos.erp_DESART}")
    campo("IR" if datos.tipo_referencia == "ir" else "Lote", _texto(datos.nro_referencia))
    campo("Fecha de muestreo", _fmt_fecha(datos.fecha_muestreo))
    campo("Muestreador", _texto(datos.usuario_muestreo_nombre))

    subtitulo("Análisis")
    campo("Análisis a realizar", _texto(datos.analisis_solicitados))
    campo("Protocolo a utilizar", _texto(datos.protocolo_utilizar))

    if datos.testigo_codigo:
        subtitulo("Testigo asignado")
        campo("Código", _texto(datos.testigo_codigo))
        campo("Nombre", _texto(datos.testigo_nombre))
        campo("Lote", _texto(datos.testigo_nro_lote))
        campo("Vencimiento", _fmt_fecha(datos.testigo_fecha_vencimiento))
        campo("Cantidad enviada", _texto(datos.cantidad_testigo))

    subtitulo("Datos del envío")
    campo("Fecha de despacho", _fmt_fecha_hora(datos.fecha_despacho))
    campo("Temperatura de transporte", _texto(datos.temperatura_transporte))
    campo("Transportista", _texto(datos.transportista))
    campo("N° remito/guía externo", _texto(datos.nro_remito))

    y -= 1.2 * cm
    c.line(x, y, x + 6 * cm, y)
    y -= 0.4 * cm
    c.setFont("Helvetica", 8)
    c.drawString(x, y, "Firma")

    c.showPage()
    c.save()
    return buffer.getvalue()
