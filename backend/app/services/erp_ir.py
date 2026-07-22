"""
Búsqueda de Informes de Recepción (IR) en el ERP GI_LX.

El "IR" que conoce el operario es un número compuesto "NNN/AA" (ej. "262/20"):
NNN es el correlativo que se completa con ceros hasta el ancho del campo
GIN01CPB.NUMCOMO, y AA son los últimos 2 dígitos del año de GIN01CPB.FECCOM.
El comprobante se identifica combinando:
  - IdT05O = GIT05TCM.T05Id donde GIT05TCM.CODTCM = 'IR'
  - LETCOMO = 'X'
  - NUMCOMO = NNN (zero-padded)
  - YEAR(FECCOM) = 2000 + AA
(regla confirmada por el usuario -- no está documentada en ningún lado del ERP).

El 2020-04-02 fue la fecha de puesta en marcha del ERP: ese día se cargaron
~430 comprobantes IR de arrastre con numeración repetida (varios NUMCOMO
comparten número dentro del mismo año). Fuera de esa fecha la combinación
(NUMCOMO, año) es única. Ante una colisión nos quedamos con el comprobante
más reciente por FECCOM -- el de arrastre casi nunca es el que el operario
está buscando.

El proveedor se resuelve vía GIN01CPB.IdM02O -> GIM02ANA.M02Id, filtrando
GIM02ANA.IdT04 = 2 (tipo "proveedor") -- confirmado por el usuario, aunque
hoy no se esté cargando en la práctica (puede venir NULL).
"""
import re

import pyodbc
from fastapi import HTTPException

_PATRON_IR = re.compile(r"^\s*(\d{1,12})\s*/\s*(\d{2})\s*$")

_FECHA_MIGRACION = "2020-04-02"


def _parsear_nro_ir(nro_ir: str) -> tuple[str, int]:
    m = _PATRON_IR.match(nro_ir)
    if not m:
        raise HTTPException(
            status_code=400,
            detail="El número de IR debe tener el formato 'NNN/AA' (ej. 262/20)",
        )
    numero, anio_corto = m.groups()
    return numero.zfill(12), 2000 + int(anio_corto)


def _tipo_comprobante_ir(erp: pyodbc.Connection) -> int:
    cursor = erp.cursor()
    cursor.execute("SELECT T05Id FROM GIT05TCM WHERE CODTCM = 'IR'")
    fila = cursor.fetchone()
    if not fila:
        raise HTTPException(status_code=502, detail="El ERP no tiene configurado el tipo de comprobante 'IR'")
    return fila.T05Id


def formatear_nro_ir(numcomo: str, feccom) -> str:
    """Reconstruye el formato 'NNN/AA' que reconoce el operario a partir de
    los campos crudos del ERP."""
    return f"{int(numcomo)}/{feccom.year % 100:02d}"


def buscar_lineas_ir(erp: pyodbc.Connection, nro_ir: str):
    numcomo, anio = _parsear_nro_ir(nro_ir)
    id_tipo_ir = _tipo_comprobante_ir(erp)

    cursor = erp.cursor()
    cursor.execute(
        """
        SELECT TOP 1 N01Id
        FROM GIN01CPB
        WHERE IdT05O = ? AND LETCOMO = 'X' AND NUMCOMO = ? AND YEAR(FECCOM) = ?
        ORDER BY FECCOM DESC
        """,
        id_tipo_ir, numcomo, anio,
    )
    cabecera = cursor.fetchone()
    if not cabecera:
        return []

    cursor.execute(
        """
        SELECT cab.N01Id, cab.NUMCOMO, cab.FECCOM, cab.VENCOM,
               its.IdM21, its.CANTID,
               art.CODART, art.DESART, umd.ABREV AS unidad,
               ana.DESANA AS proveedor,
               sar.CODSAR, sar.DESSAR
        FROM GIN01CPB cab
        INNER JOIN GIN02ITS its ON its.IdN01O = cab.N01Id
        INNER JOIN GIM21ART art ON art.M21Id = its.IdM21
        LEFT JOIN GIT21UMD umd ON umd.T21Id = art.IdT21M
        LEFT JOIN GIM02ANA ana ON ana.M02Id = cab.IdM02O AND ana.IdT04 = 2
        LEFT JOIN GIT59SAR sar ON sar.T59Id = art.IdT59
        WHERE cab.N01Id = ?
        """,
        cabecera.N01Id,
    )
    return cursor.fetchall()


def obtener_vencimiento_lote(erp: pyodbc.Connection, nro_ir: str):
    """VENCOM del comprobante IR. 1899-12-30 es el sentinel del ERP para
    "sin vencimiento" (igual que en el eBR) -- se normaliza a None."""
    numcomo, anio = _parsear_nro_ir(nro_ir)
    id_tipo_ir = _tipo_comprobante_ir(erp)

    cursor = erp.cursor()
    cursor.execute(
        """
        SELECT TOP 1 VENCOM
        FROM GIN01CPB
        WHERE IdT05O = ? AND LETCOMO = 'X' AND NUMCOMO = ? AND YEAR(FECCOM) = ?
        ORDER BY FECCOM DESC
        """,
        id_tipo_ir, numcomo, anio,
    )
    row = cursor.fetchone()
    if not row or not row.VENCOM:
        return None
    vencom = row.VENCOM.date() if hasattr(row.VENCOM, "date") else row.VENCOM
    return vencom if vencom.year > 1900 else None
