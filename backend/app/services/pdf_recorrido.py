"""
Resumen de trazabilidad de una muestra en PDF ("Recorrido de Muestra") --
mismo contenido y misma estructura de 6 bloques que la pantalla Consulta de
Muestras > Ver recorrido (ConsultaMuestraDetallePage.jsx), pero como PDF
para poder incluirlo como primera sección del "Legajo completo" (ver
pdf_legajo.py). Dibujo directo con reportlab (canvas), mismo enfoque que el
resto de los PDFs del proyecto (pdf_remito.py, pdf_solicitud_muestreo.py).

"Ver recorrido" (la pantalla HTML con window.print()) no cambia -- este
módulo es nuevo, solo lo usa el Legajo completo.
"""
import io
from datetime import date, datetime

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.pdfgen import canvas

from app.schemas.recorrido import RecorridoResponse


def _texto(valor) -> str:
    if valor in (None, ""):
        return "—"
    return str(valor)


def _fmt_fecha(valor) -> str:
    if not valor:
        return "—"
    if isinstance(valor, datetime):
        valor = valor.date()
    if isinstance(valor, str):
        valor = date.fromisoformat(valor)
    return valor.strftime("%d/%m/%Y")


def _fmt_dt(valor) -> str:
    if not valor:
        return "—"
    if isinstance(valor, str):
        valor = datetime.fromisoformat(valor)
    return valor.strftime("%d/%m/%Y %H:%M")


def _resultado_texto(en) -> str:
    if en.tipo_dato == "numerico":
        return _texto(en.valor_numerico)
    return _texto(en.valor_cualitativo)


def _especificacion_texto(en) -> str:
    if en.tipo_dato == "numerico":
        return f"{_texto(en.limite_inferior)} a {_texto(en.limite_superior)} {en.unidad_medida or ''}".strip()
    return _texto(en.valor_requerido)


def _estado_texto(en) -> str:
    if en.dentro_especificacion is None:
        return "Sin resultado"
    return "Cumple" if en.dentro_especificacion else "No cumple"


def generar_pdf_recorrido(recorrido: RecorridoResponse) -> bytes:
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    _dibujar_recorrido(c, recorrido)
    c.save()
    return buffer.getvalue()


