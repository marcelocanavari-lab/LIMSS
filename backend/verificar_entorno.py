"""
Verificacion rapida de entorno para el backend de LIMSS / LIMSS_DEV.

Corre en segundos y chequea de una sola vez los puntos que mas tiempo
hicieron perder en el pasado: variables de entorno faltantes o vacias,
Python que no puede lanzar subprocesos, Tesseract no encontrado o en
otra maquina, conexion a la base caida, rama de git inesperada para la
carpeta, o estar parado en una ruta de red en vez de local.

No reemplaza a Docker -- es un chequeo manual rapido para este esquema
de despliegue actual (carpetas separadas + .env por entorno). Correrlo
cada vez que se arma un entorno nuevo, o cuando algo "no anda" y no se
sabe por donde empezar.

Uso: parado en la carpeta backend/ (de LIMSS o de LIMSS_DEV), correr:
    C:\\Python312-embed\\python.exe verificar_entorno.py
"""
import os
import subprocess
import sys
from pathlib import Path

OK = "[OK]"
FALLO = "[FALLA]"
AVISO = "[AVISO]"


def seccion(titulo):
    print(f"\n--- {titulo} ---")


def leer_env(path):
    valores = {}
    if not path.exists():
        return valores
    for linea_txt in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        linea_txt = linea_txt.strip()
        if not linea_txt or linea_txt.startswith("#") or "=" not in linea_txt:
            continue
        clave, _, valor = linea_txt.partition("=")
        valores[clave.strip()] = valor.strip().strip('"').strip("'")
    return valores


