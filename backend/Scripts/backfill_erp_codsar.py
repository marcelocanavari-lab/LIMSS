# -*- coding: utf-8 -*-
"""
backfill_erp_codsar.py
=======================
Corrida única: recorre las especificaciones con erp_codsar IS NULL, resuelve
el subarticulo (CODSAR) de cada una contra el ERP por su erp_CODART (mismo
JOIN GIM21ART -> GIT59SAR que usa erp_ir.py, ver
app.services.erp_ir.resolver_codsar_por_codart) y actualiza la columna.

No frena ante un erp_CODART que no se encuentra en el ERP (dato de prueba,
artículo discontinuado) -- lo loguea y sigue con el resto.

Usa app.db.connections (mismo .env que el resto del backend -- LIMSS_DEV o
LIMSS según en qué carpeta se corra), no una conexión propia, para no
duplicar credenciales ni arriesgar apuntar al entorno equivocado.

Uso, parado en backend/:
    venv\\Scripts\\python.exe Scripts\\backfill_erp_codsar.py
    venv\\Scripts\\python.exe Scripts\\backfill_erp_codsar.py --dry-run
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db.connections import get_erp_conn, get_limss_conn
from app.services.erp_ir import resolver_codsar_por_codart


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="Solo muestra qué se resolvería, no escribe en la BD")
    args = parser.parse_args()

    resueltos = 0
    no_encontrados = []

    with get_limss_conn() as conn, get_erp_conn() as erp:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id_especificacion, erp_CODART, erp_DESART FROM lims_especificaciones WHERE erp_codsar IS NULL"
        )
        pendientes = cursor.fetchall()
        print(f"Especificaciones con erp_codsar pendiente: {len(pendientes)}")

        for espec in pendientes:
            codsar = resolver_codsar_por_codart(erp, espec.erp_CODART)
            if codsar is None:
                no_encontrados.append((espec.id_especificacion, espec.erp_CODART.strip(), espec.erp_DESART))
                print(f"  [SIN RESOLVER] id={espec.id_especificacion} erp_CODART='{espec.erp_CODART.strip()}' ({espec.erp_DESART})")
                continue

            print(f"  [OK] id={espec.id_especificacion} erp_CODART='{espec.erp_CODART.strip()}' -> erp_codsar='{codsar}'")
            if not args.dry_run:
                cursor.execute(
                    "UPDATE lims_especificaciones SET erp_codsar = ? WHERE id_especificacion = ?",
                    codsar, espec.id_especificacion,
                )
            resueltos += 1

        if not args.dry_run:
            conn.commit()

    print(f"\nResueltos: {resueltos}/{len(pendientes)}")
    if no_encontrados:
        print(f"Sin resolver ({len(no_encontrados)}) -- erp_CODART no encontrado en el ERP:")
        for id_esp, codart, desart in no_encontrados:
            print(f"  id_especificacion={id_esp}  erp_CODART='{codart}'  ({desart})")
    if args.dry_run:
        print("\n(--dry-run: no se escribió nada en la BD)")


if __name__ == "__main__":
    main()
