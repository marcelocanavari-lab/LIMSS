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

# El ERP cambió el formato de GIN01CPB.NUMCOMO a partir de los comprobantes
# de 2026, manteniendo el mismo ancho total de 12 caracteres: antes eran 12
# dígitos zero-padded sin información de año ("000000000255"); desde 2026
# el campo arranca con el año completo (4 dígitos) seguido del correlativo
# zero-padded a 8 dígitos ("202600000255") -- verificado contra un
# comprobante real en GI_LX (IR 255/26 -> NUMCOMO='202600000255'), la regla
# original que se había propuesto (correlativo a 9 dígitos) no coincidía con
# el dato real y quedó descartada.
_ANIO_CAMBIO_FORMATO_NUMCOMO = 2026


def construir_numcomo(numero: str, anio: int) -> str:
    """Arma el NUMCOMO a buscar en GIN01CPB a partir del correlativo (NNN de
    'NNN/AA') y el año completo -- el formato depende del año, ver arriba."""
    if anio >= _ANIO_CAMBIO_FORMATO_NUMCOMO:
        return f"{anio}{numero.zfill(8)}"
    return numero.zfill(12)


def _extraer_numero_de_numcomo(numcomo: str, anio: int) -> int:
    """Inversa de construir_numcomo: recupera el correlativo NNN a partir del
    NUMCOMO crudo que devuelve el ERP, conociendo el año del comprobante
    (GIN01CPB.FECCOM)."""
    numcomo = numcomo.strip()
    if anio >= _ANIO_CAMBIO_FORMATO_NUMCOMO:
        return int(numcomo[len(str(anio)):])
    return int(numcomo)


def _parsear_nro_ir(nro_ir: str) -> tuple[str, int]:
    m = _PATRON_IR.match(nro_ir)
    if not m:
        raise HTTPException(
            status_code=400,
            detail="El número de IR debe tener el formato 'NNN/AA' (ej. 262/20)",
        )
    numero, anio_corto = m.groups()
    anio = 2000 + int(anio_corto)
    return construir_numcomo(numero, anio), anio


def _tipo_comprobante_ir(erp: pyodbc.Connection) -> int:
    cursor = erp.cursor()
    cursor.execute("SELECT T05Id FROM GIT05TCM WHERE CODTCM = 'IR'")
    fila = cursor.fetchone()
    if not fila:
        raise HTTPException(status_code=502, detail="El ERP no tiene configurado el tipo de comprobante 'IR'")
    return fila.T05Id


def formatear_nro_ir(numcomo: str, feccom) -> str:
    """Reconstruye el formato 'NNN/AA' que reconoce el operario a partir de
    los campos crudos del ERP -- el año de FECCOM determina cómo leer
    NUMCOMO (ver _ANIO_CAMBIO_FORMATO_NUMCOMO)."""
    anio = feccom.year
    numero = _extraer_numero_de_numcomo(numcomo, anio)
    return f"{numero}/{anio % 100:02d}"


def normalizar_fecha_sentinel(valor):
    """1899-12-30 es el sentinel del ERP para "sin fecha cargada" (igual en
    el eBR) -- se normaliza a None. Sirve tanto para VENCOM como para
    cualquier otra fecha del ERP con el mismo sentinel."""
    if not valor:
        return None
    fecha = valor.date() if hasattr(valor, "date") else valor
    return fecha if fecha.year > 1900 else None


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
               ana.CODANA AS proveedor_codigo, ana.DESANA AS proveedor,
               sar.CODSAR, sar.DESSAR,
               (SELECT SUM(its2.CANTID) FROM GIN02ITS its2 WHERE its2.IdN01O = cab.N01Id) AS cantidad_total
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
    return normalizar_fecha_sentinel(row.VENCOM) if row else None
