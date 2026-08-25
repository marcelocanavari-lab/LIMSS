"""
Impresión directa de etiquetas en impresoras SATO (CG40TT/CG408TT, WS408TT)
por SBPL (SATO Barcode Printer Language), sin pasar por el software del
fabricante -- se arma el comando SBPL a mano y se manda como trabajo RAW a
la impresora, compartida en red desde la PC donde está conectada por USB
(ver imprimir_sbpl).

Comandos usados, sintaxis verificada contra dos manuales oficiales de SATO
(no inventada): el manual genérico "SATO Barcode Programming Language for
Enhanced Printer Models", y el "WS4 Series Programming Reference"
(satoamerica.com, específico de WS408TT/WS412TT) -- ambos coinciden byte a
byte en la sintaxis de estos comandos:

    <A>                       inicio del trabajo
    <A1>VVVVHHHH              tamaño de etiqueta en puntos (vertical, horizontal)
    <A3>VabbbbHcdddd          corrección del punto de origen (a/c=signo
                               opcional, bbbb/dddd=desplazamiento en puntos)
    <L>aabb                   expansión de fuente (aa=horizontal, bb=vertical,
                               múltiplos ENTEROS 01-12, no hay % exacto)
    <V>nnnn<H>nnnn<XM>txt     posición + texto en fuente XM (24x24 puntos base)
    <FW>aabcccc               una línea recta (modo "Rule"): a=grosor (02-99
                               pts), b=H o V, c=largo. El recuadro se arma
                               con 4 de estas (una por lado) -- el modo
                               "Grid" (aabbVccccHdddd, una sola invocación)
                               NO cierra un rectángulo por sí solo, dibuja
                               apenas una V + una H desde la misma esquina
                               (piezas para armar una grilla de tabla, no
                               un box) -- confirmado en la impresora real:
                               con "Grid" faltaba el lado de cierre.
    <2D30>,a,bb,c,d           código QR (Model 2): a=nivel de corrección de
                               error (L/M/Q/H), bb=tamaño de celda (01-32 pts),
                               c=modo de datos (0=manual), d=modo de
                               concatenación (0=normal)
    <DS>k,datos               datos del QR en modo manual (k=2 alfanumérico)
    <BG>aabbbdatos            código de barras CODE128: a=ancho de barra
                               angosta (01-12 pts), bbb=alto (001-600 pts),
                               datos=el dato a codificar (el dígito
                               verificador se genera solo) -- sección
                               "ESC+BG CODE128 Barcode Specification" del
                               mismo manual "SATO Barcode Programming
                               Language for Enhanced Printer Models" citado
                               arriba, página 51 (verificado, no inventado).
    <Q>1                      cantidad de copias
    <Z>                       fin del trabajo

Modelo real detrás de "CG40TT": no existe ese nombre exacto en el catálogo
SATO -- el modelo real es CG408TT (mismo patrón de nombre que WS408TT).
Soporte de código QR en CG408TT confirmado por su hoja de especificaciones
(lista QR Code, Micro QR, PDF417, Micro PDF, MAXI Code, GS1 DataMatrix como
símbolos 2D soportados) y por el "E/Pro Programming Reference" de SATO, que
cubre la serie CG4 (CG208/212/408/412) con el mismo set de comandos SBPL --
no se pudo descargar ese PDF puntual para citarlo textual (enlaces caídos),
pero la sintaxis de <2D30> ya está verificada byte a byte contra dos
manuales oficiales distintos y SBPL es el mismo lenguaje en toda la línea de
impresoras "Enhanced" de SATO, así que no hay motivo para asumir que difiere
en CG408TT.

Dos puntos que no eran evidentes de la notación del manual y que hicieron
que la primera versión de este módulo mandara texto plano que la impresora
no reconocía como nada (se confirmó por Windows sin error, pero no imprimía):

1. `<A>`, `<V>`, `<XM>`, etc. son notación DE DOCUMENTACIÓN, no texto
   literal -- cada uno representa el byte ESC real (0x1B) seguido de la
   letra/palabra del comando. `<A>` = byte 0x1B + 'A', no los tres
   caracteres '<', 'A', '>'. Ver _cmd().
2. El payload completo (`<A>...<Z>`, ya con los ESC reales) va envuelto en
   STX (0x02) al principio y ETX (0x03) al final -- sección "Command
   Composition" del manual.

pywin32 (win32print) verificado explícitamente en este entorno antes de
construir este módulo -- a diferencia de Tesseract/subprocess, importa y
funciona sin problemas (OpenPrinter/ClosePrinter probados contra impresoras
reales de este servidor)."""
import logging
import socket
import struct
from pathlib import Path
from typing import Optional

from app.services.formato import etiqueta_referencia, formatear_cantidad

logger = logging.getLogger("impresion_sato")

try:
    import win32print
except ImportError:
    # No debería pasar en este entorno (ver Paso 0) -- si pasa, imprimir_sbpl
    # falla con un mensaje claro en vez de un ImportError críptico más abajo.
    win32print = None

ESC = b"\x1b"
STX = b"\x02"
ETX = b"\x03"


def mm_a_puntos(mm: float, dpi: int) -> int:
    return round(mm * dpi / 25.4)


# ── Logo (etiquetas CUARENTENA/APROBADO) ────────────────────────────────
#
# <GP> (ESC+GP, "PCX File Print Specification") -- sección "Basic Commands"
# del manual oficial SATO Barcode Programming Language (páginas 72 y, para
# la variante con registro en memory card que NO se usa acá, 197). Se eligió
# <GP> sobre <PI>/<GI> (sección "Option Command (Memory Card)", página 185)
# a propósito: <PI>/<GI> registran el gráfico en una tarjeta de memoria
# (requieren <CC>, Card Slot) para reimprimirlo después con <PY>/<GR> --
# esta impresora no tiene ese hardware confirmado, y el resto de este módulo
# ya manda el SBPL completo en cada trabajo (sin estado persistente en la
# impresora), así que <GP> (imprime directo, sin registrar nada) es
# consistente con esa arquitectura y no depende de una tarjeta que
# capaz no existe.
#
# Formato confirmado en el manual (no inventado): <GP>aaaaa,n-n
#   a "Total Byte of a PCX file" -- 5 dígitos
#   n "Data" -- los bytes crudos del archivo PCX (no hex, binario real)
# El archivo PCX en sí (1 bit, blanco y negro puro, formato ZSoft estándar
# con RLE -- exactamente lo que el manual exige: "A PCX file can only be
# used in Black/White mode") se generó una sola vez a partir del logo
# (backend/app/assets/logo_lamar_icono.pcx) y se lee acá tal cual, sin
# volver a convertir nada en cada impresión.
_RUTA_LOGO_PCX = Path(__file__).resolve().parent.parent / "assets" / "logo_lamar_icono.pcx"


def _cargar_logo_pcx() -> tuple[bytes, int, int]:
    """Devuelve (bytes_del_archivo, ancho_px, alto_px) -- ancho/alto se leen
    del propio header PCX (offsets 4-11: Xmin/Ymin/Xmax/Ymax, 16 bits cada
    uno, little-endian -- formato ZSoft estándar) en vez de hardcodearlos,
    para que si se reemplaza el archivo por uno de otro tamaño, el layout se
    siga calculando bien solo."""
    datos = _RUTA_LOGO_PCX.read_bytes()
    xmin, ymin, xmax, ymax = struct.unpack("<HHHH", datos[4:12])
    return datos, xmax - xmin + 1, ymax - ymin + 1


_LOGO_PCX_BYTES, _LOGO_ANCHO_PX, _LOGO_ALTO_PX = _cargar_logo_pcx()


def _cmd_grafico_pcx(pcx_bytes: bytes) -> bytes:
    """<GP>: a diferencia de _cmd(), los datos son binarios (el archivo PCX
    tal cual), no texto -- no se puede pasar por _cmd() (asume datos: str y
    los codifica como latin-1)."""
    return ESC + b"GP" + f"{len(pcx_bytes):05d},".encode("ascii") + pcx_bytes


def _texto(valor) -> str:
    return str(valor) if valor not in (None, "") else "-"


# Acentos/ñ en la SATO (punto 6 del pedido de ajustes de etiquetas): se
# investigó primero si el manual documenta un comando de code page/juego de
# caracteres distinto para <XM> (u otra fuente usada acá) que sí imprima
# á/é/í/ó/ú/ñ correctamente -- no se encontró ninguno. La especificación de
# <XM> (sección "ESC+XM XM Font Specification" del manual) solo permite
# elegir paso proporcional o fijo, sin ningún parámetro de charset/code
# page; tampoco aparece un comando de selección de tabla de caracteres en
# el resto del manual (se buscó explícitamente "code page", "character
# set", ISO-8859, Windows-1252, CP437, etc.). Probar a ciegas un comando no
# documentado para esto es justamente el escenario "demasiado riesgoso" que
# el pedido contempla como razón válida para no intentarlo (un comando mal
# formado puede hacer que la impresora ignore el resto del trabajo). Se usa
# entonces el respaldo explícitamente autorizado: sacar los acentos SOLO en
# el texto que se manda a la SATO (el PDF de la misma etiqueta sigue
# mostrando los acentos normalmente, no pasa por acá).
_MAPA_SIN_ACENTOS = str.maketrans("áéíóúÁÉÍÓÚñÑüÜ", "aeiouAEIOUnNuU")


