"""
PDFs de la Solicitud de Muestreo para Materias Primas: formulario (2 copias,
igual patrón que pdf_remito.py) y hoja de etiquetas (etiquetas de 7.2x4cm con
QR, en grilla -- ver _ESCALA_ETIQUETA).

Dibujo directo con reportlab (canvas), sin Platypus/tablas -- mismos motivos
que pdf_remito.py: documentos cortos de campos clave-valor, reportlab es
puro Python (sin dependencias nativas) y ya está en requirements.txt. El QR
usa el soporte nativo de reportlab (reportlab.graphics.barcode.qr), no hace
falta una librería aparte.

A diferencia del remito de envío, estos PDFs se generan al vuelo en cada
GET (no se guardan en storage/): reflejan el estado actual de la solicitud
y su especificación, no un documento firmado que deba quedar fijo en el
tiempo.
"""
import io
from datetime import date
from types import SimpleNamespace

from reportlab.graphics import renderPDF
from reportlab.graphics.barcode.qr import QrCodeWidget
from reportlab.graphics.shapes import Drawing
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas
from reportlab.platypus import Paragraph

from app.services.formato import etiqueta_referencia, formatear_cantidad, titulo_etiqueta_por_tipo

_ESTILO_ESPECIFICACION = ParagraphStyle(
    "especificacion_solicitud", fontName="Helvetica", fontSize=8, leading=9.5,
)
_ESTILO_INSTRUCCIONES = ParagraphStyle(
    "instrucciones_solicitud", fontName="Helvetica", fontSize=9, leading=12,
)
# -20% de tamaño respecto a la etiqueta original (9x5cm) -- todas las
# dimensiones de la etiqueta (fuente, márgenes, separación entre líneas) se
# derivan de esta única constante multiplicando el valor original, para que
# el achique quede realmente proporcional en vez de elegir números nuevos a
# mano campo por campo.
_ESCALA_ETIQUETA = 0.8

_ESTILO_NOMBRE_ETIQUETA_GRANDE = ParagraphStyle(
    "nombre_etiqueta_grande", fontName="Helvetica-Bold",
    fontSize=14 * _ESCALA_ETIQUETA, leading=15.5 * _ESCALA_ETIQUETA,
)
_ESTILO_NOMBRE_ETIQUETA_CHICO = ParagraphStyle(
    "nombre_etiqueta_chico", fontName="Helvetica-Bold",
    fontSize=12 * _ESCALA_ETIQUETA, leading=13.5 * _ESCALA_ETIQUETA,
)

_LABEL_X_OFFSET = 5.5 * cm


def _texto(valor) -> str:
    if valor in (None, ""):
        return "—"
    return str(valor)


def _fmt_fecha(valor) -> str:
    if not valor:
        return "—"
    if isinstance(valor, str):
        valor = date.fromisoformat(valor)
    if hasattr(valor, "date"):
        valor = valor.date()
    return valor.strftime("%d/%m/%Y")


def _escapar_html(texto: str) -> str:
    """Paragraph interpreta un subconjunto de HTML -- escapar antes de pasarle
    texto libre que puede venir de la especificación cargada por el usuario."""
    return texto.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _especificacion_texto(e) -> str:
    if e.tipo_dato == "numerico":
        unidad = f" {e.unidad_medida}" if e.unidad_medida else ""
        return f"{_texto(e.limite_inferior)} a {_texto(e.limite_superior)}{unidad}"
    return e.valor_requerido or e.especificacion_texto or "—"


def _cantidad_texto(cantidad, unidad) -> str:
    if cantidad is None:
        return "—"
    return f"{formatear_cantidad(cantidad)} {unidad or ''}".strip()


# ── Formulario (2 copias) ──────────────────────────────────────────

