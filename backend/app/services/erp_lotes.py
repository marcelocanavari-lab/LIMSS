"""
Búsqueda de número de lote interno en el ERP GI_LX para Granel,
Semi-Elaborado y Producto Terminado (Materia Prima usa IR -- ver erp_ir.py).

El lote se guarda como atributo variable del artículo, no en una tabla de
lotes dedicada: GIM25ALT (atributos del artículo) relaciona el artículo
(IdM21 -> GIM21ART.M21Id) con un código de la tabla genérica GIT52DSC vía
IdT521 -> GIT52DSC.T52Id; GIT52DSC.IdT51 = 2 (GIT51SCD: CODSCD='02',
DESSCD='LOTE') marca las filas que son números de lote -- confirmado por el
usuario, no está documentado en ningún lado del ERP.

Un mismo número de lote suele estar asignado a varios artículos a la vez --
ej. un lote de Granel que se fracciona en varias presentaciones de Producto
Terminado -- por eso la búsqueda se filtra también por CODSAR (tipo de
material ya elegido en el paso 1) para acotar a los artículos relevantes;
si ese lote+tipo tiene más de una presentación, el frontend deja elegir
entre los resultados, igual que con el IR.
"""
import pyodbc


def buscar_lote(erp: pyodbc.Connection, codsar: str, nro_lote: str):
    cursor = erp.cursor()
    # RTRIM en CODART/DESART: GIM21ART es CHAR de ancho fijo, ver la nota en
    # erp_ir.py -- se recorta al leer, único punto de esta consulta.
    cursor.execute(
        """
        SELECT art.M21Id AS IdM21, RTRIM(art.CODART) AS CODART, RTRIM(art.DESART) AS DESART, umd.ABREV AS unidad
        FROM GIT52DSC dsc
        INNER JOIN GIM25ALT alt ON alt.IdT521 = dsc.T52Id
        INNER JOIN GIM21ART art ON art.M21Id = alt.IdM21
        INNER JOIN GIT59SAR sar ON sar.T59Id = art.IdT59
        LEFT JOIN GIT21UMD umd ON umd.T21Id = art.IdT21M
        WHERE dsc.IdT51 = 2 AND RTRIM(dsc.CODDSC) = ? AND sar.CODSAR = ?
        """,
        nro_lote, codsar,
    )
    return cursor.fetchall()


def obtener_vencimiento_lote_produccion(erp: pyodbc.Connection, nro_lote: str):
    """Vencimiento del comprobante de tipo LOTE (GIT05TCM.T05Id = 49, fijo --
    confirmado por el usuario, no está documentado en ningún lado del ERP) que
    corresponde al lote de producción interno de Granel/Semi-Elaborado/
    Producto Terminado (a diferencia de Materia Prima, que usa IR -- ver
    erp_ir.obtener_vencimiento_lote). NUMCOMO es el número de lote tal cual lo
    ingresa el usuario, rellenado con ceros a la izquierda hasta 12
    caracteres. 1899-12-30 es el sentinel del ERP para "sin vencimiento"
    (igual que en el eBR) -- se normaliza a None."""
    cursor = erp.cursor()
    cursor.execute(
        """
        SELECT TOP 1 VENCOM
        FROM GIN01CPB
        WHERE IdT05O = 49
          AND NUMCOMO = RIGHT('000000000000' + CAST(? AS VARCHAR), 12)
        ORDER BY FECCOM DESC
        """,
        nro_lote,
    )
    row = cursor.fetchone()
    if not row or not row.VENCOM:
        return None
    vencom = row.VENCOM.date() if hasattr(row.VENCOM, "date") else row.VENCOM
    return vencom if vencom.year > 1900 else None
