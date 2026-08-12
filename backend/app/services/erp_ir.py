"""
Búsqueda de Informes de Recepción (IR) en el ERP GI_LX.

El "IR" que conoce el operario es un número compuesto "NNN/AA" (ej. "212/26"):
NNN es el correlativo y AA son los últimos 2 dígitos del año. El comprobante
se identifica combinando:
  - IdT05O = GIT05TCM.T05Id donde GIT05TCM.CODTCM = 'IR'
  - LETCOMO = 'X'
  - NUMCOMO = NNN zero-padded a 12 caracteres (ej. '000000000212')
  - YEAR(FECCOR) = 2000 + AA

Importante: el año se filtra por FECCOR, NO por FECCOM -- son dos columnas
datetime distintas en GIN01CPB (no un alias). En la mayoría de los
comprobantes coinciden, pero difieren en los de arrastre de la carga inicial
(algunos conservan en FECCOR la fecha real del comprobante original --
2013/2015/2018/2019 -- mientras FECCOM quedó forzado a la fecha de carga) y
ocasionalmente en comprobantes consecutivos cerca de un cambio de mes/año.
Se verificó directamente contra GI_LX (2026-08) que NUMCOMO sigue siendo
zero-pad de 12 dígitos sin prefijo de año -- una versión anterior de esta
lógica asumía que el ERP había empezado a prefijar el año en NUMCOMO a
partir de 2026 (ej. NUMCOMO='202600000212'), pero esa regla no coincide con
ningún comprobante real y quedó descartada; el bug real que hacía fallar la
búsqueda de IRs de 2026 era ese formato de NUMCOMO inventado, no un cambio
real en el ERP.

El 2020-04-02 fue la fecha de puesta en marcha del ERP: ese día se cargaron
~430 comprobantes IR de arrastre con numeración repetida (varios NUMCOMO
comparten número dentro del mismo año). Fuera de esa fecha la combinación
(NUMCOMO, año) es única. Ante una colisión nos quedamos con el comprobante
más reciente por FECCOR -- el de arrastre casi nunca es el que el operario
está buscando.

El proveedor se resuelve vía GIN01CPB.IdM02O -> GIM02ANA.M02Id, filtrando
GIM02ANA.IdT04 = 2 (tipo "proveedor") -- confirmado por el usuario, aunque
hoy no se esté cargando en la práctica (puede venir NULL).
"""
import re
from typing import Optional

import pyodbc
from fastapi import HTTPException

_PATRON_IR = re.compile(r"^\s*(\d{1,12})\s*/\s*(\d{2})\s*$")

_FECHA_MIGRACION = "2020-04-02"


def construir_numcomo(numero: str) -> str:
    """Arma el NUMCOMO a buscar en GIN01CPB a partir del correlativo (NNN de
    'NNN/AA'): zero-pad a 12 caracteres, sin prefijo de año."""
    return numero.zfill(12)


def _extraer_numero_de_numcomo(numcomo: str) -> int:
    """Inversa de construir_numcomo: recupera el correlativo NNN a partir del
    NUMCOMO crudo que devuelve el ERP."""
    return int(numcomo.strip())


def _parsear_nro_ir(nro_ir: str) -> tuple[str, int]:
    m = _PATRON_IR.match(nro_ir)
    if not m:
        raise HTTPException(
            status_code=400,
            detail="El número de IR debe tener el formato 'NNN/AA' (ej. 262/20)",
        )
    numero, anio_corto = m.groups()
    anio = 2000 + int(anio_corto)
    return construir_numcomo(numero), anio


def tipo_comprobante_ir(erp: pyodbc.Connection) -> int:
    """T05Id del tipo de comprobante 'IR' (GIT05TCM.CODTCM = 'IR')."""
    cursor = erp.cursor()
    cursor.execute("SELECT T05Id FROM GIT05TCM WHERE CODTCM = 'IR'")
    fila = cursor.fetchone()
    if not fila:
        raise HTTPException(status_code=502, detail="El ERP no tiene configurado el tipo de comprobante 'IR'")
    return fila.T05Id


# Alias histórico -- buscar_lineas_ir/obtener_vencimiento_lote seguían
# llamando a esta función por su nombre privado original.
_tipo_comprobante_ir = tipo_comprobante_ir


_QUERY_LINEAS_POR_N01ID = """
    SELECT cab.N01Id, cab.NUMCOMO, cab.FECCOM, cab.FECCOR, cab.VENCOM,
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
"""


def _lineas_por_n01id(erp: pyodbc.Connection, n01id: int):
    """Query de JOIN compartida entre buscar_lineas_ir (resuelve el N01Id a
    partir de "NNN/AA") y lineas_comprobante_por_id (ya tiene el N01Id) --
    un solo lugar para mantener si cambia el esquema del ERP."""
    cursor = erp.cursor()
    cursor.execute(_QUERY_LINEAS_POR_N01ID, n01id)
    return cursor.fetchall()


