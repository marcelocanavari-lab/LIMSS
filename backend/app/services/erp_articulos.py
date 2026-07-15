"""
Búsqueda de artículos del ERP (GI_LX) para asociar especificaciones LIMSS.

A diferencia de eBR, acá no filtramos por GIT59SAR.CODSAR: una especificación
LIMSS puede aplicar a materia prima, granel o producto terminado, y esa
clasificación la elige el usuario manualmente al crear la ficha (el mapeo
CODSAR -> tipo_material no está confirmado para materia prima en el ERP).
"""
import pyodbc


def buscar_articulos(erp: pyodbc.Connection, buscar: str = ""):
    like = f"%{buscar}%"
    cursor = erp.cursor()
    cursor.execute(
        """
        SELECT art.M21Id AS IdM21, art.CODART, art.DESART, umd.ABREV AS unidad
        FROM GIM21ART art
        LEFT JOIN GIT21UMD umd ON umd.T21Id = art.IdT21M
        WHERE art.CODART LIKE ? OR art.DESART LIKE ?
        ORDER BY art.DESART
        """,
        like, like,
    )
    return cursor.fetchall()
