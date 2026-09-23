# -*- coding: utf-8 -*-
"""
importar_aspecto_mp_907.py
===========================
Corrida única: agrega el ensayo "Aspecto" (visual, a cargo del muestreador,
categoría "Aspectos de la Materia Prima", orden 907) a las especificaciones
de Materia Prima listadas en Scripts/data/consolidado_final_mp_aspecto.json
(100 objetos: codigo, nombre, aspecto_texto -- ver forma completa en el
propio JSON).

A diferencia de importar_especificaciones_empaque.py, acá el pedido
original era NO crear especificaciones nuevas (las 100 debían existir ya) --
pero al investigar contra la base real, solo 45/100 códigos tenían una
especificación vigente de materia_prima. De los 55 restantes, 43 SÍ
resuelven contra el ERP (GIM21ART/GIT59SAR, CODSAR de materia_prima) como
artículo real, así que -- decisión explícita del usuario tomada durante
esta misma corrida -- para esos 43 se crea una especificación nueva MÍNIMA
(solo el ensayo Aspecto, ningún otro dato analítico) en vez de saltearlos.
Los 12 códigos que ni siquiera resuelven en el ERP no tienen forma de crear
nada (erp_IdM21 es NOT NULL, atado a un artículo real) -- esos quedan
reportados aparte, sin tocar.

Tres resultados posibles por código:
  1. Especificación vigente ya existe -> se le agrega el ensayo (o se
     saltea si el orden 907 ya estaba, para que correr esto 2 veces sea
     idempotente).
  2. Especificación no existe pero el código resuelve en el ERP como
     materia_prima -> se crea una especificación NUEVA con vigente=0 (mismo
     principio de importar_especificaciones_empaque.py: nadie la usa hasta
     que un humano la revise y la marque vigente a mano) y se le agrega
     SOLO el ensayo Aspecto.
  3. Especificación no existe y el código tampoco resuelve en el ERP -> no
     se crea nada, queda reportado como "no resuelto en el ERP".

El ensayo maestro "Aspecto" y la categoría "materia_prima" deben existir de
antemano (se resuelven una sola vez al principio, se reutiliza el mismo id
para las 100 filas) -- si no existen, el script aborta antes de tocar nada.

Uso, parado en backend/:
    venv\\Scripts\\python.exe Scripts\\importar_aspecto_mp_907.py --dry-run
    venv\\Scripts\\python.exe Scripts\\importar_aspecto_mp_907.py
"""
import argparse
import json
import logging
import sys
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db.connections import get_erp_conn, get_limss_conn
from app.services.erp_materiales import obtener_codsar_por_tipo

logger = logging.getLogger("importar_aspecto_mp_907")

RUTA_JSON = Path(__file__).resolve().parent / "data" / "consolidado_final_mp_aspecto.json"
RUTA_REPORTE = Path(__file__).resolve().parent / "data" / "reporte_importacion_aspecto_mp_907.json"
ID_USUARIO_CARGA = 1  # Administrador Sistema
ORDEN_ASPECTO = 907


def resolver_articulo_erp_mp(ecursor, codigo: str, codsar_mp: str):
    """Busca `codigo` en GIM21ART, exige que su CODSAR sea el de materia_
    prima -- None si no existe el artículo o existe con otro CODSAR (ese
    caso no se vio en la corrida real, pero no se asume)."""
    ecursor.execute(
        """
        SELECT art.M21Id AS IdM21, RTRIM(art.CODART) AS CODART, RTRIM(art.DESART) AS DESART, RTRIM(sar.CODSAR) AS CODSAR
        FROM GIM21ART art
        LEFT JOIN GIT59SAR sar ON sar.T59Id = art.IdT59
        WHERE RTRIM(art.CODART) = ?
        """,
        codigo,
    )
    filas = ecursor.fetchall()
    match = [f for f in filas if f.CODSAR == codsar_mp]
    return match[0] if match else None


