"""
Generación del PDF del remito de envío a laboratorio externo (REQ-ENV-004).

Dibujo directo con reportlab (canvas), sin Platypus/tablas: son documentos
cortos de campos clave-valor más un par de tablas simples, no necesitan un
motor de layout complejo. Se eligió reportlab sobre weasyprint porque es
puro Python (instalable con pip sin dependencias nativas de Cairo/Pango),
más simple de desplegar en un servidor Windows.

El PDF trae dos copias idénticas (ORIGINAL / DUPLICADO), cada una con su
propia paginación si el contenido no entra en una hoja.
"""
import io
from datetime import date
from typing import Optional

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas
from reportlab.platypus import Paragraph

_ESTILO_ESPECIFICACION = ParagraphStyle(
    "especificacion", fontName="Helvetica", fontSize=8, leading=9.5,
)


def _escapar_html(texto: str) -> str:
    """Paragraph interpreta un subconjunto de HTML -- escapar antes de pasarle
    texto libre que puede venir de la especificación cargada por el usuario."""
    return texto.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _fmt_fecha(valor) -> str:
    if not valor:
        return "—"
    if isinstance(valor, str):
        # El driver ODBC devuelve columnas DATE (a diferencia de DATETIME)
        # como str en este entorno; se normaliza antes de formatear.
        valor = date.fromisoformat(valor)
    return valor.strftime("%d/%m/%Y")


def _fmt_fecha_hora(valor) -> str:
    if not valor:
        return "—"
    return valor.strftime("%d/%m/%Y %H:%M")


def _fmt_vencimiento_lote(valor) -> str:
    """A diferencia de _fmt_fecha, acá "sin dato" tiene un significado propio
    (el ERP no tiene vencimiento cargado para ese lote/IR) y se distingue del
    "—" genérico de otros campos vacíos."""
    if not valor:
        return "Sin vencimiento"
    return _fmt_fecha(valor)


def _texto(valor) -> str:
    if valor in (None, ""):
        return "—"
    return str(valor)


_LABEL_X_OFFSET = 5 * cm  # separación mínima etiqueta -> valor


