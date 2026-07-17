# -*- coding: utf-8 -*-
"""
importar_especificaciones_pt.py
Importa especificaciones de Producto Terminado al LIMSS.
"""

import os, sys, re, subprocess, argparse, logging
from datetime import datetime
from pathlib import Path

CONFIG = {
    "db_server":   "Lamarserver",
    "db_name":     "LIMSS",
    "db_user":     "limss_app",
    "db_password": "Limss2024#",       # ← cambiar
    "db_driver":   "SQL Server",
    "id_usuario_carga": 1,                   # ← ID del usuario admin en lims_usuarios
    "tipo_material":    "producto_terminado",
}

def setup_logging(carpeta_log):
    log_file = carpeta_log / f"importacion_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(levelname)-8s  %(message)s",
        handlers=[
            logging.FileHandler(log_file, encoding="utf-8"),
            logging.StreamHandler(sys.stdout),
        ],
    )
    return log_file

def limpiar(texto):
    if not texto: return ""
    return " ".join(texto.strip().split())

def parsear_documento(docx_path):
    try:
        from docx import Document
    except ImportError:
        logging.error("  python-docx no instalado.")
        return None
    try:
        doc = Document(docx_path)
    except Exception as e:
        logging.error(f"  No se pudo abrir {docx_path.name}: {e}")
        return None

    # Leer header
    header_texts = []
    for section in doc.sections:
        for t in section.header.tables:
            for row in t.rows:
                for cell in row.cells:
                    txt = cell.text.strip()
                    if txt:
                        header_texts.append(txt)
        break

    codigo = nombre = tipo_mp = accion = ""
    for txt in header_texts:
        txt_clean = txt.replace('\n', ' ').strip()
        # Codigo PT: C.digo matchea Código con o sin tilde
        m = re.search(r'C.digo\s*:\s*(PT\d{3})', txt_clean, re.IGNORECASE)
        if m:
            codigo = m.group(1).strip()
        # Nombre
        m2 = re.search(r'Especificaciones de producto terminado\s*(.+)', txt_clean, re.IGNORECASE | re.DOTALL)
        if m2:
            nombre = limpiar(m2.group(1).replace('\n', ' '))
        # Actividad
        m4 = re.search(r'Actividad del Producto\s*:\s*(.+)', txt_clean, re.IGNORECASE)
        if m4:
            accion = limpiar(m4.group(1))

    if not codigo:
        logging.error(f"  No se pudo extraer el codigo PT de {docx_path.name}")
        return None

    # Leer cuerpo del documento
    texto_completo = []
    tablas_cuerpo = []
    for element in doc.element.body:
        from docx.oxml.ns import qn
        if element.tag == qn('w:p'):
            from docx.text.paragraph import Paragraph
            p = Paragraph(element, doc)
            if p.text.strip():
                texto_completo.append(p.text.strip())
        elif element.tag == qn('w:tbl'):
            from docx.table import Table
            t = Table(element, doc)
            rows_data = []
            for row in t.rows:
                rows_data.append([cell.text.strip() for cell in row.cells])
            tablas_cuerpo.append(rows_data)

    texto = "\n".join(texto_completo)

    # Extraer campos de caracteristicas de los parrafos
    envasado = ""
    for line in texto_completo:
        m = re.search(r'Condici[oó]nes? de almacenamiento\s*[:\-]\s*(.+)', line, re.IGNORECASE)
        if m:
            envasado = limpiar(m.group(1))

    # Ensayos de las tablas
    ensayos = []
    HEADERS = {'ensayo', 'determinacion', 'determinaciones'}
    for tabla in tablas_cuerpo:
        if not tabla:
            continue
        primera = [c.lower().strip() for c in tabla[0]]
        if not any(h in ' '.join(primera) for h in HEADERS):
            continue
        for fila in tabla[1:]:
            if len(fila) < 2:
                continue
            nombre_e = limpiar(fila[0])
            espec    = limpiar(fila[1]) if len(fila) > 1 else ""
            tecnica  = limpiar(fila[2]) if len(fila) > 2 else ""
            biblio   = limpiar(fila[3]) if len(fila) > 3 else ""
            if nombre_e and not re.match(r'^(ENSAYO|DETERMINACI)', nombre_e, re.IGNORECASE):
                ensayos.append({
                    "nombre_ensayo":  nombre_e,
                    "especificacion": espec,
                    "tecnica":        tecnica,
                    "bibliografia":   biblio,
                })

    return {
        "codigo":              codigo,
        "nombre":              nombre,
        "tipo_mp":             "",
        "accion_terapeutica":  accion,
        "sinonimia":           "",
        "nro_cas":             "",
        "nombre_quimico":      "",
        "formula_molecular":   "",
        "peso_molecular":      "",
        "envasado_almacenamiento": envasado,
        "ensayos":             ensayos,
    }