def main():
    errores = 0
    avisos = 0
    cwd = Path.cwd()

    seccion("Ubicacion")
    print(f"Carpeta actual: {cwd}")
    es_ruta_red = str(cwd).startswith("\\\\") or (len(str(cwd)) >= 2 and str(cwd)[1] != ":")
    if not es_ruta_red:
        # Puede ser una unidad de red MAPEADA (ej. Y:), que a simple
        # vista tiene la misma forma que una unidad local (letra + ":").
        # Consultar "net use" para confirmar si la letra actual esta
        # mapeada a una ruta \\servidor\... antes de decir "local".
        try:
            r = subprocess.run(["net", "use"], capture_output=True, text=True, timeout=5)
            letra_actual = str(cwd)[:2].upper()  # ej. "Y:"
            for linea_salida in r.stdout.splitlines():
                if letra_actual in linea_salida.upper() and "\\\\" in linea_salida:
                    es_ruta_red = True
                    break
        except Exception:
            pass  # si "net use" falla, seguir con el chequeo simple de arriba
    if es_ruta_red:
        print(f"{FALLO} Es una unidad de RED (mapeada o UNC), no local.")
        print("        Correr desde una ruta tipo C:\\... para evitar corrupcion de dependencias.")
        errores += 1
    else:
        print(f"{OK} Ruta local.")

    seccion("Archivo .env")
    env_path = cwd / ".env"
    env_example_path = cwd / ".env.example"
    valores = leer_env(env_path)
    ejemplo = leer_env(env_example_path)
    if not env_path.exists():
        print(f"{FALLO} No existe .env en esta carpeta ({env_path}).")
        errores += 1
    else:
        print(f"{OK} .env encontrado, {len(valores)} variables leidas.")
        if ejemplo:
            faltantes = [k for k in ejemplo if k not in valores or not valores[k]]
            if faltantes:
                print(f"{AVISO} Variables presentes en .env.example pero vacias o ausentes en .env:")
                for f in faltantes:
                    print(f"         - {f}")
                avisos += len(faltantes)
            else:
                print(f"{OK} Todas las variables de .env.example estan presentes con valor en .env.")
        else:
            print(f"{AVISO} No se encontro .env.example para comparar -- no se puede detectar variables faltantes.")
            avisos += 1

    seccion("Subprocess (necesario para OCR de Material de Empaque)")
    try:
        r = subprocess.run(["cmd.exe", "/c", "echo ok"], capture_output=True, timeout=5)
        if r.returncode == 0:
            print(f"{OK} Este Python puede lanzar procesos hijos.")
        else:
            print(f"{FALLO} subprocess devolvio codigo {r.returncode}.")
            errores += 1
    except Exception as e:
        print(f"{FALLO} No se pudo lanzar un proceso hijo: {e}")
        errores += 1

    seccion("Tesseract (comparacion de etiquetas)")
    tpath = valores.get("TESSERACT_PATH", "")
    if not tpath:
        print(f"{AVISO} TESSERACT_PATH no esta configurada en .env.")
        print("        La comparacion de etiquetas de Material de Empaque no va a funcionar (modo degradado, no bloquea nada).")
        avisos += 1
    elif not Path(tpath).exists():
        print(f"{FALLO} TESSERACT_PATH apunta a '{tpath}', pero ese archivo no existe en ESTA maquina.")
        print("        (causa mas probable: Tesseract se instalo en otra maquina, no en este servidor)")
        errores += 1
    else:
        try:
            r = subprocess.run([tpath, "--version"], capture_output=True, timeout=10)
            if r.returncode == 0:
                print(f"{OK} Tesseract responde correctamente en la ruta configurada.")
            else:
                print(f"{FALLO} Tesseract existe pero devolvio error al ejecutarlo.")
                errores += 1
        except Exception as e:
            print(f"{FALLO} No se pudo ejecutar Tesseract: {e}")
            errores += 1

    seccion("API key de Claude")
    if not valores.get("ANTHROPIC_API_KEY"):
        print(f"{AVISO} ANTHROPIC_API_KEY no configurada.")
        print("        El agente de muestreo y la comparacion con IA funcionan en modo degradado (no bloquea nada), pero sin usar IA de verdad.")
        avisos += 1
    else:
        print(f"{OK} ANTHROPIC_API_KEY presente.")

    seccion("Base de datos")
    try:
        import pyodbc
        posibles_server = ["LIMSS_DB_SERVER", "DB_SERVER", "SQL_SERVER"]
        posibles_db = ["LIMSS_DB_NAME", "DB_NAME", "SQL_DATABASE"]
        posibles_user = ["LIMSS_DB_USER", "DB_USER", "SQL_USER"]
        posibles_pwd = ["LIMSS_DB_PASSWORD", "DB_PASSWORD", "SQL_PASSWORD"]

        def primero(claves):
            for c in claves:
                if valores.get(c):
                    return valores[c]
            return None

        server = primero(posibles_server)
        db = primero(posibles_db)
        user = primero(posibles_user)
        pwd = primero(posibles_pwd)

        if not all([server, db, user, pwd]):
            print(f"{AVISO} No se encontraron todas las variables de conexion esperadas en .env.")
            print("        (este chequeo prueba varios nombres comunes -- si el proyecto usa otros nombres de variable,")
            print("         ajustar las listas 'posibles_*' al principio de esta seccion del script)")
            avisos += 1
        else:
            drivers_a_probar = [
                "ODBC Driver 18 for SQL Server",
                "ODBC Driver 17 for SQL Server",
                "SQL Server Native Client 11.0",
                "SQL Server",
            ]
            drivers_instalados = [d for d in pyodbc.drivers()]
            conectado = False
            ultimo_error = None
            for drv in drivers_a_probar:
                if drv not in drivers_instalados:
                    continue
                try:
                    conn_str = f"DRIVER={{{drv}}};SERVER={server};DATABASE={db};UID={user};PWD={pwd}"
                    conn = pyodbc.connect(conn_str, timeout=5)
                    conn.close()
                    print(f"{OK} Conexion a la base '{db}' en '{server}' exitosa (driver: {drv}).")
                    conectado = True
                    break
                except Exception as e:
                    ultimo_error = e
                    continue
            if not conectado:
                if not any(d in drivers_instalados for d in drivers_a_probar):
                    print(f"{AVISO} Ninguno de los drivers ODBC esperados esta instalado en este Python.")
                    print(f"        Drivers disponibles: {drivers_instalados or '(ninguno)'}")
                    print("        Esto no significa que la base este caida -- puede que el backend real use pyodbc de otro entorno.")
                    avisos += 1
                else:
                    print(f"{FALLO} No se pudo conectar a la base: {ultimo_error}")
                    errores += 1
    except ImportError:
        print(f"{AVISO} pyodbc no esta instalado en este Python -- no se pudo probar la conexion a la base.")
        avisos += 1
    except Exception as e:
        print(f"{FALLO} No se pudo conectar a la base: {e}")
        errores += 1

    seccion("Git")
    try:
        r = subprocess.run(
            ["git", "branch", "--show-current"],
            capture_output=True, text=True, cwd=cwd.parent, timeout=5,
        )
        rama = r.stdout.strip()
        if rama:
            print(f"Rama actual: {rama}")
            es_carpeta_dev = "DEV" in str(cwd).upper()
            if es_carpeta_dev and rama != "dev":
                print(f"{AVISO} Esta carpeta parece ser de DESARROLLO pero la rama activa es '{rama}', no 'dev'.")
                avisos += 1
            elif not es_carpeta_dev and rama != "main":
                print(f"{AVISO} Esta carpeta parece ser de PRODUCCION pero la rama activa es '{rama}', no 'main'.")
                avisos += 1
            else:
                print(f"{OK} La rama coincide con lo esperado para esta carpeta.")
        else:
            print(f"{AVISO} No se pudo determinar la rama de git (¿la carpeta no es un repo git?).")
            avisos += 1
    except FileNotFoundError:
        print(f"{AVISO} git no esta disponible en el PATH -- no se pudo verificar la rama.")
        avisos += 1
    except Exception as e:
        print(f"{AVISO} Error verificando git: {e}")
        avisos += 1

    seccion("Resumen")
    print(f"Errores: {errores}  |  Avisos: {avisos}")
    if errores == 0 and avisos == 0:
        print("Todo en orden.")
    elif errores == 0:
        print("Sin errores criticos, pero revisar los avisos de arriba.")
    else:
        print("Hay errores que probablemente causen fallas reales -- revisar antes de dar por buena esta corrida.")

    sys.exit(1 if errores else 0)


if __name__ == "__main__":
    main()
