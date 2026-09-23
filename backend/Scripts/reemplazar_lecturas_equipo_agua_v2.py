# -*- coding: utf-8 -*-
"""
reemplazar_lecturas_equipo_agua_v2.py
======================================
Reemplazo completo de las lecturas del Equipo de Purificación de Agua:
borra todo lo existente para ese equipo y carga desde el CSV validado
(lecturas_equipo_agua_completo.csv, 1212 filas de datos + encabezado).

Corrige los dos problemas encontrados en el intento anterior:
- Busca ORP/pH/Conductividad por coincidencia parcial (LIKE), no nombre
  exacto -- tolera que en producción la variable se llame "pH Aliment"
  en vez de "pH".
- El log muestra el nombre real de la base conectada (DB_NAME()), no un
  texto fijo.

Maneja:
- Fechas con año de 2 o 4 dígitos mezcladas en el mismo archivo.
- Filas con columnas de más al final ("[cite: N]", campos vacíos) --
  se ignoran, solo se usan las primeras 15 columnas reales.
- Valores límite con "<"/">" (ej. "<2.8") -- se guarda el número sin el
  símbolo, como aproximación.
- Valores genuinamente no numéricos (ej. "Sí") -- se loguean y se
  saltea esa variable puntual para esa fila (no toda la fila).

Uso, parado en backend/:
    C:\\Python312-embed\\python.exe Scripts\\reemplazar_lecturas_equipo_agua_v2.py
    C:\\Python312-embed\\python.exe Scripts\\reemplazar_lecturas_equipo_agua_v2.py --dry-run
"""
import argparse
import csv
import logging
import re
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db.connections import get_limss_conn

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("reemplazar_lecturas_agua")

CSV_PATH = Path(__file__).resolve().parent / "data" / "lecturas_equipo_agua_completo.csv"
NOMBRE_EQUIPO = "Equipo de Purificación de Agua"
ID_USUARIO_REALIZO = 3

# columna CSV -> (codigo en lims_equipo_variables, o None si se busca por nombre)
COLUMNAS = [
    ("ORP_mV", None, "ORP"),
    ("pH_ALI", None, "pH"),
    ("BOMBA_BAJA_PI01", "PI-01", None),
    ("FILTRO_BIG_BLUE_PI02", "PI-02", None),
    ("ALIMENT_PI03", "PI-03", None),
    ("ENTRADA_ETAPA1_PI04", "PI-04", None),
    ("SALIDA_ETAPA1_PI05", "PI-05", None),
    ("ENTRADA_ETAPA2_PI06", "PI-06", None),
    ("SALIDA_ETAPA2_PI07", "PI-07", None),
    ("ALIMENT_FS01", "FS-01", None),
    ("CONCEN1_FS02", "FS-02", None),
    ("CONCEN2_FS03", "FS-03", None),
    ("CONDUCTIVIDAD", None, "Conductividad"),
]


def parsear_fecha(fecha_str: str):
    d, m, y = fecha_str.strip().split("/")
    y_full = int(y) if len(y) == 4 else 2000 + int(y)
    return datetime(y_full, int(m), int(d)).date()


def parsear_valor(valor_str: str):
    """Devuelve (numero, motivo_descarte). Si numero es None, motivo
    explica por que -- para loguear sin adivinar."""
    v = valor_str.strip()
    if not v:
        return None, None  # celda vacia, no es un error, simplemente no hay dato
    m = re.match(r"^([<>])\s*([\d.,]+)$", v)
    if m:
        return float(m.group(2).replace(",", ".")), None
    try:
        return float(v.replace(",", ".")), None
    except ValueError:
        return None, f"valor no numerico: '{v}'"