def insertar_en_bd(datos, conn):
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id_especificacion FROM lims_especificaciones WHERE erp_CODART = ?",
        datos["codigo"]
    )
    if cursor.fetchone():
        logging.info(f"  Ya existe — saltando.")
        return False

    cursor.execute(
        """
        INSERT INTO lims_especificaciones
            (erp_IdM21, erp_CODART, erp_DESART, tipo_material, version, vigente,
             tipo_mp, accion_terapeutica, sinonimia, nro_cas, nombre_quimico,
             formula_molecular, peso_molecular, envasado_almacenamiento, id_usuario_carga)
        VALUES (0, ?, ?, ?, '1.0', 1, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        datos["codigo"][:20],
        datos["nombre"][:100],
        CONFIG["tipo_material"][:20],
        datos["tipo_mp"][:50],
        datos["accion_terapeutica"][:500],
        datos["sinonimia"][:1000],
        datos["nro_cas"][:50],
        datos["nombre_quimico"][:2000],
        datos["formula_molecular"][:100],
        datos["peso_molecular"][:100],
        datos["envasado_almacenamiento"][:2000],
        CONFIG["id_usuario_carga"],
    )
    cursor.execute("SELECT @@IDENTITY AS id")
    id_especificacion = int(cursor.fetchone().id)

    for orden, ensayo in enumerate(datos["ensayos"], start=1):
        cursor.execute(
            """
            INSERT INTO lims_ensayos
                (id_especificacion, orden, nombre_ensayo, metodologia,
                 tipo_dato, valor_requerido, bibliografia, especificacion_texto, obligatorio)
            VALUES (?, ?, ?, ?, 'cualitativo', ?, ?, ?, 1)
            """,
            id_especificacion, orden,
            ensayo["nombre_ensayo"][:300],
            ensayo["tecnica"][:500],
            ensayo["especificacion"][:2000],
            ensayo["bibliografia"][:500],
            ensayo["especificacion"][:2000],
        )

    conn.commit()
    return True

def main():
    parser = argparse.ArgumentParser(description="Importar especificaciones PT al LIMSS")
    parser.add_argument("--carpeta", required=True)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    carpeta = Path(args.carpeta)
    if not carpeta.exists():
        print(f"ERROR: La carpeta '{carpeta}' no existe.")
        sys.exit(1)

    log_file = setup_logging(carpeta)
    archivos = sorted(list(carpeta.glob("*.docx")))
    archivos = [f for f in archivos if not f.name.startswith('~')]

    logging.info(f"Carpeta: {carpeta}")
    logging.info(f"Archivos encontrados: {len(archivos)}")
    logging.info(f"Modo: {'DRY RUN' if args.dry_run else 'INSERCION EN BD'}")
    logging.info("=" * 60)

    conn = None
    if not args.dry_run:
        try:
            import pyodbc
            cs = (f"DRIVER={{{CONFIG['db_driver']}}};"
                  f"SERVER={CONFIG['db_server']};"
                  f"DATABASE={CONFIG['db_name']};"
                  f"UID={CONFIG['db_user']};"
                  f"PWD={CONFIG['db_password']};"
                  f"TrustServerCertificate=yes;")
            conn = pyodbc.connect(cs, autocommit=False)
            logging.info("Conexion a BD LIMSS OK")
        except Exception as e:
            logging.error(f"No se pudo conectar: {e}")
            sys.exit(1)

    ok = saltados = errores = 0

    for archivo in archivos:
        logging.info(f"\n-> {archivo.name}")
        datos = parsear_documento(archivo)
        if not datos:
            errores += 1
            continue

        logging.info(f"  Codigo:  {datos['codigo']}")
        logging.info(f"  Nombre:  {datos['nombre']}")
        logging.info(f"  Ensayos: {len(datos['ensayos'])}")
        for e in datos["ensayos"]:
            logging.info(f"    - {e['nombre_ensayo']}")

        if args.dry_run:
            ok += 1
            continue

        try:
            if insertar_en_bd(datos, conn):
                logging.info(f"  Insertado OK")
                ok += 1
            else:
                saltados += 1
        except Exception as e:
            logging.error(f"  Error al insertar: {e}")
            conn.rollback()
            errores += 1

    if conn:
        conn.close()

    logging.info("\n" + "=" * 60)
    logging.info("RESUMEN FINAL")
    logging.info(f"  Insertados: {ok}")
    logging.info(f"  Saltados:   {saltados}")
    logging.info(f"  Errores:    {errores}")
    logging.info("=" * 60)

if __name__ == "__main__":
    main()
