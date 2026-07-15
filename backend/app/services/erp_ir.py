"""
Búsqueda de Informes de Recepción (IR) en el ERP GI_LX.

El "IR" que conoce el operario es el número de comprobante de ingreso
(GIN01CPB.NUMCOMO). Un mismo IR puede tener varias líneas (materiales), en
GIN02ITS. El proveedor se resuelve vía GIN01CPB.IdM02O -> GIM02ANA.M02Id,
filtrando GIM02ANA.IdT04 = 2 (tipo "proveedor") -- confirmado por el usuario,
aunque hoy no se esté cargando en la práctica (puede venir NULL).
"""
import pyodbc


def buscar_lineas_ir(erp: pyodbc.Connection, nro_ir: str):
    cursor = erp.cursor()
    cursor.execute(
        """
        SELECT cab.N01Id, cab.NUMCOMO, cab.FECCOM, cab.VENCOM,
               its.IdM21, its.CANTID,
               art.CODART, art.DESART, umd.ABREV AS unidad,
               ana.DESANA AS proveedor
        FROM GIN01CPB cab
        INNER JOIN GIN02ITS its ON its.IdN01O = cab.N01Id
        INNER JOIN GIM21ART art ON art.M21Id = its.IdM21
        LEFT JOIN GIT21UMD umd ON umd.T21Id = art.IdT21M
        LEFT JOIN GIM02ANA ana ON ana.M02Id = cab.IdM02O AND ana.IdT04 = 2
        WHERE RTRIM(LTRIM(cab.NUMCOMO)) = RTRIM(LTRIM(?))
        """,
        nro_ir,
    )
    return cursor.fetchall()