def _dibujar_copia(
    c: canvas.Canvas, datos, nro_remito_interno: str,
    ensayos: list, testigos: list, principios_activos: list,
    vencimiento_lote, etiqueta_copia: str,
):
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

    def salto_pagina_si_hace_falta(espacio_necesario: float):
        nonlocal y
        if y - espacio_necesario < 3 * cm:
            c.showPage()
            y = height - 2 * cm

    def campo(etiqueta: str, valor: str):
        nonlocal y
        c.setFont("Helvetica-Bold", 9)
        c.drawString(x, y, f"{etiqueta}:")
        ancho_etiqueta = stringWidth(f"{etiqueta}: ", "Helvetica-Bold", 9)
        offset = max(_LABEL_X_OFFSET, ancho_etiqueta + 0.3 * cm)
        c.setFont("Helvetica", 9)
        c.drawString(x + offset, y, valor)
        y -= 0.5 * cm

    def campo_multilinea(etiqueta: str, valores: list):
        """Etiqueta fija a la izquierda; un valor por línea a la derecha --
        para campos con varios componentes (principios activos)."""
        nonlocal y
        if not valores:
            return
        c.setFont("Helvetica-Bold", 9)
        c.drawString(x, y, f"{etiqueta}:")
        ancho_etiqueta = stringWidth(f"{etiqueta}: ", "Helvetica-Bold", 9)
        offset = max(_LABEL_X_OFFSET, ancho_etiqueta + 0.3 * cm)
        c.setFont("Helvetica", 9)
        for i, valor in enumerate(valores):
            salto_pagina_si_hace_falta(0.5 * cm)
            c.drawString(x + offset, y, valor)
            if i < len(valores) - 1:
                y -= 0.42 * cm
        y -= 0.5 * cm

    titulo("Laboratorio Lamar SRL")
    titulo("REMITO DE ENVÍO A LABORATORIO EXTERNO")
    c.setFont("Helvetica-Bold", 10)
    c.drawString(x, y, etiqueta_copia)
    y -= 0.6 * cm
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
    campo("Vencimiento del lote", _fmt_vencimiento_lote(vencimiento_lote))
    campo("Muestreador", _texto(datos.usuario_muestreo_nombre))
    if datos.cantidad_enviada is not None:
        campo("Cantidad de muestra enviada", f"{datos.cantidad_enviada} {datos.unidad_enviada or ''}".strip())
    if principios_activos:
        campo_multilinea(
            "Principio/s activo/s",
            [f"{p['nombre']} ({p['codigo']})" for p in principios_activos],
        )
        campo("Concentración declarada", " / ".join(p["concentracion"] for p in principios_activos))

    if ensayos:
        subtitulo("Análisis solicitados")
        salto_pagina_si_hace_falta(1.5 * cm)
        col_ensayo = (x, 4.3 * cm)
        col_metodo = (x + 4.3 * cm, 4 * cm)
        col_tipo = (x + 8.3 * cm, 2.2 * cm)
        col_espec_x, col_espec_w = x + 10.5 * cm, 6.5 * cm  # resto del ancho de tabla (17cm)

        c.setFont("Helvetica-Bold", 8)
        c.drawString(col_ensayo[0], y, "Ensayo")
        c.drawString(col_metodo[0], y, "Metodología/Técnica")
        c.drawString(col_tipo[0], y, "Tipo")
        c.drawString(col_espec_x, y, "Especificación/Límites")
        y -= 0.15 * cm
        c.line(x, y, x + 17 * cm, y)
        y -= 0.45 * cm

        for e in ensayos:
            tipo_legible = "Numérico" if e.tipo_dato == "numerico" else "Cualitativo"
            if e.tipo_dato == "numerico":
                unidad = f" {e.unidad_medida}" if e.unidad_medida else ""
                especificacion = f"{_texto(e.limite_inferior)} a {_texto(e.limite_superior)}{unidad}"
            else:
                especificacion = e.valor_requerido or e.especificacion_texto or "—"

            # Especificación/Límites puede ser texto largo -- Paragraph lo
            # divide en varias líneas dentro del ancho de la columna; el resto
            # de las columnas son de una sola línea, así que la altura de la
            # fila la termina marcando esta celda.
            parrafo = Paragraph(_escapar_html(str(especificacion)), _ESTILO_ESPECIFICACION)
            _, alto_parrafo = parrafo.wrap(col_espec_w - 0.2 * cm, 1000)
            alto_fila = max(0.45 * cm, alto_parrafo + 0.15 * cm)

            salto_pagina_si_hace_falta(alto_fila)

            c.setFont("Helvetica", 8)
            c.drawString(col_ensayo[0], y, e.nombre_ensayo[: int(col_ensayo[1] / 0.17)])
            c.drawString(col_metodo[0], y, _texto(e.metodologia)[: int(col_metodo[1] / 0.17)])
            c.drawString(col_tipo[0], y, tipo_legible)
            parrafo.drawOn(c, col_espec_x, y - alto_parrafo)

            y -= alto_fila

    if testigos:
        subtitulo("Testigos a utilizar")
        salto_pagina_si_hace_falta(1.5 * cm)
        columnas_t = [
            ("N° IR", x, 2 * cm),
            ("Nombre", x + 2 * cm, 4.3 * cm),
            ("Lote", x + 6.3 * cm, 2.2 * cm),
            ("Vencimiento", x + 8.5 * cm, 2.2 * cm),
            ("Cantidad", x + 10.7 * cm, 1.8 * cm),
            ("Unidad", x + 12.5 * cm, 1.5 * cm),
            ("Fecha envío al lab.", x + 14 * cm, 3 * cm),
        ]
        c.setFont("Helvetica-Bold", 8)
        for etiqueta, cx, _ in columnas_t:
            c.drawString(cx, y, etiqueta)
        y -= 0.15 * cm
        c.line(x, y, x + 17 * cm, y)
        y -= 0.45 * cm

        c.setFont("Helvetica", 8)
        for t in testigos:
            salto_pagina_si_hace_falta(0.45 * cm)
            valores = [
                _texto(t.nro_ir), t.nombre, _texto(t.nro_lote), _fmt_fecha(t.fecha_vencimiento),
                _texto(t.cantidad), _texto(t.unidad_medida), _fmt_fecha_hora(datos.fecha_despacho),
            ]
            for (_, cx, ancho), valor in zip(columnas_t, valores):
                c.drawString(cx, y, str(valor)[: int(ancho / 0.17)])
            y -= 0.45 * cm

    subtitulo("Datos del envío")
    campo("Fecha de despacho", _fmt_fecha_hora(datos.fecha_despacho))
    campo("Temperatura de transporte", _texto(datos.temperatura_transporte))
    campo("Transportista", _texto(datos.transportista))
    campo("N° remito/guía externo", _texto(datos.nro_remito))

    salto_pagina_si_hace_falta(4.4 * cm)
    y -= 0.3 * cm
    c.line(x, y, x + 17 * cm, y)

    y -= 4 * cm
    c.line(x, y, x + 8 * cm, y)
    y -= 0.4 * cm
    c.setFont("Helvetica", 9)
    c.drawString(x, y, "Firma y aclaración")
    y -= 0.5 * cm
    c.drawString(x, y, "Fecha: ___/___/______")

    c.showPage()


def generar_pdf_remito(
    datos, nro_remito_interno: str,
    ensayos: Optional[list] = None, testigos: Optional[list] = None,
    principios_activos: Optional[list] = None, vencimiento_lote=None,
) -> bytes:
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    for etiqueta_copia in ("ORIGINAL - Para el laboratorio", "DUPLICADO - Para archivo Lamar"):
        _dibujar_copia(
            c, datos, nro_remito_interno, ensayos or [], testigos or [],
            principios_activos or [], vencimiento_lote, etiqueta_copia,
        )
    c.save()
    return buffer.getvalue()
