# -*- coding: utf-8 -*-
"""
importar_lecturas_equipo_agua.py
=================================
Corrida única: importa las 130 lecturas históricas del Equipo de
Purificación de Agua desde Scripts/data/control_de_variables_consolidado.csv
a lims_equipo_lecturas / lims_equipo_lectura_valores.

Mapeo columna CSV -> variable de lims_equipo_variables (por codigo cuando
existe, por nombre cuando el codigo es NULL) -- ver MAPEO_COLUMNAS más abajo,
confirmado contra la tabla real antes de escribir este script.

codigo_documento/realizo/verifico del CSV NO se importan (decisión
explícita del usuario -- no aportan valor acá, el CSV las trae vacías o son
un dato de documento que no hace falta guardar); id_usuario_realizo/
id_usuario_verifico quedan NULL en las 130 filas.

Idempotencia: una fila del CSV se saltea si ya existe una lectura para el
mismo (id_equipo, fecha, hora) CON LOS MISMOS VALORES -- correr esto dos
veces no duplica nada. Si ya existe una lectura para esa fecha+hora pero con
valores DISTINTOS (visto en la práctica: un segundo archivo con lecturas
reales pero distintas que coinciden por casualidad en fecha+hora con algo
ya cargado), NO se pisa ni se inserta un duplicado en silencio -- se
reporta aparte como "conflicto de valor" para que un humano decida (ver
detalle_conflictos_valor en el reporte).
Transacción POR FILA del CSV (mismo criterio que importar_especificaciones_
empaque.py): si una fila falla, se hace rollback solo de esa fila y se
sigue con las demás.

"Fuera de rango" es solo informativo en el reporte (esperable en un
registro histórico real) -- no bloquea ni excluye nada, se inserta el
valor igual.

Uso, parado en backend/:
    venv\\Scripts\\python.exe Scripts\\importar_lecturas_equipo_agua.py --dry-run
    venv\\Scripts\\python.exe Scripts\\importar_lecturas_equipo_agua.py
"""
import argparse
import csv
import logging
import sys
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db.connections import get_limss_conn

logger = logging.getLogger("importar_lecturas_equipo_agua")

RUTA_CSV_DEFAULT = Path(__file__).resolve().parent / "data" / "control_de_variables_consolidado.csv"
RUTA_REPORTE = Path(__file__).resolve().parent / "data" / "reporte_importacion_lecturas_agua.json"
NOMBRE_EQUIPO = "Equipo de Purificación de Agua"

# columna del CSV -> ("codigo", valor) o ("nombre", valor) para buscar en
# lims_equipo_variables -- confirmado 1 a 1 contra la tabla real (13
# variables) antes de escribir esto.
MAPEO_COLUMNAS = [
    ("orp_mv", "nombre", "ORP"),
    ("ph_alimentacion", "nombre", "pH"),
    ("presion_pi01_baja_bomba_bar", "codigo", "PI-01"),
    ("presion_pi02_big_blue_bar", "codigo", "PI-02"),
    ("presion_pi03_alimentacion_bar", "codigo", "PI-03"),
    ("presion_pi04_entrada_e1_kgcm2", "codigo", "PI-04"),
    ("presion_pi05_salida_e1_bar", "codigo", "PI-05"),
    ("presion_pi06_entrada_e2_bar", "codigo", "PI-06"),
    ("presion_pi07_salida_e2_bar", "codigo", "PI-07"),
    ("caudal_fs01_alimentacion_lpm", "codigo", "FS-01"),
    ("caudal_fs02_concen1_lpm", "codigo", "FS-02"),
    ("caudal_fs03_concen2_lpm", "codigo", "FS-03"),
    ("conductividad_us", "nombre", "Conductividad"),
]


def _a_datetime(valor: date):
    """El driver ODBC "SQL Server" (legacy) no puede bindear objetos date
    de Python -- se convierte a datetime (mismo problema y mismo fix que en
    el resto del proyecto, ver app/api/routes/equipos.py)."""
    return datetime.combine(valor, datetime.min.time())


