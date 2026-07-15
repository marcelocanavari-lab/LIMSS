"""
Búsqueda de lotes de producción interna (Granel, Semi-Elaborado, Producto
Terminado) en la base del eBR. Estos materiales no pasan por el circuito de
recepción del ERP (GIN01CPB) -- se producen internamente y el eBR les asigna
su propio número de lote (ebr_lotes), sin proveedor asociado.
"""
import pyodbc


def buscar_lote(ebr: pyodbc.Connection, nro_lote: str):
    cursor = ebr.cursor()
    cursor.execute(
        """
        SELECT id_lote, nro_lote, erp_IdM21, erp_CODART, erp_DESART, erp_unidad,
               tamanio_lote, fecha_elaboracion, fecha_vencimiento, estado
        FROM ebr_lotes
        WHERE RTRIM(LTRIM(nro_lote)) = RTRIM(LTRIM(?))
        """,
        nro_lote,
    )
    return cursor.fetchone()
