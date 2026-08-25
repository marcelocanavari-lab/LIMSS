"""
Búsqueda de materiales del ERP filtrados por tipo (GIT59SAR.CODSAR), para el
flujo de creación de especificaciones: primero se elige el tipo de material,
después se busca solo entre los artículos de ese tipo.

Mapeo CODSAR confirmado por el usuario (Lamar):
    '0000' -> Producto Terminado
    '0001' -> Materia Prima (tiene IR en el ERP)
    '0002' -> Granel
    '0003' -> Semi-Elaborado
    '0005' / '0006' -> Material de Empaque (codificado / sin codificar --
        ver CODSAR_MATERIAL_EMPAQUE más abajo: a diferencia del resto, es UN
        tipo_material que cubre DOS subartículos del ERP)
"""
from typing import Optional

import pyodbc

# Fallback histórico -- se usa si lims_erp_config no existe todavía (no se
# corrió la migración) o si falla la consulta por cualquier motivo. Nunca debe
# romper el flujo de creación de muestras/especificaciones por esto.
CODSAR_POR_TIPO = {
    "materia_prima": "0001",
    "granel": "0002",
    "semi_elaborado": "0003",
    "producto_terminado": "0000",
}

# Material de Empaque es el único tipo_material respaldado por dos
# subartículos del ERP a la vez (codificado y sin codificar) -- por eso vive
# aparte de CODSAR_POR_TIPO (un único código cada uno) en vez de forzar ahí
# un valor de lista que rompería a los demás consumidores de ese mapeo.
CODSAR_MATERIAL_EMPAQUE = ["0005", "0006"]


def obtener_codsar_por_tipo(conn: pyodbc.Connection) -> dict:
    """Mapeo tipo_material -> CODSAR, editable desde Datos Maestros >
    Configuración ERP (tabla lims_erp_config, claves 'codsar_<tipo>').
    Si la consulta falla, devuelve el mapeo hardcodeado de CODSAR_POR_TIPO."""
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT clave, valor FROM lims_erp_config WHERE clave LIKE 'codsar_%'")
        filas = cursor.fetchall()
    except Exception:
        return dict(CODSAR_POR_TIPO)

    mapeo = dict(CODSAR_POR_TIPO)
    for fila in filas:
        tipo = fila.clave[len("codsar_"):]
        mapeo[tipo] = fila.valor
    return mapeo


def obtener_codsars_material_empaque(conn: pyodbc.Connection) -> list[str]:
    """CODSAR de Material de Empaque -- a diferencia del resto de los tipos
    (un único CODSAR cada uno, ver obtener_codsar_por_tipo), cubre dos
    subartículos del ERP (0005 codificado, 0006 sin codificar) que en LIMSS
    se tratan como un solo tipo_material: la distinción codificado/sin
    codificar solo importa para decidir si el lote del proveedor y la fecha
    de vencimiento son obligatorios al crear la Solicitud de Muestreo (ver
    crear_solicitud en solicitudes_muestreo.py), no para separar en dos
    tipos de especificación. Editable desde Configuración ERP igual que el
    resto (clave 'codsar_material_empaque', valor separado por comas)."""
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT valor FROM lims_erp_config WHERE clave = 'codsar_material_empaque'")
        fila = cursor.fetchone()
    except Exception:
        return list(CODSAR_MATERIAL_EMPAQUE)
    if not fila or not fila.valor:
        return list(CODSAR_MATERIAL_EMPAQUE)
    return [c.strip() for c in fila.valor.split(",") if c.strip()]


def listar_subarticulos_erp(erp: pyodbc.Connection):
    """Catálogo completo de subartículos del ERP (GIT59SAR) -- tabla maestra
    chica (tipos de material: materia prima, granel, semi-elaborado, etc.),
    no confundir con GIM21ART (los artículos individuales -- miles de filas,
    un material puntual del ERP). Es el universo real de erp_codsar que se
    puede configurar en lims_erp_subarticulo_config (ver pantalla de
    administración de Subartículos y Muestreo)."""
    cursor = erp.cursor()
    # RTRIM: GIT59SAR.CODSAR/DESSAR son CHAR de ancho fijo, vienen rellenados
    # con espacios -- se recorta acá (único punto de lectura) en vez de que
    # cada consumidor tenga que hacer su propio .strip().
    cursor.execute("SELECT T59Id, RTRIM(CODSAR) AS CODSAR, RTRIM(DESSAR) AS DESSAR FROM GIT59SAR ORDER BY CODSAR")
    return cursor.fetchall()


