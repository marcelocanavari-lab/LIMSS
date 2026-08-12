"""
Búsqueda de materiales del ERP filtrados por tipo (GIT59SAR.CODSAR), para el
flujo de creación de especificaciones: primero se elige el tipo de material,
después se busca solo entre los artículos de ese tipo.

Mapeo CODSAR confirmado por el usuario (Lamar):
    '0000' -> Producto Terminado
    '0001' -> Materia Prima (tiene IR en el ERP)
    '0002' -> Granel
    '0003' -> Semi-Elaborado
"""
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


def listar_subarticulos_erp(erp: pyodbc.Connection):
    """Catálogo completo de subartículos del ERP (GIT59SAR) -- tabla maestra
    chica (tipos de material: materia prima, granel, semi-elaborado, etc.),
    no confundir con GIM21ART (los artículos individuales -- miles de filas,
    un material puntual del ERP). Es el universo real de erp_codsar que se
    puede configurar en lims_erp_subarticulo_config (ver pantalla de
    administración de Subartículos y Muestreo)."""
    cursor = erp.cursor()
    cursor.execute("SELECT T59Id, CODSAR, DESSAR FROM GIT59SAR ORDER BY CODSAR")
    return cursor.fetchall()


def buscar_materiales(erp: pyodbc.Connection, codsar: str, buscar: str = ""):
    like = f"%{buscar}%"
    cursor = erp.cursor()
    cursor.execute(
        """
        SELECT art.M21Id AS IdM21, art.CODART, art.DESART
        FROM GIM21ART art
        INNER JOIN GIT59SAR sar ON sar.T59Id = art.IdT59
        WHERE sar.CODSAR = ?
          AND (art.CODART LIKE ? OR art.DESART LIKE ?)
        ORDER BY art.DESART
        """,
        codsar, like, like,
    )
    return cursor.fetchall()