def _quitar_acentos(texto: str) -> str:
    return texto.translate(_MAPA_SIN_ACENTOS)


def _cmd(codigo: str, datos: str = "") -> bytes:
    """Un comando SBPL individual: byte ESC real (0x1B) + código ASCII del
    comando + datos (si tiene). `codigo` en ASCII puro (siempre lo es en
    SBPL); `datos` pasa primero por _quitar_acentos (ver más arriba) y
    después se codifica en latin-1 como respaldo final para cualquier otro
    carácter no contemplado (para no romper el comando entero por un
    carácter suelto que igual no se vaya a ver bien)."""
    return ESC + codigo.encode("ascii") + _quitar_acentos(datos).encode("latin-1", errors="replace")


# <L> solo admite múltiplos ENTEROS 1-12 (no hay especificación de
# porcentaje). MULTIPLICADOR_BASE es el tamaño explícito de todos los
# campos, incluido el nombre del producto -- se probó un intento de "+20%"
# con multiplicador 2 (el entero más chico que representa algún aumento
# real sobre 1x), pero en la impresora real eso duplicaba el tamaño y el
# texto se salía del margen. Revertido al tamaño original (1x, el que tenía
# el campo antes de ese intento -- no hay comando <L> especial para el
# nombre del producto, usa el mismo multiplicador base que el resto).
MULTIPLICADOR_BASE = 1

# Corrección de origen: toda la etiqueta se corre con <A3> en vez de tocar
# cada <H> individualmente. Arrancó en +5mm a la derecha; se le resta
# después un ancho de carácter (ANCHO_CARACTER_XM_PT, definido más abajo)
# para correr todo un poco hacia la izquierda -- ver el cálculo de
# correccion_h_pt en generar_sbpl_etiqueta.
CORRECCION_DERECHA_MM = 5

# Recuadro: margen desde el borde físico para que la línea no quede
# cortada en el límite de impresión de la cabeza, y grosor de línea.
MARGEN_RECUADRO_PT = 6
GROSOR_RECUADRO_PT = 3
# Alto FIJO del recuadro (ya no "todo el alto de la etiqueta") -- landscape,
# no portrait: el recuadro es más ancho que alto. En cm, no en mm, para que
# no se confunda con alto_mm (el alto físico real de la impresora). Sigue
# siendo preparación para una futura disposición de 2 etiquetas por hoja
# (esta vez apiladas una encima de la otra, no lado a lado, ya que ahora el
# recuadro reparte el ALTO en vez del ancho) -- hoy sigue imprimiéndose una
# sola etiqueta, este valor es lo que ocupa ESA etiqueta. Arrancó en 4.2cm,
# se achicó 6mm (0.6cm) porque se veía muy grande en la impresión real.
RECUADRO_ALTO_CM = 3.6

# QR: nivel de corrección de error M (15%) -- balance razonable entre
# tamaño del símbolo y tolerancia a manchas/roturas de la etiqueta. Tamaño
# de celda objetivo ~0.7mm/módulo, dentro del rango válido 01-32 pts.
NIVEL_CORRECCION_QR = "M"
TAMANO_CELDA_QR_MM = 0.7
# Margen deseado contra el borde derecho al alinear el QR ahí (en vez de
# centrado) -- mismo criterio que el margen general del resto del layout.
MARGEN_DERECHO_QR_PT_MM = 3

# QR y código de barras de la etiqueta CUARENTENA/APROBADO/RECHAZADO (ver
# generar_sbpl_etiqueta_estado) -- celda de QR más chica que
# TAMANO_CELDA_QR_MM porque esta etiqueta tiene mucho menos lugar libre que
# la de muestra (ya lleva título 2x, nombre de producto a 2 líneas, IR/LOTE
# 2x y 5 campos más antes de llegar acá).
TAMANO_CELDA_QR_ESTADO_MM = 0.5
# Código de barras CODE128 (<BG>, ver más abajo): altura fija (no depende
# del dato, a diferencia del QR que crece con el largo del texto) y ancho
# de barra angosta chico para que el símbolo completo (código de artículo +
# IR/LOTE) no se pase del ancho disponible.
ALTO_BARCODE_MM = 10
ALTO_BARCODE_MINIMO_PT = 40  # piso: por debajo de esto un CODE128 deja de ser confiable para escanear
ANCHO_BARRA_CODE128_PT = 2
# Estructura de módulos de un símbolo CODE128 (estándar ISO/IEC 15417, no
# específico de SATO): cada carácter de datos ocupa 11 módulos; el símbolo
# completo agrega además el carácter de inicio (11), el dígito verificador
# (11, el mismo que <BG> genera solo, ver nota del módulo) y el carácter de
# parada (13) -- de ahí la fórmula ya publicada L = (11*C + 35) * X, con C =
# cantidad de caracteres de DATOS (sin contar inicio/verificador/parada) y
# X = ancho de módulo (acá, ANCHO_BARRA_CODE128_PT). Asume Code Set B (un
# carácter de entrada = un carácter de símbolo) -- válido para datos
# alfanuméricos mixtos como los de esta etiqueta (código de artículo +
# IR/LOTE): el ahorro de Code Set C (2 dígitos por carácter de símbolo) solo
# aplica a corridas de 4+ dígitos seguidos, que estos datos no tienen.
MODULOS_OVERHEAD_CODE128 = 35
MODULOS_POR_CARACTER_CODE128 = 11
# Margen deseado contra el borde derecho al alinear el código de barras ahí
# (mismo criterio que MARGEN_DERECHO_QR_PT_MM para el QR de la etiqueta de
# muestra).
MARGEN_DERECHO_BARCODE_MM = 3
# Margen inferior reservado antes del logo del pie, y aire entre la grilla y
# la fila de QR/código de barras -- más chicos que el margen general
# (margen de texto, 3mm) porque acá ya no queda aire de sobra: hace falta
# ese lugar para la grilla y el QR/código de barras nuevos (ver el pedido de
# agregarlos a esta etiqueta). Son elementos gráficos, no texto -- no
# necesitan el mismo "aire" que un renglón de letra para no verse pegados.
MARGEN_INFERIOR_FOOTER_MM = 1
GAP_ANTES_CODIGOS_MM = 1.5
GAP_CODIGOS_A_FOOTER_MM = 1

# Ancho de cada carácter en la fuente <XM>, en puntos, a multiplicador 1x --
# confirmado en el manual oficial ("Font with the basic size of: width 24
# dots, height 24 dots"), paso FIJO (no proporcional, acá nunca se manda
# <PS>) -- por eso cada carácter (incluidos espacios) mide exactamente esto,
# sin necesidad de medir con una fuente real. Se usa para el diagnóstico de
# posiciones y como unidad "una letra" para correcciones de posición (ver
# el corrimiento del QR más abajo).
ANCHO_CARACTER_XM_PT = 24

# Capacidad de datos en modo alfanumérico por versión de QR, nivel de
# corrección M -- estándar ISO/IEC 18004 (no específico de SATO), usado
# para estimar cuántos módulos por lado va a tener el QR según el largo del
# identificador y así poder centrarlo horizontalmente (módulos = 4*versión
# + 17, misma fórmula del estándar). Los identificadores reales de este
# sistema (SOL-AAAA-NNN, SAMP-AAAA-NNNN: 12-14 caracteres) entran cómodos
# en la versión 1 -- la tabla llega hasta la versión 6 (154 caracteres) con
# margen de sobra; si algún identificador fuera más largo que eso, se
# estima con la versión más grande de la tabla en vez de fallar (queda
# centrado de forma aproximada, no exacta, en ese caso extremo).
_CAPACIDAD_ALFANUMERICA_QR_M = {1: 20, 2: 38, 3: 61, 4: 90, 5: 122, 6: 154}


def _modulos_qr(cantidad_caracteres: int) -> int:
    for version in sorted(_CAPACIDAD_ALFANUMERICA_QR_M):
        if cantidad_caracteres <= _CAPACIDAD_ALFANUMERICA_QR_M[version]:
            return 4 * version + 17
    return 4 * max(_CAPACIDAD_ALFANUMERICA_QR_M) + 17