def buscar_materiales(erp: pyodbc.Connection, codsares: list[str], buscar: str = ""):
    """codsares es siempre una lista -- un único CODSAR para la mayoría de
    los tipos, dos para Material de Empaque (ver obtener_codsars_material_
    empaque). Se filtra con IN en vez de tener dos variantes de esta función."""
    like = f"%{buscar}%"
    placeholders = ",".join("?" * len(codsares))
    cursor = erp.cursor()
    # RTRIM en CODART/DESART: GIM21ART es CHAR de ancho fijo, ver la nota en
    # erp_ir.py -- se recorta al leer para que erp_CODART nunca llegue con
    # espacios de más a lims_especificaciones (y de ahí a cualquier pantalla
    # que arme una URL o compare por ese código).
    cursor.execute(
        f"""
        SELECT art.M21Id AS IdM21, RTRIM(art.CODART) AS CODART, RTRIM(art.DESART) AS DESART
        FROM GIM21ART art
        INNER JOIN GIT59SAR sar ON sar.T59Id = art.IdT59
        WHERE sar.CODSAR IN ({placeholders})
          AND (art.CODART LIKE ? OR art.DESART LIKE ?)
        ORDER BY art.DESART
        """,
        *codsares, like, like,
    )
    return cursor.fetchall()


# ── numero_analisis (Libro de Ingresos) ─────────────────────────────────
#
# Correlativo exclusivo de Materia Prima y Material de Empaque (ver Libro de
# Ingresos, app/api/routes/reportes.py). Se determina por el erp_codsar YA
# RESUELTO contra el ERP de la especificación de la muestra
# (lims_especificaciones.erp_codsar, congelado al crear/versionar la
# especificación -- ver resolver_codsar_por_codart en maestros.py), NO por
# lims_muestras.tipo_material: ese es texto libre, editable después de
# creada la muestra sin volver a pasar por el ERP (ver editar_muestra en
# muestras.py), y no una fuente confiable para decidir si corresponde
# numerar.

def tiene_numero_analisis(cursor) -> bool:
    """lims_muestras.numero_analisis y lims_contador_numero_analisis pueden
    no existir todavía en un entorno que no corrió la migración -- se
    consultan las dos porque numero_analisis sin el contador (o viceversa)
    dejaría la asignación a medio hacer."""
    cursor.execute("SELECT COL_LENGTH('lims_muestras', 'numero_analisis') AS c")
    if cursor.fetchone().c is None:
        return False
    cursor.execute("SELECT OBJECT_ID('lims_contador_numero_analisis') AS oid")
    return cursor.fetchone().oid is not None


def asignar_numero_analisis_si_corresponde(conn: pyodbc.Connection, id_especificacion: Optional[int]) -> Optional[int]:
    """Si la muestra corresponde a Materia Prima o Material de Empaque
    (según el erp_codsar de su especificación, ver nota del módulo más
    arriba), asigna el siguiente numero_analisis de forma segura ante
    concurrencia (ROWLOCK/XLOCK explícito sobre la única fila de
    lims_contador_numero_analisis antes de leerla, para que dos creaciones
    simultáneas nunca reciban el mismo número) y lo devuelve. Si no
    corresponde -- otro tipo de material, sin especificación vinculada, con
    erp_codsar sin resolver (especificaciones viejas, de antes de que
    existiera esa columna, o creadas sin conexión al ERP), o si el entorno
    todavía no corrió la migración -- devuelve None sin bloquear la
    creación de la muestra: no se puede clasificar con certeza, la muestra
    queda sin número en vez de adivinar."""
    cursor = conn.cursor()
    if not tiene_numero_analisis(cursor):
        return None
    if id_especificacion is None:
        return None

    cursor.execute("SELECT erp_codsar FROM lims_especificaciones WHERE id_especificacion = ?", id_especificacion)
    espec = cursor.fetchone()
    codsar = espec.erp_codsar.strip() if espec and espec.erp_codsar else None
    if not codsar:
        return None

    codsar_materia_prima = obtener_codsar_por_tipo(conn).get("materia_prima")
    codsars_empaque = obtener_codsars_material_empaque(conn)
    if codsar != codsar_materia_prima and codsar not in codsars_empaque:
        return None

    cursor.execute(
        "UPDATE lims_contador_numero_analisis WITH (ROWLOCK, XLOCK) SET ultimo_valor = ultimo_valor + 1 WHERE id = 1"
    )
    cursor.execute("SELECT ultimo_valor FROM lims_contador_numero_analisis WHERE id = 1")
    return cursor.fetchone().ultimo_valor