def _dibujar_formulario(c: canvas.Canvas, solicitud, cantidades: dict, ensayos: list, etiqueta_copia: str):
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

    titulo("Laboratorio Lamar SRL")
    titulo("SOLICITUD DE MUESTREO")
    c.setFont("Helvetica-Bold", 10)
    c.drawString(x, y, etiqueta_copia)
    y -= 0.6 * cm
    c.setFont("Helvetica", 10)
    c.drawString(x, y, f"N° Solicitud: {solicitud.nro_solicitud}   |   Fecha: {_fmt_fecha(solicitud.fecha_solicitud)}")
    y -= 0.5 * cm
    c.drawString(x, y, f"Generado por: {solicitud.usuario_qa}")
    y -= 0.9 * cm

    subtitulo("Datos del material")
    campo("N° IR", _texto(solicitud.erp_nro_ir))
    campo("Código", _texto(solicitud.erp_CODART))
    campo("Nombre", _texto(solicitud.erp_DESART))
    campo("Laboratorio de análisis", _texto(solicitud.laboratorio_nombre))

    subtitulo("Cantidades")
    campo("Para análisis", _cantidad_texto(cantidades.get("cantidad_muestra"), cantidades.get("unidad_muestra")))
    campo("Para contramuestra", _cantidad_texto(cantidades.get("cantidad_contramuestra"), cantidades.get("unidad_contramuestra")))

    if ensayos:
        subtitulo("Ensayos a realizar")
        salto_pagina_si_hace_falta(1.5 * cm)
        col_ensayo = (x, 5 * cm)
        col_metodo = (x + 5 * cm, 4 * cm)
        col_espec_x, col_espec_w = x + 9 * cm, 8 * cm

        c.setFont("Helvetica-Bold", 8)
        c.drawString(col_ensayo[0], y, "Ensayo")
        c.drawString(col_metodo[0], y, "Metodología")
        c.drawString(col_espec_x, y, "Especificación/Límites")
        y -= 0.15 * cm
        c.line(x, y, x + 17 * cm, y)
        y -= 0.45 * cm

        for e in ensayos:
            especif = _especificacion_texto(e)
            parrafo = Paragraph(_escapar_html(str(especif)), _ESTILO_ESPECIFICACION)
            _, alto_parrafo = parrafo.wrap(col_espec_w - 0.2 * cm, 1000)
            alto_fila = max(0.45 * cm, alto_parrafo + 0.15 * cm)
            salto_pagina_si_hace_falta(alto_fila)

            c.setFont("Helvetica", 8)
            c.drawString(col_ensayo[0], y, e.nombre_ensayo[: int(col_ensayo[1] / 0.17)])
            c.drawString(col_metodo[0], y, _texto(e.metodologia)[: int(col_metodo[1] / 0.17)])
            parrafo.drawOn(c, col_espec_x, y - alto_parrafo + _ESTILO_ESPECIFICACION.fontSize)
            y -= alto_fila
    else:
        subtitulo("Ensayos a realizar")
        c.setFont("Helvetica-Oblique", 9)
        c.drawString(x, y, "Sin ensayos asignados a este laboratorio para esta especificación.")
        y -= 0.6 * cm

    subtitulo("Instrucciones al muestreador")
    instrucciones = (
        "Tomar muestra del IR indicado separando las cantidades especificadas. "
        "Pegar las etiquetas correspondientes en cada frasco."
    )
    parrafo_instr = Paragraph(_escapar_html(instrucciones), _ESTILO_INSTRUCCIONES)
    _, alto_instr = parrafo_instr.wrap(17 * cm, 1000)
    salto_pagina_si_hace_falta(alto_instr + 0.5 * cm)
    parrafo_instr.drawOn(c, x, y - alto_instr)
    y -= alto_instr + 0.6 * cm

    salto_pagina_si_hace_falta(4.4 * cm)
    y -= 0.3 * cm
    c.line(x, y, x + 17 * cm, y)
    y -= 0.6 * cm
    c.setFont("Helvetica-Bold", 10)
    c.drawString(x, y, "Firma del muestreador y fecha de ejecución")

    y -= 1.6 * cm
    c.line(x, y, x + 8 * cm, y)
    y -= 0.4 * cm
    c.setFont("Helvetica", 9)
    c.drawString(x, y, "Firma y aclaración")
    y -= 0.5 * cm
    c.drawString(x, y, "Fecha: ___/___/______")

    c.showPage()


def generar_pdf_formulario(solicitud, cantidades: dict, ensayos: list) -> bytes:
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    for etiqueta_copia in ("ORIGINAL - Para el muestreador", "DUPLICADO - Para archivo QA"):
        _dibujar_formulario(c, solicitud, cantidades, ensayos, etiqueta_copia)
    c.save()
    return buffer.getvalue()


# ── Etiquetas (7.2x4cm con QR, varias por hoja -- ver _grilla_etiquetas) ──

def _dibujar_qr(c: canvas.Canvas, valor: str, x: float, y: float, tamano: float):
    """QR con esquina inferior izquierda en (x, y), tamano x tamano puntos."""
    qr_widget = QrCodeWidget(valor)
    x0, y0, x1, y1 = qr_widget.getBounds()
    w, h = x1 - x0, y1 - y0
    d = Drawing(tamano, tamano, transform=[tamano / w, 0, 0, tamano / h, 0, 0])
    d.add(qr_widget)
    renderPDF.draw(d, c, x, y)


