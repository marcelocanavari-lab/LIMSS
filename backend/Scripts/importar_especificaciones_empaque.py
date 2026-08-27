# -*- coding: utf-8 -*-
"""
importar_especificaciones_empaque.py
=====================================
Corrida única: importa las 238 especificaciones de Material de Empaque
(primario y secundario) extraídas de las Hojas de Especificación en Word,
ya parseadas y consolidadas en Scripts/data/especificaciones_empaque_consolidado.json
-- este script NO vuelve a extraer nada de los .docx, solo carga lo que ya
viene estructurado.

Principio rector: no automatizar a ciegas sobre datos GMP-relevantes.
  - Toda especificación nueva entra con vigente=0 -- nadie la usa en el
    sistema hasta que un humano la revise y la marque vigente a mano (o en
    lote, ya con confianza, desde la ficha o un script aparte).
  - Si erp_CODART ya existe en lims_especificaciones, se SALTEA esa
    especificación entera (no se toca, no se fusiona) y queda en el reporte
    de conflictos con el detalle de ambas versiones, para que un humano
    decida.
  - erp_codsar se resuelve vía resolver_codsar_por_codart (la misma función
    ya usada/verificada en backfill_erp_codsar.py) -- si no resuelve, NO
    frena la especificación: se crea igual con erp_codsar NULL (corregible
    después con ese mismo backfill) y queda anotado en el reporte.
  - Transacción POR especificación: si algo falla a mitad de una, esa
    especificación puntual hace rollback (nada a medio cargar) y se sigue
    con las demás -- un error puntual no debe tirar abajo toda la corrida.

IMPORTANTE -- por qué este script NO sigue el patrón de los scripts viejos
Scripts/importar_especificaciones_pt.py / importar_especificaciones_mp.py:
esos dos insertan erp_IdM21 hardcodeado en 0 (no resuelven el artículo real
contra el ERP) y vigente=1 (quedan vigentes de entrada, sin revisión). Lo
primero es la causa raíz confirmada del bug investigado en
backfill_erp_codsar.py esta misma sesión (erp_CODART con el código "base"
en vez del que realmente tiene el ERP, que no matcheaba por texto). Acá se
resuelve erp_IdM21 de verdad contra GIM21ART/GIT59SAR para cada código
(igual que hace el buscador de materiales real, ver
app/services/erp_materiales.buscar_materiales) -- si un código no tiene
ningún artículo real en el ERP, NO se puede crear la especificación
(erp_IdM21 es NOT NULL en el esquema) y queda en el reporte como "no
resuelto en el ERP", no se inventa un valor.

Uso, parado en backend/:
    venv\\Scripts\\python.exe Scripts\\importar_especificaciones_empaque.py --dry-run
    venv\\Scripts\\python.exe Scripts\\importar_especificaciones_empaque.py
"""
import argparse
import json
import logging
import sys
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db.connections import get_erp_conn, get_limss_conn
from app.services.erp_ir import resolver_codsar_por_codart
from app.services.erp_materiales import obtener_codsars_material_empaque

logger = logging.getLogger("importar_especificaciones_empaque")

RUTA_JSON = Path(__file__).resolve().parent / "data" / "especificaciones_empaque_consolidado.json"
RUTA_REPORTE = Path(__file__).resolve().parent / "data" / "reporte_importacion_empaque.json"
ID_USUARIO_CARGA = 1  # Administrador Sistema (único admin activo en LIMSS_DEV al momento de escribir esto)


def normalizar_nombre_ensayo(nombre: str) -> str:
    """trim + colapsa espacios/saltos de línea internos a uno solo -- el JSON
    trae al menos un caso con un salto de línea en medio del nombre
    ("control de\\n predoblado"), que un simple .strip() no arregla y
    terminaría creando un ensayo maestro duplicado del ya normalizado
    "control de predoblado"."""
    return " ".join(nombre.split())


def resolver_articulo_erp(ecursor, codigo: str, codsares_empaque: list[str]):
    """Busca `codigo` en GIM21ART (RTRIM, igual que buscar_materiales en
    erp_materiales.py) -- si aparece con más de un CODSAR (no debería, pero
    no se asume), prioriza el que sea de Material de Empaque (0005/0006).
    None si el código no tiene ningún artículo real en el ERP."""
    ecursor.execute(
        """
        SELECT art.M21Id AS IdM21, RTRIM(art.CODART) AS CODART, RTRIM(art.DESART) AS DESART, sar.CODSAR
        FROM GIM21ART art
        INNER JOIN GIT59SAR sar ON sar.T59Id = art.IdT59
        WHERE RTRIM(art.CODART) = ?
        """,
        codigo,
    )
    filas = ecursor.fetchall()
    if not filas:
        return None
    match_empaque = [f for f in filas if f.CODSAR in codsares_empaque]
    return match_empaque[0] if match_empaque else filas[0]


