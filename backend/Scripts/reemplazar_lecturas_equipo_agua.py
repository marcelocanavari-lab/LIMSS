# -*- coding: utf-8 -*-
"""
reemplazar_lecturas_equipo_agua.py
====================================
Corrida única: REEMPLAZA por completo el historial de lecturas del Equipo
de Purificación de Agua -- borra todo lo que hay hoy en
lims_equipo_lecturas/lims_equipo_lectura_valores para este equipo y carga
de cero desde Scripts/data/lecturas_equipo_agua_completo.csv (1213 filas,
reemplaza a los dos CSV usados en la importación anterior --
control_de_variables_consolidado.csv/_2.csv, ver importar_lecturas_equipo_
agua.py, que queda como registro histórico de esa corrida y no se toca).

Mapeo de columnas -- incluso con headers distintos, mismas 13 variables que
ya usaba la importación anterior (por codigo cuando existe -- PI-01 a
PI-07, FS-01 a FS-03 --, por nombre cuando no -- ORP, pH, Conductividad).

Fecha con DOS formatos mezclados en el mismo archivo: DD/MM/AA (año de 2
dígitos, asume 2000+AA) y DD/MM/AAAA (año de 4 dígitos, tal cual) -- se
detecta por la longitud del último campo.

id_usuario_realizo = 3 para TODAS las filas (decisión explícita del
usuario). id_usuario_verifico queda NULL en todas (no hay dato de
verificación en este archivo).

Algunas filas tienen columnas de más al final (un campo vacío extra y/o
texto tipo "[cite: 11]", artefacto de conversión) -- csv.DictReader ya las
separa solas bajo la clave None (restkey por default), nunca se leen.

Si una fila no se puede parsear (fecha inválida, o un valor no vacío que
no es numérico donde debería serlo), se descarta la fila COMPLETA -- se
loguea como error y se sigue con el resto, no se inserta nada de esa fila.
Un campo REALMENTE VACÍO para una variable puntual no es error: significa
que esa variable no se cargó en esa lectura (mismo criterio ya establecido
en el resto del sistema -- no todas las lecturas completan las 13).

DELETE (de lo que había) + INSERT (de las 1213 filas nuevas) corren en UNA
sola transacción -- si algo revienta a mitad de camino, rollback total, no
queda el equipo con el historial borrado y la carga nueva a medias.

Uso, parado en backend/:
    venv\\Scripts\\python.exe Scripts\\reemplazar_lecturas_equipo_agua.py --dry-run
    venv\\Scripts\\python.exe Scripts\\reemplazar_lecturas_equipo_agua.py
"""
import argparse
import csv
import json
import logging
import sys
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db.connections import get_limss_conn

logger = logging.getLogger("reemplazar_lecturas_equipo_agua")

RUTA_CSV_DEFAULT = Path(__file__).resolve().parent / "data" / "lecturas_equipo_agua_completo.csv"
RUTA_REPORTE = Path(__file__).resolve().parent / "data" / "reporte_reemplazo_lecturas_agua.json"
NOMBRE_EQUIPO = "Equipo de Purificación de Agua"
ID_USUARIO_REALIZO = 3

# columna del CSV (header real del archivo) -> ("codigo"|"nombre", valor a
# buscar en lims_equipo_variables) -- mismas 13 variables que la
# importación anterior, headers distintos.
MAPEO_COLUMNAS = [
    ("ORP_mV", "nombre", "ORP"),
    ("pH_ALI", "nombre", "pH"),
    ("BOMBA_BAJA_PI01", "codigo", "PI-01"),
    ("FILTRO_BIG_BLUE_PI02", "codigo", "PI-02"),
    ("ALIMENT_PI03", "codigo", "PI-03"),
    ("ENTRADA_ETAPA1_PI04", "codigo", "PI-04"),
    ("SALIDA_ETAPA1_PI05", "codigo", "PI-05"),
    ("ENTRADA_ETAPA2_PI06", "codigo", "PI-06"),
    ("SALIDA_ETAPA2_PI07", "codigo", "PI-07"),
    ("ALIMENT_FS01", "codigo", "FS-01"),
    ("CONCEN1_FS02", "codigo", "FS-02"),
    ("CONCEN2_FS03", "codigo", "FS-03"),
    ("CONDUCTIVIDAD", "nombre", "Conductividad"),
]


def _a_datetime(valor: date):
    """El driver ODBC "SQL Server" (legacy) no puede bindear objetos date
    de Python -- se convierte a datetime (mismo problema y mismo fix que en
    el resto del proyecto, ver app/api/routes/equipos.py)."""
    return datetime.combine(valor, datetime.min.time())