def _dibujar_recorrido(c: canvas.Canvas, r: RecorridoResponse):
    _, height = A4
    x = 1.5 * cm
    ancho_total = 18 * cm
    y_inicial = height - 1.5 * cm
    # Lista de un elemento en vez de una variable simple: así los helpers
    # anidados de más abajo pueden mutar la posición vertical sin declarar
    # "nonlocal y" en cada uno (mismo resultado, menos repetición).
    y = [y_inicial]

    def salto_pagina_si_hace_falta(espacio: float):
        if y[0] - espacio < 2 * cm:
            c.showPage()
            y[0] = y_inicial

    def subtitulo(texto: str):
        salto_pagina_si_hace_falta(1.2 * cm)
        c.setFont("Helvetica-Bold", 11)
        c.drawString(x, y[0], texto)
        y[0] -= 0.15 * cm
        c.line(x, y[0], x + ancho_total, y[0])
        y[0] -= 0.5 * cm

    def campo(etiqueta: str, valor) -> bool:
        """Devuelve False (y no dibuja nada) si el valor está vacío -- así
        el resto de bloques opcionales se arman con `if campo(...): ...`."""
        if valor in (None, ""):
            return False
        salto_pagina_si_hace_falta(0.5 * cm)
        c.setFont("Helvetica-Bold", 9)
        c.drawString(x, y[0], f"{etiqueta}:")
        c.setFont("Helvetica", 9)
        c.drawString(x + 5 * cm, y[0], str(valor)[:95])
        y[0] -= 0.45 * cm
        return True

    def tabla_ensayos(filas):
        """Tabla de ensayos con 5 columnas (ensayo / metodología / especificación
        / resultado / estado). Sin encabezado repetido entre páginas -- mismo
        criterio que la tabla de testigos de pdf_remito_testigo.py, listas
        cortas en la práctica."""
        columnas = [
            ("Ensayo", 0, 5 * cm), ("Metodología", 5 * cm, 3.5 * cm),
            ("Especificación", 8.5 * cm, 4 * cm), ("Resultado", 12.5 * cm, 2.5 * cm),
            ("Estado", 15 * cm, 3 * cm),
        ]
        salto_pagina_si_hace_falta(0.9 * cm)
        c.setFont("Helvetica-Bold", 8)
        for titulo_col, cx, _ in columnas:
            c.drawString(x + cx, y[0], titulo_col)
        y[0] -= 0.15 * cm
        c.line(x, y[0], x + ancho_total, y[0])
        y[0] -= 0.4 * cm
        c.setFont("Helvetica", 8)
        for fila in filas:
            salto_pagina_si_hace_falta(0.4 * cm)
            for (_, cx, ancho), valor in zip(columnas, fila):
                c.drawString(x + cx, y[0], str(valor)[: int(ancho / 0.15)])
            y[0] -= 0.42 * cm
        y[0] -= 0.25 * cm

    # ── Encabezado ──────────────────────────────────────────────────
    c.setFont("Helvetica-Bold", 14)
    c.drawString(x, y[0], "Recorrido de Muestra")
    y[0] -= 0.7 * cm
    c.setFont("Helvetica-Bold", 12)
    c.drawString(x, y[0], f"{r.codigo_muestra} — {r.erp_DESART}")
    y[0] -= 0.5 * cm
    c.setFont("Helvetica", 9)
    c.drawString(x, y[0], f"Estado: {r.estado.replace('_', ' ')}" + ("  |  Datos de muestreo pendientes" if r.datos_muestreo_pendientes else ""))
    y[0] -= 0.9 * cm

    s = r.solicitud

    # 1. Solicitud de Muestreo
    subtitulo("1. Solicitud de Muestreo")
    if s:
        campo("N° Solicitud", s.nro_solicitud)
        campo("Generada por", s.usuario_qa_nombre)
        campo("Fecha de solicitud", _fmt_dt(s.fecha_solicitud))
    campo("Muestreador", r.usuario_muestreo_nombre)
    campo("Fecha de muestreo", _fmt_dt(r.fecha_muestreo))
    y[0] -= 0.3 * cm

    # 2. Identificación -- el proveedor se muestra UNA sola vez acá, igual
    # que en la pantalla (no se repite por envío).
    subtitulo("2. Identificación")
    campo("N° de IR" if r.tipo_referencia == "ir" else "N° de Lote", r.nro_referencia)
    campo("Nombre", r.erp_DESART)
    campo("Código", r.erp_CODART)
    campo("Tipo de material", r.tipo_material)
    proveedor_texto = None
    if s and s.proveedor_nombre:
        proveedor_texto = f"{s.proveedor_codigo} - {s.proveedor_nombre}" if s.proveedor_codigo else s.proveedor_nombre
    elif r.erp_proveedor:
        proveedor_texto = r.erp_proveedor
    campo("Proveedor", proveedor_texto)
    if s:
        campo("Lote del proveedor", s.lote_proveedor)
        campo("Fecha de vencimiento", _fmt_fecha(s.fecha_vencimiento))
        campo("Fecha de reanálisis", _fmt_fecha(s.fecha_reanalisis))
    y[0] -= 0.3 * cm

    # 3. Datos del Contenedor
    if s:
        df = s.datos_fisicos
        campos_contenedor = [
            ("Identificación de contenedor", df.identificacion_contenedor),
            ("Aspecto externo", df.aspecto_externo),
            ("Cierre", df.cierre),
            ("Aspecto interno", df.aspecto_interno),
            ("Precintos", df.precintos),
            ("N° de bultos muestreados", df.nro_bultos_muestreados),
        ]
        if any(v not in (None, "") for _, v in campos_contenedor):
            subtitulo("3. Datos del Contenedor")
            for etiqueta, valor in campos_contenedor:
                campo(etiqueta, valor)
            y[0] -= 0.3 * cm

    # 4. Aspecto de la Materia Prima + especificaciones internas (Orden de Trabajo)
    if s:
        subtitulo("4. Aspecto de la Materia Prima")
        campo("Aspecto de la MP", df.aspecto_mp)
        campo("Materias extrañas", df.materias_extranas)
        campo("Olor", df.olor)
        campo("Color", df.color)
        campo("Fecha de vencimiento real", _fmt_fecha(df.fecha_vencimiento_real) if df.fecha_vencimiento_real else None)
        campo("Fecha de reanálisis real", _fmt_fecha(df.fecha_reanalisis_real) if df.fecha_reanalisis_real else None)
        y[0] -= 0.15 * cm
        c.setFont("Helvetica-Bold", 9)
        salto_pagina_si_hace_falta(0.5 * cm)
        c.drawString(x, y[0], "Especificaciones definidas")
        y[0] -= 0.45 * cm
        if r.resultados_orden_trabajo:
            tabla_ensayos([
                (en.nombre_ensayo, en.metodologia or "—", _especificacion_texto(en), _resultado_texto(en), _estado_texto(en))
                for en in r.resultados_orden_trabajo
            ])
        else:
            c.setFont("Helvetica", 9)
            salto_pagina_si_hace_falta(0.5 * cm)
            c.drawString(x, y[0], "Sin resultados internos cargados.")
            y[0] -= 0.5 * cm
        if campo("Observaciones", df.observaciones_muestreo):
            pass
        y[0] -= 0.3 * cm

    # 5. Datos del Envío -- un bloque completo por cada envío
    if not r.envios:
        subtitulo("5. Datos del Envío")
        c.setFont("Helvetica", 9)
        salto_pagina_si_hace_falta(0.5 * cm)
        c.drawString(x, y[0], "Esta muestra todavía no tiene envíos registrados.")
        y[0] -= 0.6 * cm
    else:
        for en in r.envios:
            subtitulo(f"5. Datos del Envío — N° {en.nro_remito or en.id_envio} — {en.laboratorio_nombre}")
            campo("Laboratorio", en.laboratorio_nombre)
            campo("Fecha de envío", _fmt_dt(en.fecha_despacho))
            if en.testigos:
                campo("Testigo utilizado", ", ".join(f"{t.codigo} — {t.nombre}" for t in en.testigos))
            if en.protocolo:
                campo("Protocolo externo", en.protocolo.nro_protocolo_ext)
            y[0] -= 0.15 * cm
            if en.ensayos:
                tabla_ensayos([
                    (ens.nombre_ensayo, ens.metodologia or "—", _especificacion_texto(ens), _resultado_texto(ens), _estado_texto(ens))
                    for ens in en.ensayos
                ])
            y[0] -= 0.3 * cm

    # 6. Dictamen Final
    subtitulo("6. Dictamen Final")
    if r.dictamen:
        c.setFont("Helvetica-Bold", 11)
        salto_pagina_si_hace_falta(0.6 * cm)
        c.drawString(x, y[0], r.dictamen.estado_dictamen.upper())
        y[0] -= 0.6 * cm
        campo("QA firmante", r.dictamen.usuario_qa_nombre)
        campo("Fecha del dictamen", _fmt_dt(r.dictamen.fecha_dictamen))
        campo("Justificación", r.dictamen.justificacion_oos)
        campo("Observaciones", r.dictamen.observaciones)
    else:
        c.setFont("Helvetica", 9)
        salto_pagina_si_hace_falta(0.5 * cm)
        c.drawString(x, y[0], "Pendiente de dictamen QA")
        y[0] -= 0.5 * cm

    c.showPage()