def generar_sbpl_etiqueta(datos: dict, ancho_mm: int, alto_mm: int, dpi: int, cantidad_copias: int = 1) -> bytes:
    """Arma el comando SBPL completo para una etiqueta de muestra, con los
    MISMOS campos, mismo orden y mismo criterio de énfasis por tamaño que
    la etiqueta en PDF (ver generar_pdf_etiqueta_muestra / _dibujar_etiqueta
    en app/services/pdf_solicitud_muestreo.py) -- no técnicamente idéntico
    pixel a pixel (dos tecnologías de impresión distintas), pero deben verse
    como la misma etiqueta al ojo del operador.

    `datos` (ver _datos_etiqueta_para_impresion en app/api/routes/muestras.py):
        titulo ("MUESTRA PARA ANÁLISIS"/"TESTIGO"/"CONTRAMUESTRA"/"MUESTRA",
        mismo texto que el título del PDF -- ver
        app.services.formato.titulo_etiqueta_por_tipo), identificador,
        erp_codart, erp_desart, nro_ir, cantidad_texto, laboratorio_nombre,
        fecha (date/datetime u None), iniciales_muestreador,
        cantidad_muestra_texto (opcional -- cantidad definida en
        lims_especificacion_muestras para el tipo de muestra puntual de
        esta etiqueta, ver imprimir_etiqueta_directo en muestras.py; cuando
        está presente reemplaza a cantidad_texto en el campo "Cantidad",
        mismo criterio que sigue el PDF entre generar_pdf_etiquetas_v2 y
        generar_pdf_etiqueta_muestra).

    El texto de cada comando se codifica en latin-1 (SBPL trabaja
    primariamente en ASCII; latin-1 cubre los acentos/ñ del español sin
    romper el resto del comando, a diferencia de utf-8 que generaría bytes
    multi-byte que SBPL no interpreta como texto) -- ver _cmd(). El
    resultado final va envuelto en STX/ETX, sin lo cual la impresora no
    reconoce el payload como un comando (ver nota al principio del archivo)."""
    ancho_pt = mm_a_puntos(ancho_mm, dpi)
    alto_pt = mm_a_puntos(alto_mm, dpi)

    margen = mm_a_puntos(3, dpi)
    salto = mm_a_puntos(5, dpi)
    v = margen
    h = margen

    comandos = [_cmd("A")]

    # Diagnóstico de posiciones (punto 3 de este pedido): un log con la
    # posición H, ancho estimado y borde derecho (H+ancho) de cada campo
    # que tiene <H>, para identificar CUÁL campo puntual se pasa del ancho
    # total configurado, en vez de ajustar posiciones a ciegas. Se llena a
    # medida que se arma cada campo (abajo) y se loguea junto antes de
    # devolver el payload.
    diagnostico = []  # (nombre, h_campo, ancho_estimado_pt)

    # Corrección de origen -- <A3> desplaza el punto de origen de toda la
    # etiqueta de una sola vez (en vez de tocar cada <H> individualmente).
    # Va justo después de <A> y antes de <A1>, así aplica a todo lo que
    # sigue. Arrancó en +5mm a la derecha; ahora se le resta un ancho de
    # carácter (ANCHO_CARACTER_XM_PT) para correr todo un poco hacia la
    # izquierda -- el diagnóstico de abajo muestra las posiciones YA con
    # esta corrección aplicada (las reales que la impresora recibe).
    correccion_h_pt = mm_a_puntos(CORRECCION_DERECHA_MM, dpi) - ANCHO_CARACTER_XM_PT
    signo_correccion_h = "+" if correccion_h_pt >= 0 else "-"
    comandos.append(_cmd("A3", f"V0000H{signo_correccion_h}{abs(correccion_h_pt):04d}"))

    comandos.append(_cmd("A1", f"{alto_pt:04d}{ancho_pt:04d}"))

    def campo(texto: str, multiplicador: int = MULTIPLICADOR_BASE, avance: int = None, nombre_diag: str = None):
        """Si el multiplicador pedido no entra en el ancho disponible (a
        diferencia de IR/LOTE y Cantidad en CUARENTENA/APROBADO, acá el
        contenido es variable -- cantidad_texto/nro_referencia los carga el
        usuario, no hay garantía de que el valor real sea corto como en las
        pruebas), se cae a 1x en vez de desbordar -- mismo criterio adaptativo
        que ya usa el PDF de esta etiqueta (baja de fuente cuando el nombre
        del producto es largo, ver _ESTILO_NOMBRE_ETIQUETA_CHICO en
        pdf_solicitud_muestreo.py)."""
        nonlocal v
        ancho_disponible = ancho_pt - h - margen
        if len(texto) * ANCHO_CARACTER_XM_PT * multiplicador > ancho_disponible:
            multiplicador = MULTIPLICADOR_BASE
        comandos.append(_cmd("V", f"{v:04d}"))
        comandos.append(_cmd("H", f"{h:04d}"))
        comandos.append(_cmd("L", f"{multiplicador:02d}{multiplicador:02d}"))
        comandos.append(_cmd("XM", texto))
        diagnostico.append((nombre_diag or texto[:24], h, len(texto) * ANCHO_CARACTER_XM_PT * multiplicador))
        v += avance if avance is not None else salto

    # Título -- mismo texto que ya usa el PDF de esta etiqueta
    # (generar_pdf_etiqueta_muestra/generar_pdf_etiquetas_v2 en
    # pdf_solicitud_muestreo.py: "MUESTRA PARA ANÁLISIS"/"TESTIGO"/
    # "CONTRAMUESTRA"/"MUESTRA") como primer renglón, para que ambas
    # versiones de la etiqueta se vean iguales (mismos campos, mismo orden).
    # Reemplaza al campo "Tipo: X" que antes iba al final (misma
    # información, ahora en la misma posición que el PDF).
    campo(_texto(datos.get("titulo")), nombre_diag="Título")

    campo(_texto(datos.get("identificador")), nombre_diag="Identificador")
    # Nombre del producto: se mantiene al tamaño base -- un intento anterior
    # de agrandarlo en esta etiqueta puntual desbordó el margen en la
    # impresora real y se revirtió (ver MULTIPLICADOR_BASE más arriba). El
    # PDF sí lo muestra más grande que el resto, pero acá no hay margen para
    # replicarlo sin repetir ese problema -- misma etiqueta física
    # (100x85mm) donde ya se confirmó el desborde.
    campo(_texto(datos.get("erp_desart"))[:40], nombre_diag="Nombre del producto")

    # Código e IR/LOTE: en el PDF son dos renglones separados (antes acá iban
    # en una sola línea combinada). IR/LOTE se imprimía notablemente más
    # grande que el resto (2x) -- se bajó a 1x (mismo tamaño que el resto de
    # los campos) porque en la impresión real se veía demasiado grande;
    # <L> solo admite multiplicadores ENTEROS (01-12, no hay fracciones),
    # así que con la misma fuente <XM> 1x es el único paso disponible por
    # debajo de 2x.
    campo(_texto(datos.get("erp_codart")), nombre_diag="Código")
    etiqueta_ref = datos.get("etiqueta_referencia") or "IR"
    campo(f"{etiqueta_ref}: {_texto(datos.get('nro_ir'))}", nombre_diag=etiqueta_ref)

    # Cantidad: un solo campo (antes eran dos -- "Ingreso" y "Cantidad
    # muestra" -- el PDF solo tiene uno). Cuando esta etiqueta puntual tiene
    # un tipo de muestra confirmado (ver imprimir_etiqueta_directo en
    # muestras.py), usa la cantidad de ESE tipo; si no, la cantidad general
    # de la muestra -- mismo criterio que ya sigue el PDF entre
    # generar_pdf_etiquetas_v2 y generar_pdf_etiqueta_muestra. Mismo tamaño
    # base que el resto (antes 2x, ver nota de IR/LOTE arriba).
    cantidad_final = datos.get("cantidad_muestra_texto") or datos.get("cantidad_texto")
    campo(f"Cantidad: {_texto(cantidad_final)}", nombre_diag="Cantidad")

    if datos.get("laboratorio_nombre"):
        campo(f"Lab: {datos['laboratorio_nombre']}", nombre_diag="Laboratorio")

    fecha = datos.get("fecha")
    fecha_texto = fecha.strftime("%d/%m/%Y") if fecha else "-"
    linea_fecha = f"Fecha: {fecha_texto}"
    if datos.get("iniciales_muestreador"):
        linea_fecha += f"  Muestreador: {datos['iniciales_muestreador']}"
    campo(linea_fecha, nombre_diag="Fecha + muestreador")

    # Punto 3 de ESTE pedido: el QR se corrió 5 renglones más arriba de la
    # posición que tenía en el pedido anterior (v + 2*salto) -- misma
    # referencia de altura de línea (`salto`) que ya se usaba ahí:
    # v + 2*salto - 5*salto = v - 3*salto.
    codigo_qr = _texto(datos.get("identificador"))
    tamano_celda_qr = max(1, min(32, mm_a_puntos(TAMANO_CELDA_QR_MM, dpi)))
    ancho_qr_pt = _modulos_qr(len(codigo_qr)) * tamano_celda_qr
    v_qr = v + 2 * salto - 5 * salto
    # Alineado contra el margen derecho (pedido anterior), corrido ahora un
    # ancho de carácter más hacia la izquierda (ANCHO_CARACTER_XM_PT, la
    # misma unidad "una letra" que ya usa el resto del layout).
    margen_derecho_qr_pt = mm_a_puntos(MARGEN_DERECHO_QR_PT_MM, dpi)
    h_qr = ancho_pt - ancho_qr_pt - margen_derecho_qr_pt - ANCHO_CARACTER_XM_PT
    comandos.append(_cmd("V", f"{v_qr:04d}"))
    comandos.append(_cmd("H", f"{h_qr:04d}"))
    comandos.append(_cmd("2D30", f",{NIVEL_CORRECCION_QR},{tamano_celda_qr:02d},0,0"))
    comandos.append(_cmd("DS", f"2,{codigo_qr}"))
    diagnostico.append(("QR", h_qr, ancho_qr_pt))

    # Punto 2 de ESTE pedido: recuadro LANDSCAPE (más ancho que alto), no
    # portrait -- alto FIJO de RECUADRO_ALTO_CM, ancho el de toda la
    # etiqueta (con el mismo margen que ya tenía). Es al revés del intento
    # anterior (ahí el ancho era el fijo y el alto ocupaba toda la
    # etiqueta -- daba portrait, un recuadro angosto y alto).
    #
    # CORRECCIÓN de un intento previo a este: <FW> en modo "Grid" (una sola
    # invocación, aabbVccccHdddd) en realidad dibuja UNA línea vertical +
    # UNA línea horizontal desde la misma esquina -- son las piezas para
    # armar una grilla de tabla (de ahí el nombre), NO un rectángulo
    # cerrado. Por eso faltaba el lado de cierre en la impresión real. Un
    # rectángulo completo se arma con 4 líneas rectas independientes, modo
    # "Rule" (<FW>aabcccc: a=grosor, b=H o V, c=largo) -- inequívoco, cada
    # invocación es UNA sola línea recta.
    # Punto 1 de ESTE pedido: el borde derecho quedaba justo en el límite
    # (o pasado) del área imprimible real y no se veía -- se achica el
    # ancho del recuadro en un ancho de carácter (ANCHO_CARACTER_XM_PT) del
    # lado derecho, mismo criterio que ya se usó para correr el QR.
    alto_recuadro_pt = mm_a_puntos(RECUADRO_ALTO_CM * 10, dpi)
    ancho_recuadro_pt = ancho_pt - 2 * MARGEN_RECUADRO_PT - ANCHO_CARACTER_XM_PT
    v_recuadro = MARGEN_RECUADRO_PT
    h_recuadro = MARGEN_RECUADRO_PT

    # Borde superior (horizontal).
    comandos.append(_cmd("V", f"{v_recuadro:04d}"))
    comandos.append(_cmd("H", f"{h_recuadro:04d}"))
    comandos.append(_cmd("FW", f"{GROSOR_RECUADRO_PT:02d}H{ancho_recuadro_pt:04d}"))
    # Borde inferior (horizontal, mismo largo, al pie del recuadro).
    comandos.append(_cmd("V", f"{v_recuadro + alto_recuadro_pt:04d}"))
    comandos.append(_cmd("H", f"{h_recuadro:04d}"))
    comandos.append(_cmd("FW", f"{GROSOR_RECUADRO_PT:02d}H{ancho_recuadro_pt:04d}"))
    # Borde izquierdo (vertical).
    comandos.append(_cmd("V", f"{v_recuadro:04d}"))
    comandos.append(_cmd("H", f"{h_recuadro:04d}"))
    comandos.append(_cmd("FW", f"{GROSOR_RECUADRO_PT:02d}V{alto_recuadro_pt:04d}"))
    # Borde derecho (vertical, mismo largo, en el borde derecho del recuadro).
    comandos.append(_cmd("V", f"{v_recuadro:04d}"))
    comandos.append(_cmd("H", f"{h_recuadro + ancho_recuadro_pt:04d}"))
    comandos.append(_cmd("FW", f"{GROSOR_RECUADRO_PT:02d}V{alto_recuadro_pt:04d}"))

    diagnostico.append(("Recuadro", h_recuadro, ancho_recuadro_pt))

    comandos.append(_cmd("Q", str(cantidad_copias)))
    comandos.append(_cmd("Z"))

    logger.info("=== Diagnóstico de posiciones SBPL -- ancho etiqueta configurado: %dmm = %dpt (dpi=%d) ===", ancho_mm, ancho_pt, dpi)
    for nombre, h_campo, ancho_campo in diagnostico:
        borde_derecho = h_campo + ancho_campo
        aviso = "  <-- SE PASA DEL ANCHO TOTAL" if borde_derecho > ancho_pt else ""
        logger.info(
            "  %-22s H=%4d  ancho=%4d  H+ancho=%4d%s",
            nombre, h_campo, ancho_campo, borde_derecho, aviso,
        )

    return STX + b"".join(comandos) + ETX