def main(dry_run: bool):
    with open(RUTA_JSON, encoding="utf-8") as f:
        items = json.load(f)

    logger.info("Codigos en el JSON: %d", len(items))
    logger.info("Modo: %s", "DRY RUN (no se escribe nada)" if dry_run else "INSERCION REAL EN LIMSS (PRODUCCION)")

    ensayo_agregado_a_existente = []
    ya_existia_orden_907 = []
    especificacion_nueva_creada = []
    no_resueltos_en_erp = []
    errores = []

    with get_limss_conn() as conn, get_erp_conn() as erp:
        cursor = conn.cursor()
        ecursor = erp.cursor()

        cursor.execute(
            "SELECT id_ensayo_maestro, nombre_ensayo FROM lims_ensayos_maestro WHERE LOWER(LTRIM(RTRIM(nombre_ensayo))) = 'aspecto'"
        )
        filas_aspecto = cursor.fetchall()
        if not filas_aspecto:
            logger.error("No existe ningun ensayo maestro 'Aspecto' -- abortando sin tocar nada.")
            sys.exit(1)
        if len(filas_aspecto) > 1:
            logger.error("Hay MAS DE UN ensayo maestro 'Aspecto' (%s) -- ambiguo, abortando sin tocar nada.",
                         [f.id_ensayo_maestro for f in filas_aspecto])
            sys.exit(1)
        id_ensayo_maestro_aspecto = filas_aspecto[0].id_ensayo_maestro
        logger.info("Ensayo maestro 'Aspecto' reutilizado: id_ensayo_maestro=%d", id_ensayo_maestro_aspecto)

        cursor.execute("SELECT id_categoria FROM lims_categorias_ensayo WHERE codigo = 'materia_prima'")
        fila_cat = cursor.fetchone()
        if not fila_cat:
            logger.error("No existe la categoria 'materia_prima' en lims_categorias_ensayo -- abortando sin tocar nada.")
            sys.exit(1)
        id_categoria_mp = fila_cat.id_categoria
        logger.info("Categoria 'materia_prima' reutilizada: id_categoria=%d", id_categoria_mp)

        codsar_mp = obtener_codsar_por_tipo(conn).get("materia_prima")
        logger.info("CODSAR de materia_prima: %s", codsar_mp)

        for item in items:
            codigo = item["codigo"].strip()
            nombre_json = item["nombre"].strip()
            aspecto_texto = (item.get("aspecto_texto") or "").strip() or None

            try:
                # OJO: sin filtrar por vigente=1 -- si se filtrara, una
                # especificacion creada por ESTE MISMO script en una corrida
                # anterior (vigente=0 a proposito, ver mas abajo) no se
                # reconoceria como ya existente en la corrida siguiente y se
                # duplicaria (bug real, confirmado en la corrida de prueba de
                # idempotencia: 43 especificaciones quedaron duplicadas y
                # hubo que borrarlas a mano).
                cursor.execute(
                    "SELECT id_especificacion FROM lims_especificaciones WHERE RTRIM(erp_CODART) = ?",
                    codigo,
                )
                existente = cursor.fetchone()

                if existente:
                    id_especificacion = existente.id_especificacion
                    especificacion_nueva = False
                else:
                    articulo = resolver_articulo_erp_mp(ecursor, codigo, codsar_mp)
                    if not articulo:
                        no_resueltos_en_erp.append({"codigo": codigo, "nombre_json": nombre_json})
                        logger.warning("[SIN RESOLVER EN ERP] %s (%s) -- no existe como articulo de materia_prima en el ERP", codigo, nombre_json)
                        continue

                    if not dry_run:
                        cursor.execute(
                            """
                            INSERT INTO lims_especificaciones
                                (erp_IdM21, erp_CODART, erp_DESART, tipo_material, version, vigente,
                                 erp_codsar, id_usuario_carga, fecha_carga)
                            VALUES (?, ?, ?, 'materia_prima', '1.0', 0, ?, ?, GETDATE())
                            """,
                            articulo.IdM21, articulo.CODART, articulo.DESART, codsar_mp, ID_USUARIO_CARGA,
                        )
                        cursor.execute("SELECT @@IDENTITY AS id")
                        id_especificacion = int(cursor.fetchone().id)
                    else:
                        id_especificacion = None
                    especificacion_nueva = True
                    especificacion_nueva_creada.append({
                        "codigo": codigo, "id_especificacion": id_especificacion,
                        "erp_DESART": articulo.DESART, "erp_IdM21": articulo.IdM21,
                    })
                    logger.info(
                        "[ESPECIFICACION NUEVA] %s -> id_especificacion=%s, vigente=0 (erp_DESART='%s')%s",
                        codigo, id_especificacion, articulo.DESART, " [DRY RUN, no persistido]" if dry_run else "",
                    )

                if not especificacion_nueva:
                    cursor.execute(
                        "SELECT 1 FROM lims_especificacion_ensayos WHERE id_especificacion = ? AND orden = ?",
                        id_especificacion, ORDEN_ASPECTO,
                    )
                    if cursor.fetchone():
                        ya_existia_orden_907.append({"codigo": codigo, "id_especificacion": id_especificacion})
                        logger.info("[YA EXISTIA] %s (id_especificacion=%d) ya tiene un ensayo en orden %d -- salteado", codigo, id_especificacion, ORDEN_ASPECTO)
                        if not dry_run:
                            conn.commit()
                        continue

                if not dry_run:
                    cursor.execute(
                        """
                        INSERT INTO lims_especificacion_ensayos
                            (id_especificacion, id_ensayo_maestro, orden, id_categoria, etapa, tipo_dato,
                             especificacion_texto, obligatorio, requerido_por_defecto, activo)
                        VALUES (?, ?, ?, ?, 'muestreo', 'cualitativo', ?, 0, 1, 1)
                        """,
                        id_especificacion, id_ensayo_maestro_aspecto, ORDEN_ASPECTO, id_categoria_mp, aspecto_texto,
                    )
                    conn.commit()

                if not especificacion_nueva:
                    ensayo_agregado_a_existente.append({"codigo": codigo, "id_especificacion": id_especificacion})
                    logger.info(
                        "[OK] %s (id_especificacion=%d) -> ensayo Aspecto agregado en orden %d%s",
                        codigo, id_especificacion, ORDEN_ASPECTO, " [DRY RUN, no persistido]" if dry_run else "",
                    )

            except Exception as exc:
                if not dry_run:
                    conn.rollback()
                errores.append({"codigo": codigo, "error": str(exc)})
                logger.error("[ERROR] %s -- rollback de este item, se sigue con los demas: %s", codigo, exc, exc_info=True)

    reporte = {
        "fecha": datetime.now().isoformat(),
        "modo": "dry-run" if dry_run else "real",
        "total_en_json": len(items),
        "ensayos_agregados_a_especificacion_existente": len(ensayo_agregado_a_existente),
        "salteados_ya_existia_orden_907": len(ya_existia_orden_907),
        "especificaciones_nuevas_creadas": len(especificacion_nueva_creada),
        "no_resueltos_en_erp": len(no_resueltos_en_erp),
        "errores_inesperados": len(errores),
        "id_ensayo_maestro_aspecto_reutilizado": id_ensayo_maestro_aspecto,
        "detalle_ensayos_agregados": ensayo_agregado_a_existente,
        "detalle_salteados": ya_existia_orden_907,
        "detalle_especificaciones_nuevas": especificacion_nueva_creada,
        "detalle_no_resueltos_en_erp": no_resueltos_en_erp,
        "detalle_errores": errores,
    }
    with open(RUTA_REPORTE, "w", encoding="utf-8") as f:
        json.dump(reporte, f, ensure_ascii=False, indent=2, default=str)

    logger.info("=" * 70)
    logger.info("RESUMEN FINAL (%s)", "DRY RUN" if dry_run else "REAL")
    logger.info("  Total en el JSON:                                 %d", len(items))
    logger.info("  Ensayos agregados a especificacion EXISTENTE:      %d", len(ensayo_agregado_a_existente))
    logger.info("  Salteados (orden 907 ya existia):                 %d", len(ya_existia_orden_907))
    logger.info("  Especificaciones NUEVAS creadas (vigente=0):      %d", len(especificacion_nueva_creada))
    logger.info("  No resueltos en el ERP (sin tocar):                %d", len(no_resueltos_en_erp))
    for n in no_resueltos_en_erp:
        logger.info("      - %s (%s)", n["codigo"], n["nombre_json"])
    logger.info("  Errores inesperados:                               %d", len(errores))
    for e in errores:
        logger.info("      - %s: %s", e["codigo"], e["error"])
    logger.info("  Ensayo maestro 'Aspecto' reutilizado (id=%d) en TODOS los casos -- ninguno nuevo creado.", id_ensayo_maestro_aspecto)
    logger.info("Reporte completo guardado en: %s", RUTA_REPORTE)
    logger.info("=" * 70)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Agregar ensayo Aspecto (orden 907) a especificaciones de Materia Prima")
    parser.add_argument("--dry-run", action="store_true", help="No escribe nada -- solo simula y reporta")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(levelname)-8s  %(message)s")
    main(dry_run=args.dry_run)
