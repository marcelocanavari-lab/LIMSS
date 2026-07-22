"""
Composición declarada de un artículo (principios activos + concentración) a
partir de GIM21ART.OBSERV, para completar el remito de envío de muestras.

Formato de OBSERV (confirmado por el usuario -- no documentado en ningún
lado del ERP): "MPxxx - concentración" por cada principio activo, con
posibles múltiples componentes separados por "/", ej:
    "MP049 - 0.3 mg" o "MP049 - 0.3 mg / MP012 - 0.1 mg"
El nombre de cada principio activo se resuelve buscando MPxxx en
GIM21ART.CODART y trayendo GIM21ART.DESART.
"""
import re

import pyodbc

_PATRON_COMPONENTE = re.compile(r"^\s*(MP\d+)\s*-\s*(.+?)\s*$", re.IGNORECASE)


def obtener_principios_activos(erp: pyodbc.Connection, codart: str) -> list[dict]:
    cursor = erp.cursor()
    cursor.execute("SELECT OBSERV FROM GIM21ART WHERE RTRIM(CODART) = RTRIM(?)", codart)
    row = cursor.fetchone()
    if not row or not row.OBSERV or not row.OBSERV.strip():
        return []

    componentes = []
    for parte in row.OBSERV.split("/"):
        m = _PATRON_COMPONENTE.match(parte)
        if m:
            componentes.append((m.group(1).upper(), m.group(2).strip()))

    resultado = []
    for codigo, concentracion in componentes:
        cursor.execute("SELECT DESART FROM GIM21ART WHERE RTRIM(CODART) = ?", codigo)
        art = cursor.fetchone()
        nombre = art.DESART.strip() if art else codigo
        resultado.append({"codigo": codigo, "nombre": nombre, "concentracion": concentracion})
    return resultado
