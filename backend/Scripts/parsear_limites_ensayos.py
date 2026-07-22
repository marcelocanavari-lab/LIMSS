# -*- coding: utf-8 -*-
"""
parsear_limites_ensayos.py
==========================
Parsea el campo valor_requerido de lims_especificacion_ensayos
para completar limite_inferior, limite_superior, unidad_medida
y cambiar tipo_dato a 'numerico' cuando corresponda.

Uso:
    python parsear_limites_ensayos.py --dry-run   (solo muestra cambios)
    python parsear_limites_ensayos.py              (aplica cambios en BD)

Reglas de parseo:
    1. "≤ X unidad"      → limite_superior=X, unidad=unidad
    2. "≥ X unidad"      → limite_inferior=X, unidad=unidad
    3. "X – Y unidad"    → limite_inferior=X, limite_superior=Y, unidad=unidad
    4. Texto complejo    → dejar como cualitativo sin modificar
"""

import re
import sys
import argparse
import pyodbc
from decimal import Decimal, InvalidOperation

CONFIG = {
    "db_server":   "Lamarserver",
    "db_name":     "LIMSS",
    "db_user":     "limss_app",
    "db_password": "Limss2024#",   # ← cambiar
    "db_driver":   "SQL Server",
}

# Unidades reconocidas — si el texto que sigue al número es una de estas,
# es numérico. Si tiene más texto después, es cualitativo.
UNIDADES_SIMPLES = {
    '%', 'p/p', 'p/v', 'v/v',
    'g/ml', 'g/l', 'mg/ml', 'mg/l', 'ml/ml', 'ml/l',
    'mg', 'g', 'ml', 'l', 'µg', 'ug', 'mcg',
    'mg/comp', 'mg/cap', 'mg/tab',
    'ppm', 'ppb',
    'mval', 'meq',
    '%p/p', '%p/v', '%v/v',
}


def normalizar_numero(texto: str) -> float | None:
    """Convierte texto de número con coma decimal a float."""
    texto = texto.strip()
    # Reemplazar coma decimal por punto
    texto = texto.replace(',', '.')
    try:
        return float(texto)
    except ValueError:
        return None


def es_unidad_simple(texto: str) -> bool:
    """Verifica si el texto restante después del número es una unidad simple."""
    if not texto:
        return True  # sin unidad también es válido
    # Limpiar paréntesis y texto de referencia
    texto_limpio = texto.strip().lower()
    # Verificar unidades exactas
    if texto_limpio in UNIDADES_SIMPLES:
        return True
    # Porcentajes con variantes
    if re.match(r'^%\s*$', texto_limpio):
        return True
    return False


