# -*- coding: utf-8 -*-
"""
backfill_erp_codsar.py
=======================
Corrida única: recorre las especificaciones con erp_codsar IS NULL, resuelve
el subarticulo (CODSAR) de cada una contra el ERP y actualiza la columna.

No frena ante un erp_CODART que no se encuentra en el ERP (dato de prueba,
artículo discontinuado) -- lo loguea y sigue con el resto.

Historial de este script -- por qué tiene dos métodos de resolución:
-----------------------------------------------------------------
Se corrió en producción una vez: de 88 especificaciones pendientes, solo 2
quedaron resueltas, sin ninguna pista de qué pasó con las otras 86 (el
script solo decía "[SIN RESOLVER]", sin loguear el motivo). Investigando en
LIMSS_DEV con el diagnóstico agregado acá, las 28 especificaciones
pendientes en este entorno (todas tipo_material='producto_terminado')
fallaban TODAS por el mismo motivo real, verificado contra el ERP:
lims_especificaciones.erp_CODART tiene el código "base" del producto (ej.
'PT001'), pero el ERP le agrega a los producto_terminado un sufijo de
tamaño de envase por presentación ('PT001/10', 'PT008/100', 'PT017/12',
etc. -- variable por artículo, no un sufijo fijo) -- probablemente quedó
así por Scripts/importar_especificaciones_pt.py, que cargó el código base.
El match por texto exacto (resolver_codsar_por_codart, WHERE CODART = ?)
nunca iba a encontrar nada aunque el artículo SÍ exista en el ERP. No es el
caso legítimo de "el artículo no tiene equivalente en el ERP" -- es un
desajuste de formato entre el texto guardado y el texto real.

Confirmado con una consulta directa: para las 28 especificaciones de
DEV, GIM21ART.M21Id = lims_especificaciones.erp_IdM21 SIEMPRE encuentra la
fila real del ERP (con su IdT59 ya cargado), aunque el CODART no matchee.
Por eso este script prueba primero resolver_codsar_por_codart (el método
ya usado y verificado -- no se toca su comportamiento para los casos que
ya venían resolviendo bien) y, si falla, cae a resolver_codsar_por_idm21
(mismo JOIN pero por la clave numérica M21Id, que no tiene el problema de
formato de texto) antes de darlo por "sin resolver" de verdad.

Uso, parado en backend/:
    venv\\Scripts\\python.exe Scripts\\backfill_erp_codsar.py
    venv\\Scripts\\python.exe Scripts\\backfill_erp_codsar.py --dry-run
"""
import argparse
import logging
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db.connections import get_erp_conn, get_limss_conn
from app.services.erp_ir import resolver_codsar_por_codart, resolver_codsar_por_idm21

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("backfill_erp_codsar")

MOTIVO_NO_EXISTE_EN_ERP = "erp_CODART no existe en GIM21ART, y erp_IdM21 tampoco resolvió nada (el artículo no está cargado en el ERP)"
MOTIVO_SIN_IDT59 = "el artículo existe en el ERP (por CODART o por IdM21) pero no tiene IdT59 (subarticulo) asignado"
MOTIVO_IDT59_INCONSISTENTE = "el artículo tiene IdT59={idt59} pero ese T59Id no existe en GIT59SAR (dato inconsistente del ERP)"
MOTIVO_CODSAR_VACIO = "el subarticulo (T59Id={idt59}) existe pero su CODSAR viene vacío"
MOTIVO_MULTIPLES_FILAS = "erp_CODART matchea {n} filas distintas en GIM21ART (CODART no es único) -- se usó la primera"
MOTIVO_SIN_IDM21 = "no tiene erp_IdM21 guardado, así que no se pudo intentar el respaldo por M21Id"