def main(dry_run: bool):
    with open(RUTA_JSON, encoding="utf-8") as f:
        especificaciones = json.load(f)

    logger.info("Especificaciones en el JSON: %d", len(especificaciones))
    logger.info("Modo: %s", "DRY RUN (no se escribe nada)" if dry_run else "INSERCION REAL EN LIMSS_DEV")

    creadas = []
    conflictos = []
    no_resueltas_erp = []
    sin_codsar = []
    errores = []
    ensayos_maestro_nuevos = {}  # nombre normalizado -> id (nuevo)
    ensayos_maestro_reutilizados_count = 0
    ensayos_insertados_total = 0
    ensayos_con_revisar = []  # (codigo, nombre_ensayo, motivos) -- ver campo "revisar" del JSON

    with get_limss_conn() as conn, get_erp_conn() as erp:
        cursor = conn.cursor()
        ecursor = erp.cursor()
        codsares_empaque = obtener_codsars_material_empaque(cursor)
        logger.info("CODSAR de Material de Empaque: %s", codsares_empaque)

        cursor.execute("SELECT id_ensayo_maestro, nombre_ensayo FROM lims_ensayos_maestro")
        cache_ensayos_maestro = {
            normalizar_nombre_ensayo(r.nombre_ensayo).lower(): r.id_ensayo_maestro for r in cursor.fetchall()
        }
        logger.info("Ensayos maestro ya existentes en la base: %d", len(cache_ensayos_maestro))

        for item in especificaciones:
            codigo = item["codigo"].strip()
            nombre_json = item["nombre"].strip()
            tipo_embalaje = item.get("tipo_embalaje")

            try:
                cursor.execute(
                    "SELECT id_especificacion, erp_DESART, tipo_material, vigente, version "
                    "FROM lims_especificaciones WHERE RTRIM(erp_CODART) = ?",
                    codigo,
                )
                existente = cursor.fetchone()
                if existente:
                    conflictos.append({
                        "codigo": codigo,
                        "id_especificacion_existente": existente.id_especificacion,
                        "erp_DESART_existente": (existente.erp_DESART or "").strip(),
                        "tipo_material_existente": existente.tipo_material,
                        "vigente_existente": bool(existente.vigente),
                        "version_existente": existente.version,
                        "nombre_json_a_importar": nombre_json,
                        "tipo_embalaje_json_a_importar": tipo_embalaje,
                    })
                    logger.info("[CONFLICTO] %s ya existe (id_especificacion=%s) -- salteada", codigo, existente.id_especificacion)
                    continue

                articulo = resolver_articulo_erp(ecursor, codigo, codsares_empaque)
                if not articulo:
                    no_resueltas_erp.append({"codigo": codigo, "nombre_json": nombre_json})
                    logger.warning("[SIN RESOLVER EN ERP] %s -- no existe ningun articulo con ese CODART", codigo)
                    continue

                erp_codsar = resolver_codsar_por_codart(erp, articulo.CODART)

                # En --dry-run NUNCA se ejecuta ningún INSERT (ni siquiera
                # dentro de una transacción que después se deshace): un
                # ensayo maestro "creado" sin commit y su especificación
                # dependiente conviven en la misma transacción abierta sin
                # problema mientras se sigue de largo, pero en cuanto se
                # necesitara hacer rollback de UNA especificación puntual
                # (por un error real más adelante) se arrastraría también el
                # ensayo maestro recién insertado por OTRA especificación
                # anterior en la misma corrida, dejando el caché en memoria
                # apuntando a un id_ensayo_maestro que ya no existe -- FK
                # violation confirmada al probarlo. Simular en memoria (sin
                # tocar la base) evita el problema de raíz en vez de
                # parchear el orden de los rollbacks.
                if not dry_run:
                    cursor.execute(
                        """
                        INSERT INTO lims_especificaciones
                            (erp_IdM21, erp_CODART, erp_DESART, tipo_material, version, vigente,
                             id_usuario_carga, fecha_carga, erp_codsar, tipo_embalaje)
                        VALUES (?, ?, ?, 'material_empaque', '1.0', 0, ?, GETDATE(), ?, ?)
                        """,
                        articulo.IdM21, articulo.CODART, articulo.DESART,
                        ID_USUARIO_CARGA, erp_codsar, tipo_embalaje,
                    )
                    cursor.execute("SELECT @@IDENTITY AS id")
                    id_especificacion = int(cursor.fetchone().id)
                else:
                    id_especificacion = None

                if not erp_codsar:
                    sin_codsar.append({"codigo": codigo, "id_especificacion": id_especificacion})

                ensayos_json = item.get("ensayos", [])
                for orden, en in enumerate(ensayos_json, start=1):
                    nombre_ensayo_norm = normalizar_nombre_ensayo(en["nombre_ensayo"])
                    clave = nombre_ensayo_norm.lower()
                    id_ensayo_maestro = cache_ensayos_maestro.get(clave)
                    if id_ensayo_maestro is None:
                        if not dry_run:
                            cursor.execute(
                                "INSERT INTO lims_ensayos_maestro (nombre_ensayo) VALUES (?)",
                                nombre_ensayo_norm,
                            )
                            cursor.execute("SELECT @@IDENTITY AS id")
                            id_ensayo_maestro = int(cursor.fetchone().id)
                        else:
                            id_ensayo_maestro = -(len(ensayos_maestro_nuevos) + 1)  # id simulado, nunca real
                        cache_ensayos_maestro[clave] = id_ensayo_maestro
                        ensayos_maestro_nuevos[nombre_ensayo_norm] = id_ensayo_maestro
                    else:
                        ensayos_maestro_reutilizados_count += 1

                    metodologia = (en.get("metodologia") or "").strip() or None
                    especificacion_texto = (en.get("especificacion_texto") or "").strip() or None

                    if not dry_run:
                        cursor.execute(
                            """
                            INSERT INTO lims_especificacion_ensayos
                                (id_especificacion, id_ensayo_maestro, orden, metodologia, tipo_dato,
                                 limite_inferior, limite_superior, unidad_medida, especificacion_texto,
                                 obligatorio, requerido_por_defecto, id_laboratorio, activo, etapa)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0, 1, NULL, 1, 'muestreo')
                            """,
                            id_especificacion, id_ensayo_maestro, orden, metodologia, en["tipo_dato"],
                            en.get("limite_inferior"), en.get("limite_superior"), en.get("unidad_medida"),
                            especificacion_texto,
                        )
                    ensayos_insertados_total += 1

                    if en.get("revisar"):
                        ensayos_con_revisar.append({
                            "codigo": codigo, "nombre_ensayo": nombre_ensayo_norm, "motivos": en["revisar"],
                        })

                if not dry_run:
                    conn.commit()

                creadas.append({
                    "codigo": codigo, "id_especificacion": id_especificacion,
                    "erp_DESART": articulo.DESART, "erp_codsar": erp_codsar, "n_ensayos": len(ensayos_json),
                })
                logger.info(
                    "[OK] %s -> id_especificacion=%s (%d ensayos, erp_codsar=%s)%s",
                    codigo, id_especificacion, len(ensayos_json), erp_codsar,
                    " [DRY RUN, no persistido]" if dry_run else "",
                )

            except Exception as exc:
                conn.rollback()
                errores.append({"codigo": codigo, "error": str(exc)})
                logger.error("[ERROR] %s -- rollback de esta especificacion, se sigue con las demas: %s", codigo, exc, exc_info=True)

    reporte = {
        "fecha": datetime.now().isoformat(),
        "modo": "dry-run" if dry_run else "real",
        "total_en_json": len(especificaciones),
        "creadas": len(creadas),
        "conflictos_ya_existian": len(conflictos),
        "no_resueltas_en_erp": len(no_resueltas_erp),
        "errores_inesperados": len(errores),
        "ensayos_insertados_total": ensayos_insertados_total,
        "ensayos_maestro_nuevos_count": len(ensayos_maestro_nuevos),
        "ensayos_maestro_reutilizados_count": ensayos_maestro_reutilizados_count,
        "especificaciones_sin_codsar_resuelto": len(sin_codsar),
        "detalle_creadas": creadas,
        "detalle_conflictos": conflictos,
        "detalle_no_resueltas_en_erp": no_resueltas_erp,
        "detalle_errores": errores,
        "detalle_ensayos_maestro_nuevos": sorted(ensayos_maestro_nuevos.keys()),
        "detalle_especificaciones_sin_codsar": sin_codsar,
        "detalle_ensayos_marcados_para_revisar": ensayos_con_revisar,
    }
    with open(RUTA_REPORTE, "w", encoding="utf-8") as f:
        json.dump(reporte, f, ensure_ascii=False, indent=2, default=str)

    logger.info("=" * 70)
    logger.info("RESUMEN FINAL (%s)", "DRY RUN" if dry_run else "REAL")
    logger.info("  Total en el JSON:                    %d", len(especificaciones))
    logger.info("  Especificaciones creadas:             %d", len(creadas))
    logger.info("  Salteadas por ya existir (conflicto):  %d", len(conflictos))
    for c in conflictos:
        logger.info("      - %s (ya existe como id_especificacion=%s)", c["codigo"], c["id_especificacion_existente"])
    logger.info("  No resueltas contra el ERP (excluidas): %d", len(no_resueltas_erp))
    for n in no_resueltas_erp:
        logger.info("      - %s", n["codigo"])
    logger.info("  Errores inesperados:                   %d", len(errores))
    for e in errores:
        logger.info("      - %s: %s", e["codigo"], e["error"])
    logger.info("  Ensayos insertados en total:           %d", ensayos_insertados_total)
    logger.info("  Ensayos maestro NUEVOS creados:        %d", len(ensayos_maestro_nuevos))
    logger.info("  Ensayos maestro reutilizados:          %d", ensayos_maestro_reutilizados_count)
    logger.info("  Especificaciones con erp_codsar NULL:  %d", len(sin_codsar))
    logger.info("  Ensayos con aviso 'revisar' del parseo: %d", len(ensayos_con_revisar))
    logger.info("Reporte completo guardado en: %s", RUTA_REPORTE)
    logger.info("=" * 70)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Importar especificaciones de Material de Empaque al LIMSS")
    parser.add_argument("--dry-run", action="store_true", help="No escribe nada -- solo simula y reporta")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(levelname)-8s  %(message)s")
    main(dry_run=args.dry_run)