# Fuente <XS> (17x17 dots básicos, contra 24x24 de <XM>) -- usada SOLO en
# generar_sbpl_etiqueta_par (dos muestras por etiqueta física) para que el
# layout completo entre en la mitad del alto disponible. Sintaxis <XS>n-n
# verificada contra el mismo manual ya citado para el resto de los comandos
# de este archivo ("SATO Barcode Programming Language for Enhanced Printer
# Models", sección "ESC+XS XS Font Specification", tamaño básico 17x17 dots
# confirmado -- no inventado).
ANCHO_CARACTER_XS_PT = 17
# QR de cada mitad: celda más chica que TAMANO_CELDA_QR_MM (la de
# generar_sbpl_etiqueta) para acompañar proporcionalmente el texto más
# chico -- con margen de sobra igual (ver el cálculo de espacio en el
# pedido de esta función), no hace falta llevarla al mínimo como en la
# etiqueta CUARENTENA (TAMANO_CELDA_QR_ESTADO_MM), que sí tenía el alto muy
# ajustado.
TAMANO_CELDA_QR_CONDENSADA_MM = 0.6


def generar_sbpl_etiqueta_par(
    etiqueta_arriba: dict, etiqueta_abajo: Optional[dict],
    ancho_mm: int, alto_mm: int, dpi: int, cantidad_copias: int = 1,
) -> bytes:
    """Etiqueta de MUESTRA combinada: dos muestras en una sola etiqueta
    física (una arriba, una abajo, separadas por una línea horizontal) --
    el rollo es continuo (no hay largo de etiqueta fijo más allá de
    ancho_mm/alto_mm), así que combinar de a dos reduce a la mitad la
    cantidad de etiquetas físicas usadas al imprimir una lista completa
    (ver armar_pares_etiquetas_muestra en app/api/routes/muestras.py, que
    arma los pares y llama a esta función una vez por par).

    Layout condensado (fuente <XS>, ver ANCHO_CARACTER_XS_PT) de los MISMOS
    campos que generar_sbpl_etiqueta -- tipo de muestra, N° de solicitud,
    código, nombre del material, N° de IR/LOTE, cantidad, laboratorio (solo
    si la especificación de esa muestra puntual lo tiene definido), fecha +
    iniciales del muestreador, QR. Cantidad/Laboratorio se habían quedado
    afuera en un ajuste anterior (regresión real: dejaban de imprimirse) --
    hay espacio de sobra en la mitad disponible como para no tener que
    sacar nada, hoy 8 renglones de texto usan ~230pt de los ~339pt de cada
    mitad (100x85mm a 203dpi).

    `etiqueta_arriba`/`etiqueta_abajo`: mismo dict que ya arma
    imprimir_etiqueta_directo para generar_sbpl_etiqueta (titulo,
    identificador, erp_codart, erp_desart, nro_ir, etiqueta_referencia,
    fecha, iniciales_muestreador). `etiqueta_abajo` puede ser None --
    cantidad impar de muestras: la última etiqueta física lleva una sola
    muestra arriba, la mitad de abajo queda vacía (sin contenido, no se
    repite la de arriba)."""
    ancho_pt = mm_a_puntos(ancho_mm, dpi)
    alto_pt = mm_a_puntos(alto_mm, dpi)
    mitad_pt = alto_pt // 2

    margen = mm_a_puntos(3, dpi)
    # Mismo "aire" proporcional que salto (5mm para un glifo XM de 24pt) --
    # escalado al glifo más chico de XS (17pt) en vez de un valor nuevo
    # inventado.
    salto = round(mm_a_puntos(5, dpi) * ANCHO_CARACTER_XS_PT / ANCHO_CARACTER_XM_PT)

    comandos = [_cmd("A")]

    diagnostico = []  # (nombre, v, h, alto, ancho) -- mismo criterio que generar_sbpl_etiqueta_estado

    correccion_h_pt = mm_a_puntos(CORRECCION_DERECHA_MM, dpi) - ANCHO_CARACTER_XM_PT
    signo_correccion_h = "+" if correccion_h_pt >= 0 else "-"
    comandos.append(_cmd("A3", f"V0000H{signo_correccion_h}{abs(correccion_h_pt):04d}"))
    comandos.append(_cmd("A1", f"{alto_pt:04d}{ancho_pt:04d}"))

    def dibujar_mitad(datos: Optional[dict], v_base: int, etiqueta_diag: str):
        """Una mitad completa (hasta 8 renglones de texto -- 7 si no hay
        laboratorio -- + QR) -- no dibuja nada si datos es None (mitad
        vacía, cantidad impar de muestras)."""
        if not datos:
            return
        v = v_base + margen
        h = margen

        def campo(texto: str, avance: int = None, nombre_diag: str = None):
            nonlocal v
            comandos.append(_cmd("V", f"{v:04d}"))
            comandos.append(_cmd("H", f"{h:04d}"))
            comandos.append(_cmd("L", "0101"))
            comandos.append(_cmd("XS", texto))
            diagnostico.append((
                f"{etiqueta_diag} {nombre_diag or texto[:16]}", v, h,
                ANCHO_CARACTER_XS_PT, len(texto) * ANCHO_CARACTER_XS_PT,
            ))
            v += avance if avance is not None else salto

        # Geometría del QR calculada ANTES de dibujar el texto -- el nombre
        # del producto (el único campo de largo variable no acotado por el
        # propio dato, a diferencia de código/IR/fecha) se trunca según el
        # espacio libre real a la izquierda del QR, en vez de un límite fijo
        # de caracteres que podría chocar contra él (ver el diagnóstico de
        # superposición más abajo, que hubiera marcado esto si se dejaba
        # fijo).
        codigo_qr = _texto(datos.get("identificador"))
        tamano_celda_qr = max(1, min(32, mm_a_puntos(TAMANO_CELDA_QR_CONDENSADA_MM, dpi)))
        ancho_qr_pt = _modulos_qr(len(codigo_qr)) * tamano_celda_qr
        margen_derecho_qr_pt = mm_a_puntos(MARGEN_DERECHO_QR_PT_MM, dpi)
        h_qr = ancho_pt - ancho_qr_pt - margen_derecho_qr_pt - ANCHO_CARACTER_XM_PT
        gap_texto_qr_pt = mm_a_puntos(2, dpi)
        max_chars_nombre = max(10, (h_qr - gap_texto_qr_pt - h) // ANCHO_CARACTER_XS_PT)

        campo(_texto(datos.get("titulo")), nombre_diag="Tipo")
        campo(_texto(datos.get("identificador")), nombre_diag="N solicitud")
        campo(_texto(datos.get("erp_codart")), nombre_diag="Codigo")
        campo(_texto(datos.get("erp_desart"))[:max_chars_nombre], nombre_diag="Nombre")
        etiqueta_ref = datos.get("etiqueta_referencia") or "IR"
        campo(f"{etiqueta_ref}: {_texto(datos.get('nro_ir'))}", nombre_diag=etiqueta_ref)

        # Cantidad y Laboratorio -- se habían perdido al pasar a este layout
        # condensado (quedaron afuera de la lista de campos de ese pedido);
        # mismo orden y mismo criterio que generar_sbpl_etiqueta: Cantidad
        # siempre, Laboratorio solo si la especificación de esta muestra
        # puntual lo tiene definido (si no, se omite el campo entero, no se
        # deja un renglón vacío).
        cantidad_final = datos.get("cantidad_muestra_texto") or datos.get("cantidad_texto")
        campo(f"Cant: {_texto(cantidad_final)}", nombre_diag="Cantidad")

        if datos.get("laboratorio_nombre"):
            campo(f"Lab: {datos['laboratorio_nombre']}", nombre_diag="Laboratorio")

        fecha = datos.get("fecha")
        fecha_texto = fecha.strftime("%d/%m/%Y") if fecha else "-"
        linea_fecha = f"Fecha: {fecha_texto}"
        if datos.get("iniciales_muestreador"):
            linea_fecha += f"  Mstr: {datos['iniciales_muestreador']}"
        campo(linea_fecha, nombre_diag="Fecha")

        # QR, mismo dato (identificador) que generar_sbpl_etiqueta -- celda
        # más chica (TAMANO_CELDA_QR_CONDENSADA_MM), alineado contra el
        # margen derecho igual que el de la etiqueta completa.
        v_qr = v_base + margen
        comandos.append(_cmd("V", f"{v_qr:04d}"))
        comandos.append(_cmd("H", f"{h_qr:04d}"))
        comandos.append(_cmd("2D30", f",{NIVEL_CORRECCION_QR},{tamano_celda_qr:02d},0,0"))
        comandos.append(_cmd("DS", f"2,{codigo_qr}"))
        diagnostico.append((f"{etiqueta_diag} QR", v_qr, h_qr, ancho_qr_pt, ancho_qr_pt))

    dibujar_mitad(etiqueta_arriba, 0, "Arriba")
    dibujar_mitad(etiqueta_abajo, mitad_pt, "Abajo")

    # Línea divisoria horizontal entre las dos mitades -- para que quede
    # claro dónde cortar/cuál es cuál si hace falta separarlas a mano.
    ancho_linea_pt = ancho_pt - 2 * margen
    comandos.append(_cmd("V", f"{mitad_pt:04d}"))
    comandos.append(_cmd("H", f"{margen:04d}"))
    comandos.append(_cmd("FW", f"{GROSOR_RECUADRO_PT:02d}H{ancho_linea_pt:04d}"))
    diagnostico.append(("Linea divisoria", mitad_pt, margen, GROSOR_RECUADRO_PT, ancho_linea_pt))

    comandos.append(_cmd("Q", str(cantidad_copias)))
    comandos.append(_cmd("Z"))

    # Diagnóstico de posiciones -- mismo criterio (superposición real en V Y
    # en H, no solo "el siguiente de la lista") que ya usa
    # generar_sbpl_etiqueta_estado, para poder confirmar por log que las dos
    # mitades no se pisan entre sí ni con la línea divisoria.
    def _se_superponen(a, b):
        _, av, ah, aalto, aancho = a
        _, bv, bh, balto, bancho = b
        return av < bv + balto and bv < av + aalto and ah < bh + bancho and bh < ah + aancho

    logger.info(
        "=== Diagnóstico de posiciones SBPL (etiqueta de muestra combinada) -- %dmm x %dmm = %dpt alto x %dpt ancho, mitad=%dpt (dpi=%d) ===",
        ancho_mm, alto_mm, alto_pt, ancho_pt, mitad_pt, dpi,
    )
    for idx, item in enumerate(diagnostico):
        nombre, v_elem, h_elem, alto_elem, ancho_elem = item
        borde_inferior = v_elem + alto_elem
        borde_derecho = h_elem + ancho_elem
        avisos = []
        if borde_inferior > alto_pt:
            avisos.append("SE PASA DEL ALTO TOTAL")
        if borde_derecho > ancho_pt:
            avisos.append("SE PASA DEL ANCHO TOTAL")
        choques = [otro[0] for j, otro in enumerate(diagnostico) if j != idx and _se_superponen(item, otro)]
        if choques:
            avisos.append(f"CHOCA CON {choques}")
        logger.info(
            "  %-24s V=%4d H=%4d alto=%4d ancho=%4d V+alto=%4d H+ancho=%4d%s",
            nombre, v_elem, h_elem, alto_elem, ancho_elem, borde_inferior, borde_derecho,
            f"  <-- {', '.join(avisos)}" if avisos else "",
        )

    return STX + b"".join(comandos) + ETX


def _envolver_texto(texto: str, max_chars: int, max_lineas: int) -> list[str]:
    """Reparte `texto` en hasta `max_lineas` líneas de como máximo
    `max_chars` cada una, cortando por palabra completa -- SBPL no tiene
    wrap automático (<XM> imprime todo en una sola línea), así que hay que
    partirlo antes de mandarlo. Si sobran palabras después de llenar
    `max_lineas`, la última línea queda truncada con "…" (mismo criterio que
    _truncar_a_ancho en pdf_solicitud_muestreo.py para el mismo problema en
    el PDF)."""
    palabras = texto.split()
    lineas: list[str] = []
    actual = ""
    i = 0
    while i < len(palabras) and len(lineas) < max_lineas:
        candidato = f"{actual} {palabras[i]}".strip()
        if len(candidato) <= max_chars or not actual:
            actual = candidato
            i += 1
        else:
            lineas.append(actual)
            actual = ""
    if actual:
        lineas.append(actual)
    if i < len(palabras) and lineas:
        # Quedaron palabras sin entrar -- la última línea se trunca con "…"
        # en vez de perderlas en silencio sin ninguna marca visual.
        ultima = lineas[-1]
        lineas[-1] = ultima[: max_chars - 1].rstrip() + "…" if len(ultima) >= max_chars - 1 else ultima + "…"
    return lineas or [""]


def generar_sbpl_etiqueta_estado(datos: dict, titulo: str, ancho_mm: int, alto_mm: int, dpi: int, cantidad_copias: int = 1) -> bytes:
    """Etiqueta CUARENTENA/APROBADO/RECHAZADO -- mismo mecanismo SBPL que
    generar_sbpl_etiqueta (etiqueta de muestra), layout propio: título
    grande, nombre del producto (hasta 2 líneas), IR/lote, código + bulto/s
    (combinados en un renglón), fechas de ingreso y vencimiento (combinadas
    en otro), cantidad, grilla de 6 casilleros vacíos, QR y código de
    barras CODE128, más el logo al pie. NO lleva lote de proveedor ni
    proveedor (a diferencia de la etiqueta de muestra) -- confirmado que no
    corresponde acá.

    `datos`:
        erp_desart, erp_codart, nro_ir, etiqueta_referencia ("IR"/"LOTE"/
        "Ref", ver app/services/formato.py), fecha_ingreso, fecha_vencimiento
        (date u None), bulto_actual, bulto_total (int), cantidad_texto (ya
        formateada, ver formatear_cantidad), cantidad_valor (el mismo dato
        SIN formatear ni unidad -- Optional[float], lo que va en el QR)."""
    ancho_pt = mm_a_puntos(ancho_mm, dpi)
    alto_pt = mm_a_puntos(alto_mm, dpi)

    margen = mm_a_puntos(3, dpi)
    salto = mm_a_puntos(5, dpi)
    v = margen

    comandos = [_cmd("A")]

    correccion_h_pt = mm_a_puntos(CORRECCION_DERECHA_MM, dpi) - ANCHO_CARACTER_XM_PT
    signo_correccion_h = "+" if correccion_h_pt >= 0 else "-"
    comandos.append(_cmd("A3", f"V0000H{signo_correccion_h}{abs(correccion_h_pt):04d}"))
    comandos.append(_cmd("A1", f"{alto_pt:04d}{ancho_pt:04d}"))

    # Avance vertical para un campo a 2x -- mismo criterio de "aire" que ya
    # usan los campos a 1x (salto = 40pt, 16pt de margen sobre un glifo de
    # 24pt de alto): a 2x el glifo mide 48pt, así que el avance análogo es
    # 48 + 16 = salto + ANCHO_CARACTER_XM_PT, no simplemente salto*2 (eso
    # dejaría el doble de aire del que corresponde y no entraba todo el
    # contenido antes del logo al pie).
    AVANCE_2X = salto + ANCHO_CARACTER_XM_PT

    def campo(texto: str, multiplicador: int = MULTIPLICADOR_BASE, avance: int = None):
        """Centrado horizontal real: la posición <H> se calcula según el
        ancho efectivo del texto (cantidad de caracteres * ancho de
        carácter * multiplicador), no una posición fija -- así cada campo
        queda centrado de verdad sin importar cuán largo sea. Con texto
        vacío no manda nada (para "reservar" un renglón sin imprimir nada
        ahí, ver el nombre del producto más abajo), pero igual avanza v."""
        nonlocal v
        if texto:
            ancho_texto_pt = len(texto) * ANCHO_CARACTER_XM_PT * multiplicador
            h_campo = max(margen, (ancho_pt - ancho_texto_pt) // 2)
            comandos.append(_cmd("V", f"{v:04d}"))
            comandos.append(_cmd("H", f"{h_campo:04d}"))
            comandos.append(_cmd("L", f"{multiplicador:02d}{multiplicador:02d}"))
            comandos.append(_cmd("XM", texto))
        v += avance if avance is not None else salto

    # Título grande (CUARENTENA / APROBADO) -- 2x. Después del título se deja
    # UN renglón en blanco de más (+salto extra) antes del nombre del
    # producto -- mismo criterio de espaciado que el resto de la etiqueta,
    # solo que acá se pide explícitamente un renglón de aire de más.
    MULT_TITULO = 2
    campo(titulo, multiplicador=MULT_TITULO, avance=AVANCE_2X + salto)

    # Nombre del producto: 2x (un paso de <L> más grande que el resto de los
    # campos, mismo criterio que el título) y SIEMPRE 2 renglones
    # reservados -- si el nombre entra en 1 sola línea, el segundo renglón
    # queda vacío (no imprime nada, ver campo() de arriba) pero v igual
    # avanza como si hubiera 2, así los campos de abajo arrancan siempre en
    # la misma posición sin importar cuán largo sea el nombre.
    MULT_PRODUCTO = 2
    ancho_util_pt = ancho_pt - 2 * margen - ANCHO_CARACTER_XM_PT
    max_chars_producto = max(1, ancho_util_pt // (ANCHO_CARACTER_XM_PT * MULT_PRODUCTO))
    lineas_producto = _envolver_texto(_texto(datos.get("erp_desart")), max_chars_producto, max_lineas=2)
    lineas_producto += [""] * (2 - len(lineas_producto))
    for linea_producto in lineas_producto:
        campo(linea_producto, multiplicador=MULT_PRODUCTO, avance=AVANCE_2X)

    # IR/LOTE: 2x, mismo criterio que el nombre del producto (un paso de <L>
    # más grande que el resto). La etiqueta ("IR"/"LOTE"/"Ref") ya viene
    # resuelta por el llamador con app.services.formato.etiqueta_referencia
    # -- no se resuelve de nuevo acá, para no duplicar esa lógica.
    MULT_REFERENCIA = 2
    etiqueta_ref = datos.get("etiqueta_referencia") or "IR"
    campo(f"{etiqueta_ref} N°: {_texto(datos.get('nro_ir'))}", multiplicador=MULT_REFERENCIA, avance=AVANCE_2X)

    def fecha_texto(valor):
        return valor.strftime("%d/%m/%y") if valor else "-"

    # Grilla, QR y código de barras (agregados a esta etiqueta): para
    # hacerles lugar sin sacar ningún dato de los que ya había, "Código" se
    # combina con "Bulto/s" en un renglón y las dos fechas en otro (antes 4
    # renglones sueltos) -- mismos datos, con etiquetas más cortas para que
    # la línea combinada entre en el ancho de la etiqueta (799pt a 203dpi,
    # 24pt/carácter a 1x: "Código:"+"Fecha de Ingreso:"/"Fecha de
    # vencimiento:" completos no entraban combinados en una sola línea,
    # "Cód:"/"Ing:"/"Venc:" sí). El salto entre estos renglones y "Cantidad"
    # también se achica (SALTO_COMPACTO en vez de salto) -- ninguno de los
    # dos cambios toca el tamaño de letra de ningún campo, solo el espacio
    # entre renglones y el texto de la etiqueta de cada uno.
    SALTO_COMPACTO = mm_a_puntos(4, dpi)
    campo(
        f"Cód: {_texto(datos.get('erp_codart'))}   Bultos: {_texto(datos.get('bulto_actual'))}/{_texto(datos.get('bulto_total'))}",
        avance=SALTO_COMPACTO,
    )
    campo(
        f"Ing: {fecha_texto(datos.get('fecha_ingreso'))}   Venc: {fecha_texto(datos.get('fecha_vencimiento'))}",
        avance=SALTO_COMPACTO,
    )
    campo(f"Cantidad: {_texto(datos.get('cantidad_texto'))}", avance=SALTO_COMPACTO)

    diagnostico = []  # (nombre, v, h, alto, ancho) -- mismo criterio de diagnóstico que ya usa generar_sbpl_etiqueta

    # Grilla de 6 casilleros vacíos, para anotar a mano cantidades restantes
    # durante la vida del bulto -- ancho completo de la etiqueta (mismo
    # margen que el resto de los campos de esta función: acá no hay
    # recuadro exterior al que pegarse, a diferencia de la etiqueta de
    # muestra) y alto igual al que ya ocupa UN renglón del nombre del
    # producto (AVANCE_2X -- la misma medida que usan las 2 líneas
    # reservadas para erp_desart más arriba, no un valor nuevo). El
    # contorno y las 5 divisiones internas se arman con 7 líneas verticales
    # (<FW> modo "Rule", ver nota del módulo) más 2 horizontales -- mismo
    # mecanismo que el recuadro de generar_sbpl_etiqueta.
    CANTIDAD_CASILLEROS = 6
    alto_grilla_pt = AVANCE_2X
    ancho_grilla_pt = ancho_pt - 2 * margen
    h_grilla = margen
    v_grilla = v

    comandos.append(_cmd("V", f"{v_grilla:04d}"))
    comandos.append(_cmd("H", f"{h_grilla:04d}"))
    comandos.append(_cmd("FW", f"{GROSOR_RECUADRO_PT:02d}H{ancho_grilla_pt:04d}"))
    comandos.append(_cmd("V", f"{v_grilla + alto_grilla_pt:04d}"))
    comandos.append(_cmd("H", f"{h_grilla:04d}"))
    comandos.append(_cmd("FW", f"{GROSOR_RECUADRO_PT:02d}H{ancho_grilla_pt:04d}"))
    for i in range(CANTIDAD_CASILLEROS + 1):
        h_linea = h_grilla + round(i * ancho_grilla_pt / CANTIDAD_CASILLEROS)
        comandos.append(_cmd("V", f"{v_grilla:04d}"))
        comandos.append(_cmd("H", f"{h_linea:04d}"))
        comandos.append(_cmd("FW", f"{GROSOR_RECUADRO_PT:02d}V{alto_grilla_pt:04d}"))
    diagnostico.append(("Grilla 6 casilleros", v_grilla, h_grilla, alto_grilla_pt, ancho_grilla_pt))

    v = v_grilla + alto_grilla_pt + mm_a_puntos(GAP_ANTES_CODIGOS_MM, dpi)

    # QR (inventario rápido) y código de barras CODE128, mismo dato
    # combinado (código de artículo + IR/LOTE), el QR además con la
    # cantidad (solo el número, sin unidad -- ver cantidad_valor). Separador
    # "*" en vez del "|" original: el modo Alfanumérico del QR (<DS>2,...>,
    # el mismo que ya usa generar_sbpl_etiqueta) solo admite el set de 45
    # caracteres del estándar ISO/IEC 18004 (0-9, A-Z, espacio y $%*+-./:) --
    # "|" no forma parte de ese set y el símbolo quedaría mal formado; "*"
    # sí, y no aparece en ningún código de artículo/IR/lote real de esta
    # base (verificado contra los datos reales de lims_muestras). Mismo
    # separador en el código de barras -- CODE128 no tiene esa restricción,
    # pero usar el mismo separador en los dos códigos evita mantener dos
    # formatos distintos para el mismo dato.
    codigo_articulo = _texto(datos.get("erp_codart"))
    ir_o_lote = _texto(datos.get("nro_ir"))
    cantidad_valor_texto = formatear_cantidad(datos.get("cantidad_valor")) or "-"
    dato_codigo_barras = f"{codigo_articulo}*{ir_o_lote}"
    dato_qr = f"{dato_codigo_barras}*{cantidad_valor_texto}"

    v_codigos = v
    alto_disponible_codigos_pt = (
        alto_pt - mm_a_puntos(MARGEN_INFERIOR_FOOTER_MM, dpi) - _LOGO_ALTO_PX
        - mm_a_puntos(GAP_CODIGOS_A_FOOTER_MM, dpi) - v_codigos
    )

    # QR a la izquierda -- celda de tamaño fijo (TAMANO_CELDA_QR_ESTADO_MM),
    # achicada solo si con el dato real (más largo de lo esperado) no
    # entraría en el alto disponible -- mismo criterio "cae a un tamaño que
    # entre en vez de desbordar" que ya usa campo() más arriba en este
    # archivo.
    modulos_qr = _modulos_qr(len(dato_qr))
    tamano_celda_qr = max(1, min(32, mm_a_puntos(TAMANO_CELDA_QR_ESTADO_MM, dpi)))
    while modulos_qr * tamano_celda_qr > alto_disponible_codigos_pt and tamano_celda_qr > 1:
        tamano_celda_qr -= 1
    ancho_qr_pt = modulos_qr * tamano_celda_qr

    comandos.append(_cmd("V", f"{v_codigos:04d}"))
    comandos.append(_cmd("H", f"{h_grilla:04d}"))
    comandos.append(_cmd("2D30", f",{NIVEL_CORRECCION_QR},{tamano_celda_qr:02d},0,0"))
    comandos.append(_cmd("DS", f"2,{dato_qr}"))
    diagnostico.append(("QR", v_codigos, h_grilla, ancho_qr_pt, ancho_qr_pt))

    # Código de barras CODE128, alineado contra el margen derecho de la
    # etiqueta (el QR queda donde está, a la izquierda, sin moverse) --
    # <BG>aabbbn-n (a=ancho de barra angosta en dots, b=alto en dots,
    # n=dato; el dígito verificador se genera solo, ver nota del módulo).
    # El alto objetivo es fijo (ALTO_BARCODE_MM) -- a diferencia del QR, no
    # depende del largo del dato -- pero igual se achica si no entra en el
    # alto disponible (mismo criterio que el QR de arriba), con un piso
    # (ALTO_BARCODE_MINIMO_PT) para no terminar con un código tan bajo que
    # ya no sea confiable de escanear.
    alto_barcode_pt = max(ALTO_BARCODE_MINIMO_PT, min(mm_a_puntos(ALTO_BARCODE_MM, dpi), alto_disponible_codigos_pt))

    # Ancho real del símbolo (MODULOS_OVERHEAD_CODE128/MODULOS_POR_CARACTER_CODE128,
    # ver esas constantes) -- con esto ya se puede calcular <H> igual que el
    # QR de la etiqueta de muestra (ancho total - ancho del elemento -
    # margen derecho deseado, con la misma corrección de un ancho de
    # carácter hacia la izquierda que ya usa esa etiqueta -- "mismo
    # criterio" pedido, no una fórmula distinta).
    ancho_barcode_pt = (MODULOS_POR_CARACTER_CODE128 * len(dato_codigo_barras) + MODULOS_OVERHEAD_CODE128) * ANCHO_BARRA_CODE128_PT
    margen_derecho_barcode_pt = mm_a_puntos(MARGEN_DERECHO_BARCODE_MM, dpi)
    h_barcode = ancho_pt - ancho_barcode_pt - margen_derecho_barcode_pt - ANCHO_CARACTER_XM_PT

    # Si el dato fuera tan largo que el código de barras, ya alineado a la
    # derecha, invadiera el lugar del QR (que no se mueve de la izquierda),
    # se lo corre lo mínimo indispensable para que no se pisen -- con datos
    # reales (código de artículo + IR/LOTE, siempre cortos) esto no debería
    # activarse nunca, pero es más seguro que dejar que se superpongan en
    # silencio.
    h_barcode_minimo = h_grilla + ancho_qr_pt + mm_a_puntos(GAP_ANTES_CODIGOS_MM, dpi)
    h_barcode = max(h_barcode, h_barcode_minimo)

    comandos.append(_cmd("V", f"{v_codigos:04d}"))
    comandos.append(_cmd("H", f"{h_barcode:04d}"))
    comandos.append(_cmd("BG", f"{ANCHO_BARRA_CODE128_PT:02d}{alto_barcode_pt:03d}{dato_codigo_barras}"))
    diagnostico.append(("Código de barras", v_codigos, h_barcode, alto_barcode_pt, ancho_barcode_pt))

    v = v_codigos + max(ancho_qr_pt, alto_barcode_pt)

    # Logo + razón social, al pie -- centrados como UN solo bloque (logo +
    # espacio + texto), no cada uno por separado, para que el conjunto quede
    # centrado en vez de descentrado hacia la izquierda. <L>0101 explícito
    # antes del gráfico para no heredar el multiplicador 2x que haya quedado
    # de los campos de arriba (el manual confirma que <L> también afecta a
    # <GP>: "Both the rotation <%> and enlargement <L> commands can be used").
    texto_footer = "Laboratorio Lamar S.R.L."
    gap_footer_pt = mm_a_puntos(2, dpi)
    ancho_texto_footer_pt = len(texto_footer) * ANCHO_CARACTER_XM_PT
    ancho_bloque_footer = _LOGO_ANCHO_PX + gap_footer_pt + ancho_texto_footer_pt
    h_footer = max(margen, (ancho_pt - ancho_bloque_footer) // 2)

    # Margen inferior reducido (MARGEN_INFERIOR_FOOTER_MM en vez de margen)
    # -- ver el comentario de esa constante: es el lugar que hacía falta
    # liberar para la grilla y el QR/código de barras de más arriba.
    v_footer = alto_pt - mm_a_puntos(MARGEN_INFERIOR_FOOTER_MM, dpi) - _LOGO_ALTO_PX
    diagnostico.append(("Logo + razón social (pie)", v_footer, h_footer, _LOGO_ALTO_PX, ancho_bloque_footer))
    comandos.append(_cmd("V", f"{v_footer:04d}"))
    comandos.append(_cmd("H", f"{h_footer:04d}"))
    comandos.append(_cmd("L", "0101"))
    comandos.append(_cmd_grafico_pcx(_LOGO_PCX_BYTES))

    # Texto de la razón social, a la derecha del logo, centrado verticalmente
    # contra el alto del logo (fuente base 24pt de alto a 1x -- se corrige
    # con (_LOGO_ALTO_PX - ANCHO_CARACTER_XM_PT)//2 para que el renglón de
    # texto quede a mitad de altura del ícono, no pegado arriba).
    h_footer_texto = h_footer + _LOGO_ANCHO_PX + gap_footer_pt
    v_footer_texto = v_footer + (_LOGO_ALTO_PX - ANCHO_CARACTER_XM_PT) // 2
    comandos.append(_cmd("V", f"{v_footer_texto:04d}"))
    comandos.append(_cmd("H", f"{h_footer_texto:04d}"))
    comandos.append(_cmd("L", "0101"))
    comandos.append(_cmd("XM", texto_footer))

    comandos.append(_cmd("Q", str(cantidad_copias)))
    comandos.append(_cmd("Z"))

    # Diagnóstico de posiciones -- mismo criterio que ya usa
    # generar_sbpl_etiqueta: loguea cada elemento agregado por este pedido
    # (grilla, QR, código de barras, pie) con su caja (V/H + alto/ancho), y
    # avisa si alguno se pasa del alto total de la etiqueta o si su caja se
    # superpone de verdad (en V Y en H) con la de otro elemento -- comparado
    # contra TODOS los demás, no solo "el siguiente de la lista", para no
    # marcar como choque el QR y el código de barras (comparten el mismo V
    # a propósito, van uno al lado del otro, no se pisan porque su H no se
    # superpone). Para poder confirmar por log, sin depender solo de mirar
    # la impresión física, que las cuentas de este layout tan ajustado
    # cierran bien.
    def _se_superponen(a, b):
        _, av, ah, aalto, aancho = a
        _, bv, bh, balto, bancho = b
        return av < bv + balto and bv < av + aalto and ah < bh + bancho and bh < ah + aancho

    logger.info("=== Diagnóstico de posiciones SBPL '%s' -- %dmm x %dmm = %dpt alto x %dpt ancho (dpi=%d) ===", titulo, ancho_mm, alto_mm, alto_pt, ancho_pt, dpi)
    for idx, item in enumerate(diagnostico):
        nombre, v_elem, h_elem, alto_elem, ancho_elem = item
        borde_inferior = v_elem + alto_elem
        borde_derecho = h_elem + ancho_elem
        avisos = []
        if borde_inferior > alto_pt:
            avisos.append("SE PASA DEL ALTO TOTAL")
        if borde_derecho > ancho_pt:
            avisos.append("SE PASA DEL ANCHO TOTAL")
        choques = [otro[0] for j, otro in enumerate(diagnostico) if j != idx and _se_superponen(item, otro)]
        if choques:
            avisos.append(f"CHOCA CON {choques}")
        logger.info(
            "  %-24s V=%4d H=%4d alto=%4d ancho=%4d V+alto=%4d H+ancho=%4d%s",
            nombre, v_elem, h_elem, alto_elem, ancho_elem, borde_inferior, borde_derecho,
            f"  <-- {', '.join(avisos)}" if avisos else "",
        )

    logger.info(
        "=== SBPL etiqueta '%s' -- %dmm x %dmm (dpi=%d), logo %dx%dpx ===",
        titulo, ancho_mm, alto_mm, dpi, _LOGO_ANCHO_PX, _LOGO_ALTO_PX,
    )

    return STX + b"".join(comandos) + ETX


_TIMEOUT_RED_DIRECTA_SEGUNDOS = 10


def _imprimir_sbpl_compartida(ruta_red: str, sbpl_bytes: bytes, nombre_trabajo: str) -> None:
    """Envía sbpl_bytes como trabajo de impresión RAW a una impresora
    compartida en red (Windows, vía win32print) desde la PC donde está
    conectada por USB -- mecanismo original de este módulo, sin cambios.
    Nunca deja pasar una excepción cruda de pywin32 -- la loguea completa
    (exc_info=True) y la relanza como RuntimeError con un mensaje claro para
    mostrar al usuario, sin romper el resto de la pantalla (impresora
    apagada, ruta de red no accesible, etc.)."""
    if win32print is None:
        raise RuntimeError("pywin32 no está disponible en este entorno -- no se puede imprimir directo")

    # Bytes exactos que se mandan a WritePrinter, en hex -- para poder
    # revisar el payload byte por byte contra la sintaxis del manual si la
    # impresora sigue sin reaccionar (Windows puede confirmar el envío del
    # trabajo aunque el contenido esté mal formado, así que esto es lo único
    # que realmente permite verificar qué se mandó).
    logger.info("SBPL a enviar (compartida) a '%s' (%d bytes): %s", ruta_red, len(sbpl_bytes), sbpl_bytes.hex())

    try:
        h_printer = win32print.OpenPrinter(ruta_red)
    except Exception:
        logger.error("No se pudo abrir la impresora '%s'", ruta_red, exc_info=True)
        raise RuntimeError(
            f"No se pudo conectar con la impresora ({ruta_red}) -- verificá que esté encendida y accesible en la red"
        )

    try:
        try:
            h_job = win32print.StartDocPrinter(h_printer, 1, (nombre_trabajo, None, "RAW"))
            try:
                win32print.StartPagePrinter(h_printer)
                win32print.WritePrinter(h_printer, sbpl_bytes)
                win32print.EndPagePrinter(h_printer)
            finally:
                win32print.EndDocPrinter(h_printer)
        except Exception:
            logger.error("Error enviando el trabajo de impresión a '%s'", ruta_red, exc_info=True)
            raise RuntimeError(f"No se pudo enviar la etiqueta a la impresora ({ruta_red})")
    finally:
        win32print.ClosePrinter(h_printer)


def _imprimir_sbpl_red_directa(ip: str, puerto: int, sbpl_bytes: bytes, nombre_trabajo: str) -> None:
    """Envía sbpl_bytes directo por socket TCP a una impresora SATO con IP
    propia en la LAN (puerto RAW estándar 9100) -- sin pasar por win32print
    ni por ningún driver/cola de Windows, alternativa a la impresora
    compartida por USB. Mismo criterio de logging/manejo de errores que
    _imprimir_sbpl_compartida: nunca deja pasar la excepción cruda, la
    loguea completa (exc_info=True) y la relanza como RuntimeError con un
    mensaje claro (impresora apagada, IP inalcanzable, timeout, etc.)."""
    logger.info(
        "SBPL a enviar (red directa) a '%s:%d' -- trabajo '%s' (%d bytes): %s",
        ip, puerto, nombre_trabajo, len(sbpl_bytes), sbpl_bytes.hex(),
    )
    try:
        with socket.create_connection((ip, puerto), timeout=_TIMEOUT_RED_DIRECTA_SEGUNDOS) as sock:
            sock.sendall(sbpl_bytes)
    except Exception:
        logger.error("Error enviando el trabajo de impresión a '%s:%d' (red directa)", ip, puerto, exc_info=True)
        raise RuntimeError(
            f"No se pudo conectar con la impresora ({ip}:{puerto}) -- verificá que esté encendida y accesible en la red"
        )


def imprimir_sbpl(impresora, sbpl_bytes: bytes, nombre_trabajo: str = "Etiqueta LIMSS") -> None:
    """Punto único de envío -- ramifica según impresora.tipo_conexion (fila
    de lims_impresoras_etiquetas, se le pasa el objeto completo en vez de
    solo la ruta porque cada camino necesita datos distintos: ruta_red para
    'compartida', ip_directa/puerto_directo para 'red_directa'). Default
    'compartida' con getattr -- mismo criterio que el resto del proyecto
    para columnas nuevas que puede que no estén en todos los entornos
    todavía (ver _g/tiene_ensayos_analisis en otros módulos)."""
    tipo_conexion = getattr(impresora, "tipo_conexion", None) or "compartida"
    if tipo_conexion == "red_directa":
        _imprimir_sbpl_red_directa(impresora.ip_directa, impresora.puerto_directo, sbpl_bytes, nombre_trabajo)
    else:
        _imprimir_sbpl_compartida(impresora.ruta_red, sbpl_bytes, nombre_trabajo)