def _truncar_a_ancho(texto: str, fuente: str, tam: float, ancho_max: float) -> str:
    """Trunca por ancho real de texto (no por cantidad de caracteres): con
    varios tamaños de fuente distintos en la misma etiqueta, un límite fijo
    de caracteres queda mal para unos y de sobra para otros."""
    if stringWidth(texto, fuente, tam) <= ancho_max:
        return texto
    while texto and stringWidth(texto + "…", fuente, tam) > ancho_max:
        texto = texto[:-1]
    return f"{texto}…" if texto else "…"


def _parrafo_nombre_articulo(nombre: str, ancho_max: float):
    """Arma el nombre del artículo como Paragraph con wordWrap, en vez de
    truncarlo con "…" -- el nombre completo es información necesaria para el
    muestreador, no algo descartable. Usa hasta 3 líneas; si el nombre es
    largo (>30 caracteres) baja de fuente (ver _ESTILO_NOMBRE_ETIQUETA_CHICO)
    para que entre completo, y solo si aun así no entra en 3 líneas (nombre
    extremo) recorta el final con "…" como último recurso."""
    estilo = _ESTILO_NOMBRE_ETIQUETA_CHICO if len(nombre) > 30 else _ESTILO_NOMBRE_ETIQUETA_GRANDE
    texto = nombre
    while True:
        candidato = texto if texto == nombre else f"{texto}…"
        parrafo = Paragraph(_escapar_html(candidato), estilo)
        _, alto = parrafo.wrap(ancho_max, 1000)
        if len(parrafo.blPara.lines) <= 3 or len(texto) <= 1:
            return parrafo, alto
        texto = texto[:-1]


def _dibujar_etiqueta(
    c: canvas.Canvas, x0: float, y0: float, ancho: float, alto: float,
    titulo_etiqueta: str, solicitud, cantidad_texto: str, laboratorio_nombre: str | None,
    iniciales_muestreador: str | None = None,
):
    # Todo (márgenes, fuentes, separación entre líneas) escala junto con
    # _ESCALA_ETIQUETA -- son los mismos valores que antes multiplicados por
    # el factor de achique, así que las proporciones internas no cambian.
    e = _ESCALA_ETIQUETA
    margen = 0.3 * cm * e
    qr_tam = 2 * cm * e
    ancho_texto_max = ancho - 2 * margen - qr_tam - 0.2 * cm * e

    c.rect(x0, y0, ancho, alto)

    x = x0 + margen
    y = y0 + alto - margen - 0.3 * cm * e

    c.setFont("Helvetica-Bold", 9 * e)
    c.drawString(x, y, titulo_etiqueta)
    y -= 0.42 * cm * e

    c.setFont("Helvetica-Bold", 9 * e)
    c.drawString(x, y, solicitud.nro_solicitud)
    y -= 0.52 * cm * e

    # erp_DESART / erp_CODART / N° IR / Cantidad: campos destacados, letra
    # grande -- son los que el muestreador necesita leer de un vistazo al
    # pegar la etiqueta en el frasco. El nombre puede ser largo: se envuelve
    # en hasta 3 líneas en vez de truncarlo (ver _parrafo_nombre_articulo).
    parrafo_nombre, alto_nombre = _parrafo_nombre_articulo(solicitud.erp_DESART.strip(), ancho_texto_max)
    parrafo_nombre.drawOn(c, x, y - alto_nombre + parrafo_nombre.style.fontSize)
    y -= alto_nombre + 0.15 * cm * e

    c.setFont("Helvetica-Bold", 12 * e)
    c.drawString(x, y, _truncar_a_ancho(solicitud.erp_CODART.strip(), "Helvetica-Bold", 12 * e, ancho_texto_max))
    y -= 0.56 * cm * e

    c.setFont("Helvetica-Bold", 14 * e)
    etiqueta_ref = etiqueta_referencia(getattr(solicitud, "tipo_referencia", "ir"))
    c.drawString(x, y, _truncar_a_ancho(f"{etiqueta_ref}: {solicitud.erp_nro_ir}", "Helvetica-Bold", 14 * e, ancho_texto_max))
    y -= 0.59 * cm * e

    c.setFont("Helvetica-Bold", 13 * e)
    c.drawString(x, y, _truncar_a_ancho(f"Cantidad: {cantidad_texto}", "Helvetica-Bold", 13 * e, ancho_texto_max))
    y -= 0.55 * cm * e

    c.setFont("Helvetica", 9 * e)
    if laboratorio_nombre:
        c.drawString(x, y, _truncar_a_ancho(f"Lab: {laboratorio_nombre}", "Helvetica", 9 * e, ancho_texto_max))
        y -= 0.38 * cm * e
    # Iniciales del muestreador en la misma línea que la fecha (no suma
    # altura a la etiqueta, que ya tiene el espacio bastante ajustado con
    # nombres largos + laboratorio -- ver _parrafo_nombre_articulo).
    fecha_texto = f"Fecha: {_fmt_fecha(solicitud.fecha_solicitud)}"
    if iniciales_muestreador:
        fecha_texto += f"   Muestreador: {iniciales_muestreador}"
    c.drawString(x, y, _truncar_a_ancho(fecha_texto, "Helvetica", 9 * e, ancho_texto_max))

    _dibujar_qr(c, solicitud.nro_solicitud, x0 + ancho - qr_tam - margen, y0 + margen, qr_tam)