def parsear_fecha(texto: str) -> date:
    """DD/MM/AA (2 dígitos -> 2000+AA) o DD/MM/AAAA (4 dígitos, tal cual) --
    confirmado contra los datos reales: el primer número siempre es día
    (1-31), el segundo siempre mes (1-12), en los dos formatos."""
    partes = texto.strip().split("/")
    if len(partes) != 3:
        raise ValueError(f"formato de fecha inesperado: '{texto}'")
    dia_str, mes_str, anio_str = partes
    dia, mes = int(dia_str), int(mes_str)
    anio = int(anio_str)
    if len(anio_str) == 2:
        anio += 2000
    elif len(anio_str) != 4:
        raise ValueError(f"año con longitud inesperada: '{texto}'")
    return date(anio, mes, dia)


def main(dry_run: bool, ruta_csv: Path):
    with open(ruta_csv, encoding="utf-8-sig") as f:
        filas = list(csv.DictReader(f))

    logger.info("CSV: %s", ruta_csv)
    logger.info("Filas en el CSV: %d", len(filas))
    logger.info("Modo: %s", "DRY RUN (no se escribe nada)" if dry_run else "REEMPLAZO REAL EN LIMSS_DEV")

    creadas = []
    errores = []
    filas_con_desviacion = []
    total_valores_insertados = 0

    with get_limss_conn() as conn:
        cursor = conn.cursor()

        cursor.execute("SELECT id_equipo FROM lims_equipos WHERE nombre = ?", NOMBRE_EQUIPO)
        fila_equipo = cursor.fetchone()
        if not fila_equipo:
            logger.error("No existe el equipo '%s' -- abortando sin tocar nada.", NOMBRE_EQUIPO)
            sys.exit(1)
        id_equipo = fila_equipo.id_equipo
        logger.info("Equipo resuelto: id_equipo=%d", id_equipo)

        cursor.execute(
            "SELECT id_variable, codigo, nombre, limite_inferior, limite_superior FROM lims_equipo_variables WHERE id_equipo = ? AND activo = 1",
            id_equipo,
        )
        variables = cursor.fetchall()
        variables_por_codigo = {(v.codigo or "").strip().lower(): v for v in variables if v.codigo}
        variables_por_nombre = {(v.nombre or "").strip().lower(): v for v in variables if not v.codigo}

        columna_a_variable = {}
        for columna, criterio, clave in MAPEO_COLUMNAS:
            tabla = variables_por_codigo if criterio == "codigo" else variables_por_nombre
            variable = tabla.get(clave.strip().lower())
            if not variable:
                logger.error("No se pudo resolver la variable para la columna '%s' (%s='%s') -- abortando, no se tocó nada.", columna, criterio, clave)
                sys.exit(1)
            columna_a_variable[columna] = variable
        logger.info("Las 13 columnas del CSV resolvieron correctamente contra lims_equipo_variables.")

        # ── Cuánto había ANTES de borrar (para el reporte) ─────────────
        cursor.execute("SELECT COUNT(*) AS n FROM lims_equipo_lecturas WHERE id_equipo = ?", id_equipo)
        lecturas_borradas = cursor.fetchone().n
        cursor.execute(
            """
            SELECT COUNT(*) AS n FROM lims_equipo_lectura_valores
            WHERE id_lectura IN (SELECT id_lectura FROM lims_equipo_lecturas WHERE id_equipo = ?)
            """,
            id_equipo,
        )
        valores_borrados = cursor.fetchone().n
        logger.info("Lecturas existentes a borrar: %d (con %d valores de variable)", lecturas_borradas, valores_borrados)

        if not dry_run:
            cursor.execute(
                """
                DELETE FROM lims_equipo_lectura_valores
                WHERE id_lectura IN (SELECT id_lectura FROM lims_equipo_lecturas WHERE id_equipo = ?)
                """,
                id_equipo,
            )
            cursor.execute("DELETE FROM lims_equipo_lecturas WHERE id_equipo = ?", id_equipo)

        # ── Insertar las filas nuevas -- misma transacción, sin commits
        # intermedios (si algo revienta, rollback de TODO: ni el borrado
        # ni lo insertado hasta ahí queda aplicado). Un error de parseo de
        # UNA fila NO es una excepción de base de datos: se detecta antes
        # de tocar el cursor para esa fila, se loguea, y se sigue -- no
        # dispara ningún rollback.
        for idx, fila in enumerate(filas, start=2):  # +2: línea 1 es el header
            fecha_texto = (fila.get("FECHA") or "").strip()
            hora_texto = (fila.get("HORA") or "").strip()
            try:
                fecha = parsear_fecha(fecha_texto)

                valores_fila = {}
                for columna, _criterio, _clave in MAPEO_COLUMNAS:
                    crudo = (fila.get(columna) or "").strip()
                    if crudo == "":
                        continue  # variable no cargada en esta lectura -- no es error
                    valores_fila[columna] = float(crudo)

            except Exception as exc:
                errores.append({"linea_csv": idx, "fecha": fecha_texto, "hora": hora_texto, "error": str(exc)})
                logger.error("[ERROR] línea %d (%s %s) -- fila descartada completa: %s", idx, fecha_texto, hora_texto, exc)
                continue

            if not dry_run:
                cursor.execute(
                    """
                    INSERT INTO lims_equipo_lecturas
                        (id_equipo, fecha, hora, id_usuario_realizo, id_usuario_verifico, fecha_registro)
                    VALUES (?, ?, ?, ?, NULL, GETDATE())
                    """,
                    id_equipo, _a_datetime(fecha), hora_texto, ID_USUARIO_REALIZO,
                )
                cursor.execute("SELECT @@IDENTITY AS id")
                id_lectura = int(cursor.fetchone().id)
            else:
                id_lectura = None

            desviaciones_fila = []
            for columna, valor in valores_fila.items():
                variable = columna_a_variable[columna]
                if not dry_run:
                    cursor.execute(
                        "INSERT INTO lims_equipo_lectura_valores (id_lectura, id_variable, valor) VALUES (?, ?, ?)",
                        id_lectura, variable.id_variable, valor,
                    )
                total_valores_insertados += 1
                li, ls = variable.limite_inferior, variable.limite_superior
                if (li is not None and valor < float(li)) or (ls is not None and valor > float(ls)):
                    desviaciones_fila.append({"variable": variable.nombre, "valor": valor})

            creadas.append({"linea_csv": idx, "fecha": fecha_texto, "hora": hora_texto, "n_valores": len(valores_fila)})
            if desviaciones_fila:
                filas_con_desviacion.append({"fecha": fecha_texto, "hora": hora_texto, "desviaciones": desviaciones_fila})

        if not dry_run:
            conn.commit()
            logger.info("COMMIT aplicado -- borrado + %d lecturas nuevas persistidos.", len(creadas))
        else:
            logger.info("DRY RUN -- no se aplicó ningún cambio real.")

        # ── Rango de fechas final (post-commit, mismo conn) ────────────
        cursor.execute(
            "SELECT MIN(fecha) AS desde, MAX(fecha) AS hasta, COUNT(*) AS n FROM lims_equipo_lecturas WHERE id_equipo = ?",
            id_equipo,
        )
        rango = cursor.fetchone()

    reporte = {
        "fecha_corrida": datetime.now().isoformat(),
        "modo": "dry-run" if dry_run else "real",
        "csv": str(ruta_csv),
        "total_filas_en_csv": len(filas),
        "lecturas_borradas_antes": lecturas_borradas,
        "valores_borrados_antes": valores_borrados,
        "lecturas_nuevas_insertadas": len(creadas),
        "valores_nuevos_insertados": total_valores_insertados,
        "errores": len(errores),
        "filas_con_algun_valor_fuera_de_rango": len(filas_con_desviacion),
        "rango_fechas_final": {
            "desde": str(rango.desde) if rango and rango.desde else None,
            "hasta": str(rango.hasta) if rango and rango.hasta else None,
            "n_lecturas_en_bd": rango.n if rango else 0,
        } if not dry_run else "N/A (dry-run)",
        "detalle_errores": errores,
        "detalle_filas_con_desviacion": filas_con_desviacion,
    }
    with open(RUTA_REPORTE, "w", encoding="utf-8") as f:
        json.dump(reporte, f, ensure_ascii=False, indent=2, default=str)

    logger.info("=" * 70)
    logger.info("RESUMEN FINAL (%s)", "DRY RUN" if dry_run else "REAL")
    logger.info("  Total filas en el CSV:                 %d", len(filas))
    logger.info("  Lecturas borradas (había antes):       %d (%d valores)", lecturas_borradas, valores_borrados)
    logger.info("  Lecturas nuevas insertadas:             %d", len(creadas))
    logger.info("  Valores de variable insertados:         %d", total_valores_insertados)
    logger.info("  Filas con algún valor fuera de rango:   %d", len(filas_con_desviacion))
    logger.info("  Errores (filas descartadas):            %d", len(errores))
    for e in errores:
        logger.info("      - línea %s (%s %s): %s", e["linea_csv"], e["fecha"], e["hora"], e["error"])
    if not dry_run:
        logger.info("  Rango de fechas final en BD: %s a %s (%d lecturas)", rango.desde, rango.hasta, rango.n)
    logger.info("Reporte completo guardado en: %s", RUTA_REPORTE)
    logger.info("=" * 70)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Reemplazar por completo las lecturas del Equipo de Purificacion de Agua")
    parser.add_argument("--dry-run", action="store_true", help="No escribe nada -- solo simula y reporta")
    parser.add_argument("--csv", type=str, default=None, help="Ruta al CSV (default: lecturas_equipo_agua_completo.csv)")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(levelname)-8s  %(message)s")
    main(dry_run=args.dry_run, ruta_csv=Path(args.csv) if args.csv else RUTA_CSV_DEFAULT)