def _fuera_de_rango(valor: float, limite_inferior, limite_superior) -> bool:
    if limite_inferior is not None and valor < float(limite_inferior):
        return True
    if limite_superior is not None and valor > float(limite_superior):
        return True
    return False


def main(dry_run: bool, ruta_csv: Path):
    with open(ruta_csv, encoding="utf-8-sig") as f:
        filas = list(csv.DictReader(f))

    logger.info("CSV: %s", ruta_csv)
    logger.info("Filas en el CSV: %d", len(filas))
    logger.info("Modo: %s", "DRY RUN (no se escribe nada)" if dry_run else "INSERCION REAL EN LIMSS_DEV")

    creadas = []
    ya_existian = []
    conflictos_valor = []
    errores = []
    filas_con_desviacion = []

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

        # Resolver el id_variable de cada columna del CSV UNA sola vez --
        # si alguna no resuelve, se aborta antes de tocar nada (error de
        # config, no de datos puntuales).
        columna_a_variable = {}
        for columna, criterio, clave in MAPEO_COLUMNAS:
            tabla = variables_por_codigo if criterio == "codigo" else variables_por_nombre
            variable = tabla.get(clave.strip().lower())
            if not variable:
                logger.error("No se pudo resolver la variable para la columna '%s' (%s='%s') -- abortando.", columna, criterio, clave)
                sys.exit(1)
            columna_a_variable[columna] = variable
        logger.info("Las 13 columnas del CSV resolvieron correctamente contra lims_equipo_variables.")

        for idx, fila in enumerate(filas, start=1):
            fecha_texto = fila["fecha"].strip()
            hora_texto = fila["hora"].strip()
            try:
                fecha = date.fromisoformat(fecha_texto)
                valores_fila = {columna: float(fila[columna].strip()) for columna, _c, _v in MAPEO_COLUMNAS}

                cursor.execute(
                    "SELECT id_lectura FROM lims_equipo_lecturas WHERE id_equipo = ? AND fecha = ? AND hora = ?",
                    id_equipo, _a_datetime(fecha), hora_texto,
                )
                existente = cursor.fetchone()
                if existente:
                    cursor.execute(
                        "SELECT id_variable, valor FROM lims_equipo_lectura_valores WHERE id_lectura = ?",
                        existente.id_lectura,
                    )
                    valores_existentes = {r.id_variable: float(r.valor) for r in cursor.fetchall()}
                    diferencias = []
                    for columna, _criterio, _clave in MAPEO_COLUMNAS:
                        id_variable = columna_a_variable[columna].id_variable
                        valor_csv = valores_fila[columna]
                        valor_bd = valores_existentes.get(id_variable)
                        # Tolerancia de redondeo (DECIMAL en la BD vs float
                        # del CSV) -- no un umbral de "parecido", solo evita
                        # falsos positivos por representación numérica.
                        if valor_bd is None or abs(valor_bd - valor_csv) > 0.001:
                            diferencias.append({"variable": columna_a_variable[columna].nombre, "valor_csv": valor_csv, "valor_bd": valor_bd})

                    if diferencias:
                        conflictos_valor.append({
                            "fecha": fecha_texto, "hora": hora_texto, "id_lectura_existente": existente.id_lectura,
                            "diferencias": diferencias,
                        })
                        logger.warning(
                            "[CONFLICTO DE VALOR] %s %s -- ya existe id_lectura=%d con valores DISTINTOS, no se pisa ni se duplica (%d variables difieren)",
                            fecha_texto, hora_texto, existente.id_lectura, len(diferencias),
                        )
                    else:
                        ya_existian.append({"fecha": fecha_texto, "hora": hora_texto})
                        logger.info("[YA EXISTIA] %s %s -- salteada (mismos valores)", fecha_texto, hora_texto)
                    continue

                if not dry_run:
                    cursor.execute(
                        """
                        INSERT INTO lims_equipo_lecturas
                            (id_equipo, fecha, hora, id_usuario_realizo, id_usuario_verifico, fecha_registro)
                        VALUES (?, ?, ?, NULL, NULL, GETDATE())
                        """,
                        id_equipo, _a_datetime(fecha), hora_texto,
                    )
                    cursor.execute("SELECT @@IDENTITY AS id")
                    id_lectura = int(cursor.fetchone().id)
                else:
                    id_lectura = None

                desviaciones_fila = []
                for columna, _criterio, _clave in MAPEO_COLUMNAS:
                    variable = columna_a_variable[columna]
                    valor = valores_fila[columna]
                    if not dry_run:
                        cursor.execute(
                            "INSERT INTO lims_equipo_lectura_valores (id_lectura, id_variable, valor) VALUES (?, ?, ?)",
                            id_lectura, variable.id_variable, valor,
                        )
                    if _fuera_de_rango(valor, variable.limite_inferior, variable.limite_superior):
                        desviaciones_fila.append({"variable": variable.nombre, "valor": valor})

                if not dry_run:
                    conn.commit()

                creadas.append({"fecha": fecha_texto, "hora": hora_texto, "id_lectura": id_lectura})
                if desviaciones_fila:
                    filas_con_desviacion.append({"fecha": fecha_texto, "hora": hora_texto, "desviaciones": desviaciones_fila})
                logger.info(
                    "[OK] %s %s -> id_lectura=%s (%d desviaciones)%s",
                    fecha_texto, hora_texto, id_lectura, len(desviaciones_fila),
                    " [DRY RUN, no persistido]" if dry_run else "",
                )

            except Exception as exc:
                if not dry_run:
                    conn.rollback()
                errores.append({"fila_csv": idx, "fecha": fecha_texto, "hora": hora_texto, "error": str(exc)})
                logger.error("[ERROR] fila %d (%s %s) -- rollback de esta fila, se sigue con las demas: %s", idx, fecha_texto, hora_texto, exc, exc_info=True)

    import json
    reporte = {
        "fecha_corrida": datetime.now().isoformat(),
        "modo": "dry-run" if dry_run else "real",
        "csv": str(ruta_csv),
        "total_en_csv": len(filas),
        "lecturas_creadas": len(creadas),
        "salteadas_ya_existia": len(ya_existian),
        "conflictos_de_valor": len(conflictos_valor),
        "filas_con_algun_valor_fuera_de_rango": len(filas_con_desviacion),
        "errores": len(errores),
        "detalle_creadas": creadas,
        "detalle_ya_existian": ya_existian,
        "detalle_conflictos_valor": conflictos_valor,
        "detalle_filas_con_desviacion": filas_con_desviacion,
        "detalle_errores": errores,
    }
    with open(RUTA_REPORTE, "w", encoding="utf-8") as f:
        json.dump(reporte, f, ensure_ascii=False, indent=2, default=str)

    logger.info("=" * 70)
    logger.info("RESUMEN FINAL (%s)", "DRY RUN" if dry_run else "REAL")
    logger.info("  Total filas en el CSV:                        %d", len(filas))
    logger.info("  Lecturas creadas:                              %d", len(creadas))
    logger.info("  Salteadas (ya existia, mismos valores):        %d", len(ya_existian))
    logger.info("  Conflictos de valor (misma fecha+hora, valores distintos, NO tocados): %d", len(conflictos_valor))
    for c in conflictos_valor:
        logger.info("      - %s %s (id_lectura_existente=%d): %d variables difieren", c["fecha"], c["hora"], c["id_lectura_existente"], len(c["diferencias"]))
    logger.info("  Filas con algun valor fuera de rango (informativo): %d", len(filas_con_desviacion))
    logger.info("  Errores:                                       %d", len(errores))
    for e in errores:
        logger.info("      - fila %s (%s %s): %s", e["fila_csv"], e["fecha"], e["hora"], e["error"])
    logger.info("Reporte completo guardado en: %s", RUTA_REPORTE)
    logger.info("=" * 70)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Importar lecturas historicas del Equipo de Purificacion de Agua")
    parser.add_argument("--dry-run", action="store_true", help="No escribe nada -- solo simula y reporta")
    parser.add_argument("--csv", type=str, default=None, help="Ruta al CSV a importar (default: control_de_variables_consolidado.csv)")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(levelname)-8s  %(message)s")
    main(dry_run=args.dry_run, ruta_csv=Path(args.csv) if args.csv else RUTA_CSV_DEFAULT)