# ── Grilla de etiquetas por hoja ────────────────────────────────────
#
# Etiqueta física a _ESCALA_ETIQUETA del tamaño original (9x5cm) -- el
# ancho/alto de la grilla se recalculan a partir de ese tamaño en vez de
# quedar fijos en "2 por hoja": al achicarse la etiqueta entran más por
# página, así que la cantidad de columnas/filas se deriva del espacio
# disponible en A4, no un número elegido a mano.
_ETIQUETA_ANCHO = 9 * cm * _ESCALA_ETIQUETA
_ETIQUETA_ALTO = 5 * cm * _ESCALA_ETIQUETA
_ETIQUETA_MARGEN_PAGINA = 2 * cm
_ETIQUETA_GAP_X = 0.4 * cm
_ETIQUETA_GAP_Y = 0.3 * cm


def _grilla_etiquetas() -> tuple[int, int]:
    """Columnas x filas que entran en una hoja A4 con el tamaño de etiqueta
    y separaciones actuales."""
    ancho_pagina, alto_pagina = A4
    ancho_disponible = ancho_pagina - 2 * _ETIQUETA_MARGEN_PAGINA
    alto_disponible = alto_pagina - 2 * _ETIQUETA_MARGEN_PAGINA
    columnas = max(1, int((ancho_disponible + _ETIQUETA_GAP_X) // (_ETIQUETA_ANCHO + _ETIQUETA_GAP_X)))
    filas = max(1, int((alto_disponible + _ETIQUETA_GAP_Y) // (_ETIQUETA_ALTO + _ETIQUETA_GAP_Y)))
    return columnas, filas


def _posicion_etiqueta(indice_en_pagina: int, columnas: int) -> tuple[float, float]:
    """Esquina inferior izquierda (x0, y0) de la etiqueta en la posición
    `indice_en_pagina` (0-based, se recorre por filas de izquierda a
    derecha) dentro de la grilla actual."""
    _, alto_pagina = A4
    fila, columna = divmod(indice_en_pagina, columnas)
    x0 = _ETIQUETA_MARGEN_PAGINA + columna * (_ETIQUETA_ANCHO + _ETIQUETA_GAP_X)
    y0 = alto_pagina - _ETIQUETA_MARGEN_PAGINA - _ETIQUETA_ALTO - fila * (_ETIQUETA_ALTO + _ETIQUETA_GAP_Y)
    return x0, y0


def _generar_hoja_etiquetas(
    solicitud, items: list[tuple[str, str, str | None]], iniciales_muestreador: str | None,
) -> bytes:
    """`items`: (titulo_etiqueta, cantidad_texto, laboratorio_nombre) por
    etiqueta a dibujar, en orden. Reparte en la grilla calculada por
    _grilla_etiquetas y arranca hoja nueva cuando se llena."""
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    columnas, filas = _grilla_etiquetas()
    por_pagina = columnas * filas

    for i, (titulo, cantidad_texto, laboratorio_nombre) in enumerate(items):
        indice_en_pagina = i % por_pagina
        if i > 0 and indice_en_pagina == 0:
            c.showPage()
        x0, y0 = _posicion_etiqueta(indice_en_pagina, columnas)
        _dibujar_etiqueta(
            c, x0, y0, _ETIQUETA_ANCHO, _ETIQUETA_ALTO, titulo, solicitud, cantidad_texto, laboratorio_nombre,
            iniciales_muestreador,
        )

    c.showPage()
    c.save()
    return buffer.getvalue()


def generar_pdf_etiquetas(solicitud, cantidades: dict, iniciales_muestreador: str | None = None) -> bytes:
    """Modelo legacy de 2 etiquetas fijas (análisis + contramuestra), usado
    como fallback cuando la solicitud no tiene filas confirmadas en
    lims_solicitud_muestras (solicitudes viejas, o entornos donde todavía no
    se corrió esa migración) -- ver generar_pdf_etiquetas_v2 para el modelo
    nuevo de N muestras."""
    cant_analisis = _cantidad_texto(cantidades.get("cantidad_muestra"), cantidades.get("unidad_muestra"))
    cant_contra = _cantidad_texto(cantidades.get("cantidad_contramuestra"), cantidades.get("unidad_contramuestra"))
    items = [
        ("MUESTRA PARA ANÁLISIS", cant_analisis, solicitud.laboratorio_nombre),
        ("CONTRAMUESTRA", cant_contra, None),
    ]
    return _generar_hoja_etiquetas(solicitud, items, iniciales_muestreador)


def generar_pdf_etiquetas_v2(solicitud, muestras: list, iniciales_muestreador: str | None = None) -> bytes:
    """Una etiqueta por cada fila de lims_solicitud_muestras confirmada
    (`muestras`, cada una con .tipo_muestra/.cantidad_real/.unidad/
    .laboratorio_nombre), en la misma grilla que el modelo legacy pero con N
    filas en vez de las 2 fijas (análisis/contramuestra)."""
    items = []
    for m in muestras:
        titulo = titulo_etiqueta_por_tipo(m.tipo_muestra)
        items.append((titulo, _cantidad_texto(float(m.cantidad_real), m.unidad), m.laboratorio_nombre))
    return _generar_hoja_etiquetas(solicitud, items, iniciales_muestreador)


def generar_pdf_etiqueta_muestra(muestra, iniciales_muestreador: str | None = None) -> bytes:
    """Etiqueta simplificada para una muestra SIN Solicitud de Muestreo
    asociada -- creada directamente por "Nueva Muestra" (ver
    descargar_etiquetas_de_muestra en app/api/routes/muestras.py), que no
    pasa por el flujo de Solicitudes de Muestreo y por lo tanto no tiene
    nro_solicitud/laboratorio/cantidades de esa tabla. Una sola etiqueta con
    los datos propios de la muestra (código, artículo, cantidad enviada,
    fecha de muestreo) -- sin desglose análisis/contramuestra ni
    laboratorio, porque esa información no existe para este tipo de
    muestra. _dibujar_etiqueta espera un objeto con los mismos nombres de
    atributo que una fila de solicitud (nro_solicitud/erp_DESART/
    erp_CODART/erp_nro_ir/tipo_referencia/fecha_solicitud); se arma un shim
    en vez de duplicar la función de dibujo."""
    solicitud_shim = SimpleNamespace(
        nro_solicitud=muestra.codigo_muestra,
        erp_DESART=muestra.erp_DESART,
        erp_CODART=muestra.erp_CODART,
        erp_nro_ir=muestra.nro_referencia,
        tipo_referencia=muestra.tipo_referencia,
        fecha_solicitud=muestra.fecha_muestreo,
    )
    cantidad_texto = _cantidad_texto(
        float(muestra.cantidad_enviada) if muestra.cantidad_enviada is not None else None,
        muestra.unidad_enviada,
    )
    items = [("MUESTRA", cantidad_texto, None)]
    return _generar_hoja_etiquetas(solicitud_shim, items, iniciales_muestreador)


# ── Orden de Trabajo de Control de Calidad (P_CC002-1) y ──────────
# ── Planilla de Muestreo de Materias Primas (P_CC002-2) ───────────
#
# Réplica en reportlab de los formularios en papel homónimos -- no hay un
# template/imagen del documento controlado real, así que el texto de
# confidencialidad del pie es un placeholder genérico: conviene pedirle a
# QA el texto exacto del documento controlado y reemplazarlo acá si
# corresponde.

def _encabezado_formulario(c: canvas.Canvas, x: float, y: float, titulo_doc: str, codigo: str, revision: str, etiqueta_copia=None) -> float:
    c.setFont("Helvetica-Bold", 14)
    c.drawString(x, y, "LABORATORIO LAMAR SRL")
    y -= 0.7 * cm
    c.setFont("Helvetica-Bold", 12)
    c.drawString(x, y, titulo_doc)
    y -= 0.55 * cm
    c.setFont("Helvetica", 9)
    c.drawString(x, y, f"Código: {codigo}   |   Revisión: {revision}")
    y -= 0.5 * cm
    if etiqueta_copia:
        c.setFont("Helvetica-Bold", 9)
        c.drawString(x, y, etiqueta_copia)
        y -= 0.6 * cm
    y -= 0.2 * cm
    c.line(x, y, x + 18 * cm, y)
    y -= 0.6 * cm
    return y


def _pie_confidencialidad(c: canvas.Canvas, x: float, y: float):
    c.setFont("Helvetica-Oblique", 7)
    c.drawString(
        x, y,
        "Documento de uso interno de Laboratorio Lamar SRL -- información confidencial, "
        "prohibida su reproducción o divulgación sin autorización.",
    )


def _fila_campos(c: canvas.Canvas, x: float, y: float, pares: list, ancho_total: float, fuente_tam: int = 8):
    """Varios pares etiqueta:valor distribuidos en una sola línea, en
    columnas de ancho igual -- las filas de datos de P_CC002-1/2 traen
    2 o 3 campos por línea."""
    n = len(pares)
    ancho_col = ancho_total / n
    for i, (etiqueta, valor) in enumerate(pares):
        cx = x + i * ancho_col
        c.setFont("Helvetica-Bold", fuente_tam)
        c.drawString(cx, y, f"{etiqueta}:")
        ancho_etiqueta = stringWidth(f"{etiqueta}: ", "Helvetica-Bold", fuente_tam)
        c.setFont("Helvetica", fuente_tam)
        c.drawString(cx + ancho_etiqueta + 0.1 * cm, y, _texto(valor))


def _campo_con_linea(c: canvas.Canvas, x: float, y: float, etiqueta: str, ancho_linea: float, fuente_tam: int = 9):
    """Etiqueta seguida de una línea en blanco para completar a mano
    (secciones de observación visual de P_CC002-2)."""
    c.setFont("Helvetica-Bold", fuente_tam)
    c.drawString(x, y, f"{etiqueta}:")
    ancho_etiqueta = stringWidth(f"{etiqueta}: ", "Helvetica-Bold", fuente_tam)
    c.line(x + ancho_etiqueta + 0.1 * cm, y - 0.05 * cm, x + ancho_etiqueta + ancho_linea, y - 0.05 * cm)


def _campo_con_valor_o_linea(c: canvas.Canvas, x: float, y: float, etiqueta: str, valor, ancho_linea: float, fuente_tam: int = 9):
    """Como _campo_con_linea, pero si la Orden de Trabajo digital ya cargó
    un valor lo imprime en vez de dejar la línea en blanco para completar a
    mano."""
    if valor not in (None, ""):
        c.setFont("Helvetica-Bold", fuente_tam)
        c.drawString(x, y, f"{etiqueta}:")
        ancho_etiqueta = stringWidth(f"{etiqueta}: ", "Helvetica-Bold", fuente_tam)
        c.setFont("Helvetica", fuente_tam)
        c.drawString(x + ancho_etiqueta + 0.1 * cm, y, str(valor))
    else:
        _campo_con_linea(c, x, y, etiqueta, ancho_linea, fuente_tam)


def _dibujar_orden_trabajo(c: canvas.Canvas, solicitud, cantidades: dict, ensayos: list, etiqueta_copia: str):
    _, height = A4
    x = 1.5 * cm
    ancho_total = 18 * cm
    y = height - 1.5 * cm

    def salto_pagina_si_hace_falta(espacio: float):
        nonlocal y
        if y - espacio < 2.5 * cm:
            c.showPage()
            y = height - 1.5 * cm

    y = _encabezado_formulario(c, x, y, "ORDEN DE TRABAJO DE CONTROL DE CALIDAD", "P CC002-1", "02", etiqueta_copia)

    _fila_campos(c, x, y, [
        ("Código de producto", solicitud.erp_CODART.strip()), ("Nombre", solicitud.erp_DESART.strip()),
    ], ancho_total)
    y -= 0.55 * cm
    _fila_campos(c, x, y, [
        ("IR N°", solicitud.erp_nro_ir), ("Proveedor", solicitud.proveedor_nombre), ("Lote proveedor", solicitud.lote_proveedor),
    ], ancho_total)
    y -= 0.55 * cm
    _fila_campos(c, x, y, [
        ("Fecha de ingreso", _fmt_fecha(solicitud.fecha_ingreso)),
        ("Fecha de vencimiento", _fmt_fecha(solicitud.fecha_vencimiento)),
        ("Fecha de reanálisis", _fmt_fecha(solicitud.fecha_reanalisis)),
    ], ancho_total)
    y -= 0.55 * cm
    _fila_campos(c, x, y, [
        ("País de origen", solicitud.pais_origen),
        ("Cantidad ingresada", _cantidad_texto(solicitud.cantidad_ingresada, solicitud.unidad_cantidad)),
        ("Cantidad a Muestrear", _cantidad_texto(cantidades.get("cantidad_muestra"), cantidades.get("unidad_muestra"))),
    ], ancho_total)
    y -= 0.55 * cm
    _fila_campos(c, x, y, [
        ("N° de Bultos ingresados", solicitud.nro_bultos),
        ("N° Bultos Muestreados", solicitud.nro_bultos_muestreados),
        ("Metodología de Análisis", solicitud.metodologia_analisis),
    ], ancho_total)
    y -= 0.9 * cm

    c.setFont("Helvetica-Bold", 11)
    c.drawString(x, y, "DETERMINACIONES A REALIZAR")
    y -= 0.2 * cm
    c.line(x, y, x + ancho_total, y)
    y -= 0.5 * cm

    col_det = (x, 5.5 * cm)
    col_esp_x, col_esp_w = x + 5.5 * cm, 7 * cm
    col_res = (x + 12.5 * cm, 3 * cm)
    col_cuad = (x + 15.5 * cm, 2.5 * cm)

    c.setFont("Helvetica-Bold", 8)
    c.drawString(col_det[0], y, "DETERMINACIONES")
    c.drawString(col_esp_x, y, "ESPECIFICACIONES")
    c.drawString(col_res[0], y, "RESULTADOS")
    c.drawString(col_cuad[0], y, "CUADERNO N°/PAG")
    y -= 0.15 * cm
    c.line(x, y, x + ancho_total, y)
    y -= 0.45 * cm

    if ensayos:
        for e in ensayos:
            especif = _especificacion_texto(e)
            parrafo = Paragraph(_escapar_html(str(especif)), _ESTILO_ESPECIFICACION)
            _, alto_parrafo = parrafo.wrap(col_esp_w - 0.2 * cm, 1000)
            alto_fila = max(0.5 * cm, alto_parrafo + 0.15 * cm)
            salto_pagina_si_hace_falta(alto_fila)

            c.setFont("Helvetica", 8)
            c.drawString(col_det[0], y, e.nombre_ensayo[:32])
            parrafo.drawOn(c, col_esp_x, y - alto_parrafo + _ESTILO_ESPECIFICACION.fontSize)

            # RESULTADOS: si la Orden de Trabajo digital ya se confirmó, se
            # imprime el valor cargado; si no, queda la línea en blanco para
            # completar a mano (mismo comportamiento que antes de digitalizar
            # este formulario). CUADERNO no tiene equivalente digital, siempre
            # en blanco.
            tiene_resultado = e.valor_numerico is not None or bool((e.valor_cualitativo or "").strip())
            if tiene_resultado:
                resultado_txt = _texto(e.valor_numerico) if e.tipo_dato == "numerico" else (e.valor_cualitativo or "")
                c.drawString(col_res[0], y, str(resultado_txt)[: int(col_res[1] / 0.17)])
            else:
                c.line(col_res[0], y - 0.1 * cm, col_res[0] + col_res[1] - 0.2 * cm, y - 0.1 * cm)
            c.line(col_cuad[0], y - 0.1 * cm, col_cuad[0] + col_cuad[1] - 0.2 * cm, y - 0.1 * cm)
            y -= alto_fila
    else:
        c.setFont("Helvetica-Oblique", 8)
        c.drawString(x, y, "Sin ensayos asignados a este laboratorio para esta especificación.")
        y -= 0.5 * cm

    y -= 0.3 * cm
    c.line(x, y, x + ancho_total, y)
    y -= 0.6 * cm

    salto_pagina_si_hace_falta(1.2 * cm)
    c.setFont("Helvetica-Bold", 9)
    c.drawString(x, y, "Observaciones:")
    y -= 0.15 * cm
    c.line(x, y, x + ancho_total, y)
    y -= 0.9 * cm

    salto_pagina_si_hace_falta(3.6 * cm)
    ancho_mitad = ancho_total / 2
    c.setFont("Helvetica-Bold", 9)
    c.drawString(x, y, "Muestreó")
    c.drawString(x + ancho_mitad, y, "Controló")
    y -= 0.9 * cm

    for etiqueta in ("Fecha", "Firma"):
        for cx in (x, x + ancho_mitad):
            c.setFont("Helvetica", 8)
            c.drawString(cx, y, f"{etiqueta}:")
            c.line(cx + 1.2 * cm, y - 0.05 * cm, cx + ancho_mitad - 0.5 * cm, y - 0.05 * cm)
        y -= 0.8 * cm

    y -= 0.4 * cm
    _pie_confidencialidad(c, x, y)

    c.showPage()


def generar_pdf_orden_trabajo(solicitud, cantidades: dict, ensayos: list) -> bytes:
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    for etiqueta_copia in ("ORIGINAL", "DUPLICADO"):
        _dibujar_orden_trabajo(c, solicitud, cantidades, ensayos, etiqueta_copia)
    c.save()
    return buffer.getvalue()


def _dibujar_planilla_muestreo(c: canvas.Canvas, solicitud):
    _, height = A4
    x = 1.5 * cm
    ancho_total = 18 * cm
    y = height - 1.5 * cm

    def salto_pagina_si_hace_falta(espacio: float):
        nonlocal y
        if y - espacio < 2.5 * cm:
            c.showPage()
            y = height - 1.5 * cm

    def titulo_seccion(texto: str):
        nonlocal y
        c.setFont("Helvetica-Bold", 10)
        c.drawString(x, y, texto)
        y -= 0.15 * cm
        c.line(x, y, x + ancho_total, y)
        y -= 0.55 * cm

    y = _encabezado_formulario(c, x, y, "PLANILLA DE MUESTREO DE MATERIAS PRIMAS", "P CC002-2", "02")

    _fila_campos(c, x, y, [("Código", solicitud.erp_CODART.strip()), ("IR", solicitud.erp_nro_ir)], ancho_total)
    y -= 0.55 * cm
    c.setFont("Helvetica-Bold", 8)
    c.drawString(x, y, "Descripción:")
    ancho_etq = stringWidth("Descripción: ", "Helvetica-Bold", 8)
    c.setFont("Helvetica", 8)
    c.drawString(x + ancho_etq + 0.1 * cm, y, solicitud.erp_DESART.strip())
    y -= 0.55 * cm
    _fila_campos(c, x, y, [("Proveedor", solicitud.proveedor_nombre), ("Fabricante", solicitud.fabricante)], ancho_total)
    y -= 0.55 * cm
    _fila_campos(c, x, y, [("Lote de Proveedor", solicitud.lote_proveedor), ("Fecha de Muestreo", "")], ancho_total)
    y -= 0.55 * cm
    _fila_campos(c, x, y, [
        ("N° de bultos totales", solicitud.nro_bultos),
        ("N° de bultos muestreados", solicitud.nro_bultos_muestreados),
    ], ancho_total)
    y -= 0.9 * cm

    salto_pagina_si_hace_falta(2.2 * cm)
    titulo_seccion("1. CONTENEDOR")
    _fila_campos(c, x, y, [
        ("Aspecto Externo", solicitud.aspecto_externo), ("Cierre", solicitud.cierre),
    ], ancho_total)
    y -= 0.55 * cm
    _fila_campos(c, x, y, [
        ("Aspecto interno", solicitud.aspecto_interno), ("Precintos", solicitud.precintos),
    ], ancho_total)
    y -= 0.9 * cm

    salto_pagina_si_hace_falta(2.9 * cm)
    titulo_seccion("2. IDENTIFICACIÓN DEL CONTENEDOR")
    _campo_con_valor_o_linea(c, x, y, "2.1 Identificación", getattr(solicitud, "identificacion_contenedor", None), 10 * cm)
    y -= 0.7 * cm
    _campo_con_valor_o_linea(c, x, y, "2.2 Fecha de Vencimiento", _fmt_fecha(getattr(solicitud, "fecha_vencimiento_real", None)) if getattr(solicitud, "fecha_vencimiento_real", None) else None, 6 * cm)
    y -= 0.7 * cm
    _campo_con_valor_o_linea(c, x, y, "2.3 Fecha de reanálisis", _fmt_fecha(getattr(solicitud, "fecha_reanalisis_real", None)) if getattr(solicitud, "fecha_reanalisis_real", None) else None, 6 * cm)
    y -= 0.9 * cm

    salto_pagina_si_hace_falta(3.8 * cm)
    titulo_seccion("3. ASPECTO DE LA MATERIA PRIMA")
    _campo_con_valor_o_linea(c, x, y, "3.0 Aspecto general", getattr(solicitud, "aspecto_mp", None), 10 * cm)
    y -= 0.55 * cm
    _campo_con_valor_o_linea(c, x, y, "3.1 Materias extrañas", solicitud.materias_extranas, 10 * cm)
    y -= 0.55 * cm
    _campo_con_valor_o_linea(c, x, y, "3.2 Olor", solicitud.olor, 10 * cm)
    y -= 0.55 * cm
    _campo_con_valor_o_linea(c, x, y, "3.3 Color", solicitud.color, 10 * cm)
    y -= 0.55 * cm
    _campo_con_valor_o_linea(c, x, y, "3.4 Observaciones", solicitud.observaciones_muestreo, 10 * cm)
    y -= 1.0 * cm

    salto_pagina_si_hace_falta(2 * cm)
    c.setFont("Helvetica-Bold", 9)
    c.drawString(x, y, "Muestreado por:")
    y -= 1.0 * cm
    c.line(x, y, x + 9 * cm, y)
    y -= 0.35 * cm
    c.setFont("Helvetica", 8)
    c.drawString(x, y, "Firma y aclaración")

    y -= 1 * cm
    _pie_confidencialidad(c, x, y)

    c.showPage()


def generar_pdf_planilla_muestreo(solicitud) -> bytes:
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    _dibujar_planilla_muestreo(c, solicitud)
    c.save()
    return buffer.getvalue()