def resolver_variables(cursor, id_equipo):
    cursor.execute(
        "SELECT id_variable, codigo, nombre FROM lims_equipo_variables WHERE id_equipo = ? AND activo = 1",
        id_equipo,
    )
    filas = cursor.fetchall()
    por_codigo = {f.codigo.strip().upper(): f.id_variable for f in filas if f.codigo}

    resueltas = {}
    for col_csv, codigo, nombre_like in COLUMNAS:
        if codigo:
            id_var = por_codigo.get(codigo.upper())
            if id_var is None:
                raise RuntimeError(f"No se pudo resolver la variable para la columna '{col_csv}' (codigo='{codigo}')")
        else:
            candidatas = [f for f in filas if nombre_like.lower() in f.nombre.lower()]
            if not candidatas:
                raise RuntimeError(f"No se pudo resolver la variable para la columna '{col_csv}' (nombre~'{nombre_like}')")
            if len(candidatas) > 1:
                raise RuntimeError(
                    f"'{nombre_like}' matchea mas de una variable: {[f.nombre for f in candidatas]} -- ambiguo, revisar a mano"
                )
            id_var = candidatas[0].id_variable
        resueltas[col_csv] = id_var
    return resueltas


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="No borra ni inserta nada, solo valida el CSV")
    args = parser.parse_args()

    if not CSV_PATH.exists():
        logger.error("No se encontro el archivo: %s", CSV_PATH)
        sys.exit(1)

    with open(CSV_PATH, encoding="utf-8-sig") as f:
        lector = csv.reader(f)
        header = next(lector)
        filas_csv = list(lector)

    logger.info("Archivo: %s", CSV_PATH)
    logger.info("Filas de datos en el CSV: %d", len(filas_csv))

    with get_limss_conn() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT DB_NAME()")
        nombre_base = cursor.fetchone()[0]
        logger.info("Base conectada: %s", nombre_base)
        logger.info("Modo: %s", "DRY-RUN (no se escribe nada)" if args.dry_run else f"REEMPLAZO REAL EN {nombre_base}")

        cursor.execute("SELECT id_equipo FROM lims_equipos WHERE nombre = ?", NOMBRE_EQUIPO)
        row = cursor.fetchone()
        if not row:
            logger.error("No se encontro el equipo '%s'", NOMBRE_EQUIPO)
            sys.exit(1)
        id_equipo = row[0]
        logger.info("Equipo resuelto: id_equipo=%d", id_equipo)

        columnas_a_variable = resolver_variables(cursor, id_equipo)
        logger.info("Variables resueltas OK para las 13 columnas del CSV.")

        cursor.execute("SELECT id_usuario FROM lims_usuarios WHERE id_usuario = ?", ID_USUARIO_REALIZO)
        if not cursor.fetchone():
            logger.error("id_usuario=%d (Realizo) no existe en lims_usuarios", ID_USUARIO_REALIZO)
            sys.exit(1)

        # --- parseo completo del CSV, sin tocar la base todavia ---
        lecturas_a_insertar = []  # (fecha, hora, {col_csv: valor})
        filas_descartadas = []
        for i, fila in enumerate(filas_csv, start=2):
            if len(fila) < 15:
                filas_descartadas.append((i, ",".join(fila), "menos de 15 columnas"))
                continue
            fecha_str, hora_str = fila[0].strip(), fila[1].strip()
            try:
                fecha = parsear_fecha(fecha_str)
            except Exception as e:
                filas_descartadas.append((i, ",".join(fila), f"fecha invalida: {e}"))
                continue

            valores = {}
            for idx, (col_csv, _, _) in enumerate(COLUMNAS, start=2):  # col 0=fecha, 1=hora, 2..14=variables
                valor_raw = fila[idx] if idx < len(fila) else ""
                numero, motivo = parsear_valor(valor_raw)
                if motivo:
                    logger.info("  [VALOR DESCARTADO] linea %d (%s %s), columna %s: %s", i, fecha_str, hora_str, col_csv, motivo)
                    continue
                if numero is not None:
                    valores[col_csv] = numero

            lecturas_a_insertar.append((fecha, hora_str, valores))

        logger.info("\nLecturas parseadas correctamente: %d", len(lecturas_a_insertar))
        logger.info("Filas totalmente descartadas (fecha invalida / muy cortas): %d", len(filas_descartadas))
        for d in filas_descartadas:
            logger.info("  linea %d: %s -- %s", d[0], d[1][:80], d[2])

        if args.dry_run:
            logger.info("\n(--dry-run: no se borro ni inserto nada)")
            return

        # --- transaccion real: borrar todo lo existente + insertar lo nuevo ---
        cursor.execute(
            "SELECT COUNT(*) FROM lims_equipo_lecturas WHERE id_equipo = ?", id_equipo
        )
        cantidad_previa = cursor.fetchone()[0]

        cursor.execute(
            """
            DELETE FROM lims_equipo_lectura_valores
            WHERE id_lectura IN (SELECT id_lectura FROM lims_equipo_lecturas WHERE id_equipo = ?)
            """,
            id_equipo,
        )
        valores_borrados = cursor.rowcount
        cursor.execute("DELETE FROM lims_equipo_lecturas WHERE id_equipo = ?", id_equipo)
        lecturas_borradas = cursor.rowcount

        total_valores_insertados = 0
        for fecha, hora, valores in lecturas_a_insertar:
            fecha_str = fecha.isoformat()  # 'YYYY-MM-DD' -- el driver ODBC viejo (SQL Server
            # Native Client 11.0) falla al bindear un objeto date de Python directamente
            # (mismo problema ya resuelto antes en esta sesion con _a_fecha()); como texto
            # ISO funciona bien.
            cursor.execute(
                """
                INSERT INTO lims_equipo_lecturas (id_equipo, fecha, hora, id_usuario_realizo, id_usuario_verifico)
                OUTPUT INSERTED.id_lectura
                VALUES (?, ?, ?, ?, NULL)
                """,
                id_equipo, fecha_str, hora, ID_USUARIO_REALIZO,
            )
            id_lectura = cursor.fetchone()[0]
            for col_csv, valor in valores.items():
                id_variable = columnas_a_variable[col_csv]
                cursor.execute(
                    "INSERT INTO lims_equipo_lectura_valores (id_lectura, id_variable, valor) VALUES (?, ?, ?)",
                    id_lectura, id_variable, valor,
                )
                total_valores_insertados += 1

        conn.commit()

        cursor.execute(
            "SELECT MIN(fecha), MAX(fecha) FROM lims_equipo_lecturas WHERE id_equipo = ?", id_equipo
        )
        fecha_min, fecha_max = cursor.fetchone()

        logger.info("\n=== REPORTE FINAL ===")
        logger.info("Lecturas borradas (previas): %d (%d valores)", lecturas_borradas, valores_borrados)
        logger.info("Lecturas nuevas insertadas: %d", len(lecturas_a_insertar))
        logger.info("Valores de variable insertados: %d", total_valores_insertados)
        logger.info("Rango de fechas final: %s a %s", fecha_min, fecha_max)


if __name__ == "__main__":
    main()