def _diagnosticar_no_resuelto(erp, erp_codart: str, erp_idm21) -> str:
    """Determina CUÁL motivo explica que NI resolver_codsar_por_codart NI
    resolver_codsar_por_idm21 hayan podido resolver esta especificación --
    mismo JOIN que ambas, pero trayendo todas las columnas relevantes en
    vez de solo el CODSAR final, para diferenciar "no existe el artículo"
    de "existe pero le falta el subarticulo" de "el subarticulo está mal
    cargado". Prioriza la fila encontrada por IdM21 si existe (más
    confiable que CODART, ver docstring del módulo) para el diagnóstico."""
    cursor = erp.cursor()
    if erp_idm21 is not None:
        cursor.execute(
            """
            SELECT art.M21Id, art.IdT59, sar.T59Id, RTRIM(sar.CODSAR) AS CODSAR
            FROM GIM21ART art
            LEFT JOIN GIT59SAR sar ON sar.T59Id = art.IdT59
            WHERE art.M21Id = ?
            """,
            erp_idm21,
        )
        filas = cursor.fetchall()
        if not filas:
            return MOTIVO_NO_EXISTE_EN_ERP
    else:
        cursor.execute(
            """
            SELECT art.M21Id, art.IdT59, sar.T59Id, RTRIM(sar.CODSAR) AS CODSAR
            FROM GIM21ART art
            LEFT JOIN GIT59SAR sar ON sar.T59Id = art.IdT59
            WHERE RTRIM(art.CODART) = RTRIM(?)
            """,
            erp_codart,
        )
        filas = cursor.fetchall()
        if not filas:
            return MOTIVO_NO_EXISTE_EN_ERP + " -- " + MOTIVO_SIN_IDM21

    prefijo = MOTIVO_MULTIPLES_FILAS.format(n=len(filas)) + " -- " if len(filas) > 1 else ""
    fila = filas[0]

    if fila.IdT59 is None:
        return prefijo + MOTIVO_SIN_IDT59
    if fila.T59Id is None:
        return prefijo + MOTIVO_IDT59_INCONSISTENTE.format(idt59=fila.IdT59)
    if not fila.CODSAR:
        return prefijo + MOTIVO_CODSAR_VACIO.format(idt59=fila.IdT59)
    # No debería llegar acá (si CODSAR tiene valor, alguno de los dos
    # métodos ya lo habría resuelto) -- se deja como red de seguridad para
    # no devolver un diagnóstico vacío si el motivo real es otro no
    # contemplado.
    return f"sin diagnóstico claro (fila encontrada: M21Id={fila.M21Id}, IdT59={fila.IdT59}, T59Id={fila.T59Id}, CODSAR='{fila.CODSAR}')"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="Solo muestra qué se resolvería, no escribe en la BD")
    args = parser.parse_args()

    resueltos_por_codart = 0
    resueltos_por_idm21 = 0
    no_encontrados = []  # (id_especificacion, erp_CODART, erp_DESART, tipo_material, motivo)

    with get_limss_conn() as conn, get_erp_conn() as erp:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id_especificacion, erp_CODART, erp_DESART, tipo_material, erp_IdM21 FROM lims_especificaciones WHERE erp_codsar IS NULL"
        )
        pendientes = cursor.fetchall()
        logger.info("Especificaciones con erp_codsar pendiente: %d", len(pendientes))

        for espec in pendientes:
            codart = espec.erp_CODART.strip() if espec.erp_CODART else espec.erp_CODART
            metodo = "CODART"
            codsar = resolver_codsar_por_codart(erp, codart)

            if codsar is None and espec.erp_IdM21 is not None:
                metodo = "IdM21 (respaldo -- CODART no matcheó exacto)"
                codsar = resolver_codsar_por_idm21(erp, espec.erp_IdM21)

            if codsar is None:
                motivo = _diagnosticar_no_resuelto(erp, codart, espec.erp_IdM21)
                no_encontrados.append((espec.id_especificacion, codart, espec.erp_DESART, espec.tipo_material, motivo))
                logger.info(
                    "  [SIN RESOLVER] id=%s erp_CODART='%s' (%s, tipo_material=%s) -- %s",
                    espec.id_especificacion, codart, espec.erp_DESART, espec.tipo_material, motivo,
                )
                continue

            logger.info("  [OK por %s] id=%s erp_CODART='%s' -> erp_codsar='%s'", metodo, espec.id_especificacion, codart, codsar)
            if not args.dry_run:
                cursor.execute(
                    "UPDATE lims_especificaciones SET erp_codsar = ? WHERE id_especificacion = ?",
                    codsar, espec.id_especificacion,
                )
            if metodo == "CODART":
                resueltos_por_codart += 1
            else:
                resueltos_por_idm21 += 1

        if not args.dry_run:
            conn.commit()

    total_resueltos = resueltos_por_codart + resueltos_por_idm21
    logger.info(
        "\nResueltos: %d/%d (por CODART: %d, por IdM21 de respaldo: %d)",
        total_resueltos, len(pendientes), resueltos_por_codart, resueltos_por_idm21,
    )
    if no_encontrados:
        logger.info("\nSin resolver (%d):", len(no_encontrados))
        for id_esp, codart, desart, tipo_material, motivo in no_encontrados:
            logger.info("  id_especificacion=%s  erp_CODART='%s'  (%s, tipo_material=%s)\n    -> %s", id_esp, codart, desart, tipo_material, motivo)

        # Agrupado por motivo (sin el detalle de M21Id/IdT59/etc. de la fila
        # puntual, para que casos con el mismo motivo de fondo cuenten
        # juntos) y por tipo_material, para detectar de un vistazo si el
        # problema es transversal o concentrado en un tipo puntual.
        logger.info("\n=== Agrupado por motivo ===")
        motivos_base = Counter(m.split(" -- ")[0] for _, _, _, _, m in no_encontrados)
        for motivo, cantidad in motivos_base.most_common():
            logger.info("  %d x %s", cantidad, motivo)

        logger.info("\n=== Agrupado por tipo_material ===")
        tipos = Counter(tm or "(sin tipo_material)" for _, _, _, tm, _ in no_encontrados)
        for tipo, cantidad in tipos.most_common():
            logger.info("  %d x %s", cantidad, tipo)
    if args.dry_run:
        logger.info("\n(--dry-run: no se escribió nada en la BD)")


if __name__ == "__main__":
    main()