def parsear_valor_requerido(texto: str) -> dict | None:
    """
    Intenta parsear el valor_requerido. 
    Retorna dict con {tipo_dato, limite_inferior, limite_superior, unidad_medida}
    o None si no es parseable como numérico.
    """
    if not texto:
        return None

    texto = texto.strip()

    # Patrón numérico: dígitos con punto o coma, opcionalmente decimales
    NUM = r'(\d+(?:[.,]\d+)*)'
    # Separadores de rango: guión largo, guión normal, "a"
    SEP = r'\s*[–\-]\s*'
    # Unidad: lo que sigue (puede estar vacío)

    # ── 1. Patrón: ≤ X [unidad] ────────────────────────────────
    m = re.match(r'^[≤<]=?\s*' + NUM + r'\s*([^\s,;(]*)(.*)$', texto, re.IGNORECASE)
    if m:
        num_str, unidad_raw, resto = m.group(1), m.group(2), m.group(3).strip()
        # Si hay texto significativo después → cualitativo
        if resto and not re.match(r'^[\s\.,;]*$', resto):
            return None
        num = normalizar_numero(num_str)
        if num is None:
            return None
        unidad = unidad_raw.strip().lower() if unidad_raw else ''
        if not es_unidad_simple(unidad + ' ' + resto):
            return None
        unidad_final = (unidad + ' ' + resto).strip() if resto else unidad
        return {
            'tipo_dato': 'numerico',
            'limite_inferior': None,
            'limite_superior': num,
            'unidad_medida': unidad_final or None,
        }

    # ── 2. Patrón: ≥ X [unidad] ────────────────────────────────
    m = re.match(r'^[≥>]=?\s*' + NUM + r'\s*([^\s,;(]*)(.*)$', texto, re.IGNORECASE)
    if m:
        num_str, unidad_raw, resto = m.group(1), m.group(2), m.group(3).strip()
        if resto and not re.match(r'^[\s\.,;]*$', resto):
            return None
        num = normalizar_numero(num_str)
        if num is None:
            return None
        unidad = unidad_raw.strip().lower() if unidad_raw else ''
        if not es_unidad_simple(unidad + ' ' + resto):
            return None
        unidad_final = (unidad + ' ' + resto).strip() if resto else unidad
        return {
            'tipo_dato': 'numerico',
            'limite_inferior': num,
            'limite_superior': None,
            'unidad_medida': unidad_final or None,
        }

    # ── 3. Patrón: X – Y [unidad] ──────────────────────────────
    m = re.match(r'^' + NUM + SEP + NUM + r'\s*([^\s,;(]*)(.*)$', texto)
    if m:
        num1_str, num2_str = m.group(1), m.group(2)
        unidad_raw = m.group(3).strip()
        resto = m.group(4).strip()

        # Si hay mucho texto después → probablemente texto complejo
        if len(resto) > 10 and not re.match(r'^[\s\.,;°C]*$', resto):
            return None

        # Verificar que el segundo límite no sea incompleto (ej: "0,890 – /ml")
        if not num2_str or num2_str.startswith('/'):
            return None

        num1 = normalizar_numero(num1_str)
        num2 = normalizar_numero(num2_str)
        if num1 is None or num2 is None:
            return None

        # El menor va al inferior
        inf, sup = (num1, num2) if num1 <= num2 else (num2, num1)

        unidad = unidad_raw.lower() if unidad_raw else ''
        # Limpiar texto de resto que sea solo unidad adicional
        if resto and re.match(r'^[°Cg/ml%\s\.]*$', resto):
            unidad = (unidad + ' ' + resto).strip()
            resto = ''

        if resto and len(resto) > 5:
            return None  # demasiado texto → cualitativo

        return {
            'tipo_dato': 'numerico',
            'limite_inferior': inf,
            'limite_superior': sup,
            'unidad_medida': unidad or None,
        }

    return None  # No parseable → dejar como cualitativo


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--dry-run', action='store_true',
                        help='Solo muestra los cambios sin aplicarlos')
    args = parser.parse_args()

    # Conectar a BD
    cs = (f"DRIVER={{{CONFIG['db_driver']}}};"
          f"SERVER={CONFIG['db_server']};"
          f"DATABASE={CONFIG['db_name']};"
          f"UID={CONFIG['db_user']};"
          f"PWD={CONFIG['db_password']};"
          f"TrustServerCertificate=yes;")
    conn = pyodbc.connect(cs, autocommit=False)
    cursor = conn.cursor()

    # Traer todos los ensayos con valor_requerido no vacío
    cursor.execute("""
        SELECT id_espec_ensayo, valor_requerido, tipo_dato,
               limite_inferior, limite_superior, unidad_medida
        FROM lims_especificacion_ensayos
        WHERE valor_requerido IS NOT NULL AND valor_requerido <> ''
          AND tipo_dato = 'cualitativo'
          AND limite_inferior IS NULL
          AND limite_superior IS NULL
        ORDER BY id_espec_ensayo
    """)
    registros = cursor.fetchall()

    print(f"Total registros a analizar: {len(registros)}")
    print("=" * 80)

    convertidos = 0
    sin_cambio = 0

    for row in registros:
        id_ee = row.id_espec_ensayo
        valor = row.valor_requerido

        resultado = parsear_valor_requerido(valor)

        if resultado:
            convertidos += 1
            if args.dry_run:
                print(f"ID {id_ee}: CONVERTIR A NUMÉRICO")
                print(f"  valor_requerido:  {valor[:80]}")
                print(f"  limite_inferior:  {resultado['limite_inferior']}")
                print(f"  limite_superior:  {resultado['limite_superior']}")
                print(f"  unidad_medida:    {resultado['unidad_medida']}")
                print()
            else:
                cursor.execute("""
                    UPDATE lims_especificacion_ensayos
                    SET tipo_dato        = 'numerico',
                        limite_inferior  = ?,
                        limite_superior  = ?,
                        unidad_medida    = ?
                    WHERE id_espec_ensayo = ?
                """,
                    resultado['limite_inferior'],
                    resultado['limite_superior'],
                    resultado['unidad_medida'],
                    id_ee
                )
        else:
            sin_cambio += 1

    print("=" * 80)
    print(f"A convertir a numérico: {convertidos}")
    print(f"Se mantienen como cualitativo: {sin_cambio}")

    if not args.dry_run and convertidos > 0:
        conn.commit()
        print(f"\n✓ {convertidos} registros actualizados en la BD.")
    elif args.dry_run:
        print("\n[DRY RUN] No se realizaron cambios en la BD.")

    conn.close()


if __name__ == "__main__":
    main()