def comprobantes_ir_nuevos(erp: pyodbc.Connection, id_tipo_ir: int, ultimo_n01id: int, fecha_inicio) -> list[int]:
    """N01Id de comprobantes IR (LETCOMO='X') con N01Id > ultimo_n01id Y
    FECCOR >= fecha_inicio, ordenados ascendente -- usado por el agente de
    detección automática para saber qué comprobantes todavía tiene que
    evaluar (ver app/services/agente_muestreo.py). fecha_inicio filtra
    comprobantes históricos de antes de que el agente existiera (ver
    agente_muestreo_fecha_inicio en lims_erp_config) -- N01Id es un
    correlativo de carga, no de fecha del documento, así que un comprobante
    viejo puede tener un N01Id más alto que ultimo_n01id si se cargó tarde;
    por eso el filtro de fecha es necesario además del de N01Id, no en
    lugar de.

    Nota: esta lista NO es "todos los N01Id > ultimo_n01id" -- los
    descartados por fecha quedan afuera acá a propósito (no se evalúan, ver
    ciclo_polling). Para el avance de la marca de agua se usa por separado
    max_n01id_nuevo, que sí ve el rango completo sin el filtro de fecha."""
    cursor = erp.cursor()
    cursor.execute(
        "SELECT N01Id FROM GIN01CPB WHERE IdT05O = ? AND LETCOMO = 'X' AND N01Id > ? AND FECCOR >= ? ORDER BY N01Id ASC",
        id_tipo_ir, ultimo_n01id, fecha_inicio,
    )
    return [fila.N01Id for fila in cursor.fetchall()]


def max_n01id_nuevo(erp: pyodbc.Connection, id_tipo_ir: int, ultimo_n01id: int) -> Optional[int]:
    """Máximo N01Id entre TODOS los comprobantes IR con N01Id > ultimo_n01id,
    sin filtrar por fecha -- se usa solo para avanzar la marca de agua
    (agente_muestreo_ultimo_n01id) más allá de los comprobantes descartados
    por comprobantes_ir_nuevos por ser anteriores a agente_muestreo_fecha_inicio,
    para no tener que volver a escanear ese rango en cada ciclo futuro. Esos
    comprobantes igual quedan sin evaluar -- no generan fila en
    lims_agente_control ni cuentan como error (ver ciclo_polling)."""
    cursor = erp.cursor()
    cursor.execute(
        "SELECT MAX(N01Id) AS max_n01id FROM GIN01CPB WHERE IdT05O = ? AND LETCOMO = 'X' AND N01Id > ?",
        id_tipo_ir, ultimo_n01id,
    )
    fila = cursor.fetchone()
    return fila.max_n01id if fila and fila.max_n01id is not None else None


def lineas_comprobante_por_id(erp: pyodbc.Connection, n01id: int):
    """Igual que buscar_lineas_ir pero recibiendo el N01Id directo (ya
    resuelto, ej. por comprobantes_ir_nuevos) en vez del string "NNN/AA" --
    no hace falta resolver NUMCOMO/FECCOR porque el comprobante ya está
    identificado. Cada IR trae un solo ítem (confirmado), así que en la
    práctica devuelve como máximo una fila -- se mantiene la forma de
    lista/cursor igual que buscar_lineas_ir por si en el futuro deja de
    ser siempre 1 a 1."""
    return _lineas_por_n01id(erp, n01id)


def formatear_nro_ir(numcomo: str, feccor) -> str:
    """Reconstruye el formato 'NNN/AA' que reconoce el operario a partir de
    los campos crudos del ERP. Recibe FECCOR (no FECCOM) para que el año
    mostrado sea el mismo que se usó para encontrar el comprobante."""
    anio = feccor.year
    numero = _extraer_numero_de_numcomo(numcomo)
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
        WHERE IdT05O = ? AND LETCOMO = 'X' AND NUMCOMO = ? AND YEAR(FECCOR) = ?
        ORDER BY FECCOR DESC
        """,
        id_tipo_ir, numcomo, anio,
    )
    cabecera = cursor.fetchone()
    if not cabecera:
        return []

    return _lineas_por_n01id(erp, cabecera.N01Id)


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
        WHERE IdT05O = ? AND LETCOMO = 'X' AND NUMCOMO = ? AND YEAR(FECCOR) = ?
        ORDER BY FECCOR DESC
        """,
        id_tipo_ir, numcomo, anio,
    )
    row = cursor.fetchone()
    return normalizar_fecha_sentinel(row.VENCOM) if row else None
