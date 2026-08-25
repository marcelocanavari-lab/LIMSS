# -*- coding: utf-8 -*-
"""
backfill_numero_analisis.py
============================
Corrida única: numera con lims_muestras.numero_analisis las muestras YA
EXISTENTES de Materia Prima / Material de Empaque (erp_codsar de su
especificación -- ver app.services.erp_materiales) que todavía no tienen
número asignado, en ORDEN CRONOLÓGICO real (COALESCE(fecha_ingreso de la
solicitud, fecha_muestreo de la muestra), con id_muestra como desempate
final) -- no el orden en que se corra el script.

Usa el mismo contador dedicado que la asignación en caliente
(lims_contador_numero_analisis, con ROWLOCK/XLOCK, ver
asignar_numero_analisis_si_corresponde en app.services.erp_materiales) para
que el backfill y las creaciones nuevas nunca colisionen: se numera una
muestra por vez, avanzando el contador, en vez de calcular los números en
memoria y volcarlos todos juntos al final.

Usa app.db.connections (mismo .env que el resto del backend -- LIMSS_DEV o
LIMSS según en qué carpeta se corra), no una conexión propia, para no
duplicar credenciales ni arriesgar apuntar al entorno equivocado.

Uso, parado en backend/:
    venv\\Scripts\\python.exe Scripts\\backfill_numero_analisis.py
    venv\\Scripts\\python.exe Scripts\\backfill_numero_analisis.py --dry-run
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db.connections import get_limss_conn
from app.services.erp_materiales import (
    obtener_codsar_por_tipo,
    obtener_codsars_material_empaque,
    tiene_numero_analisis,
)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="Solo muestra qué se numeraría, no escribe en la BD")
    args = parser.parse_args()

    with get_limss_conn() as conn:
        cursor = conn.cursor()

        if not tiene_numero_analisis(cursor):
            print("lims_muestras.numero_analisis / lims_contador_numero_analisis no existen todavía en este entorno -- abortando.")
            return

        codsar_materia_prima = obtener_codsar_por_tipo(conn).get("materia_prima")
        codsars_empaque = obtener_codsars_material_empaque(conn)
        codsares = [c for c in [codsar_materia_prima, *codsars_empaque] if c]
        print(f"CODSAR considerados Materia Prima/Material de Empaque: {codsares}")

        placeholders = ",".join("?" * len(codsares))
        cursor.execute(
            f"""
            SELECT m.id_muestra, m.codigo_muestra, e.erp_codsar,
                   s.fecha_ingreso, m.fecha_muestreo
            FROM lims_muestras m
            INNER JOIN lims_especificaciones e ON e.id_especificacion = m.id_especificacion
            LEFT JOIN lims_solicitudes_muestreo s ON s.id_muestra = m.id_muestra
            WHERE e.erp_codsar IN ({placeholders})
              AND m.numero_analisis IS NULL
            ORDER BY COALESCE(s.fecha_ingreso, m.fecha_muestreo), m.id_muestra
            """,
            *codsares,
        )
        pendientes = cursor.fetchall()
        print(f"Muestras de Materia Prima/Material de Empaque sin numero_analisis: {len(pendientes)}")

        numerados = 0
        for m in pendientes:
            fecha_orden = m.fecha_ingreso or m.fecha_muestreo
            if not args.dry_run:
                cursor.execute(
                    "UPDATE lims_contador_numero_analisis WITH (ROWLOCK, XLOCK) SET ultimo_valor = ultimo_valor + 1 WHERE id = 1"
                )
                cursor.execute("SELECT ultimo_valor FROM lims_contador_numero_analisis WHERE id = 1")
                numero_analisis = cursor.fetchone().ultimo_valor
                cursor.execute(
                    "UPDATE lims_muestras SET numero_analisis = ? WHERE id_muestra = ?",
                    numero_analisis, m.id_muestra,
                )
            else:
                numero_analisis = "(dry-run)"
            print(f"  [{numero_analisis}] id_muestra={m.id_muestra} {m.codigo_muestra} codsar={m.erp_codsar.strip()} fecha_orden={fecha_orden}")
            numerados += 1

        if not args.dry_run:
            conn.commit()

    print(f"\nNumeradas: {numerados}/{len(pendientes)}")
    if args.dry_run:
        print("\n(--dry-run: no se escribió nada en la BD)")


if __name__ == "__main__":
    main()
