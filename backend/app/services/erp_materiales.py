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

CODSAR_POR_TIPO = {
    "materia_prima": "0001",
    "granel": "0002",
    "semi_elaborado": "0003",
    "producto_terminado": "0000",
}


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
