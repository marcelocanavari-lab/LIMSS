"""
Gestión de conexiones a las tres bases de datos:
  - ERP (GI_LX):        SQL Server - SOLO LECTURA
  - eBR (Veterinario):  SQL Server - SOLO LECTURA (lotes internos)
  - LIMSS:              SQL Server - lectura/escritura
"""
import pyodbc
from contextlib import contextmanager
from typing import Generator
from app.core.config import get_settings

settings = get_settings()


def _build_conn_string(server: str, db: str, user: str, password: str, driver: str) -> str:
    return (
        f"DRIVER={{{driver}}};"
        f"SERVER={server};"
        f"DATABASE={db};"
        f"UID={user};"
        f"PWD={password};"
        f"TrustServerCertificate=yes;"
    )


ERP_CONN_STR = _build_conn_string(
    settings.erp_db_server, settings.erp_db_name,
    settings.erp_db_user, settings.erp_db_password, settings.erp_db_driver,
)

# Login limss_erp -- mismo server/base que ERP_CONN_STR (GI_LX), pero con
# permiso de UPDATE acotado sobre GIT30NUM.NUMCOM/ULTFEC (ver investigación
# de asignación manual de IR). Cadena separada a propósito: nunca se usa
# para nada más que asignar_ir_manual, así que un bug en otro lado no puede
# terminar escribiendo al ERP por accidente con este login de más permisos.
ERP_WRITE_CONN_STR = _build_conn_string(
    settings.erp_db_server, settings.erp_db_name,
    settings.erp_write_db_user, settings.erp_write_db_password, settings.erp_db_driver,
)

EBR_CONN_STR = _build_conn_string(
    settings.ebr_db_server, settings.ebr_db_name,
    settings.ebr_db_user, settings.ebr_db_password, settings.ebr_db_driver,
)

LIMSS_CONN_STR = _build_conn_string(
    settings.limss_db_server, settings.limss_db_name,
    settings.limss_db_user, settings.limss_db_password, settings.limss_db_driver,
)


@contextmanager
def get_erp_conn() -> Generator[pyodbc.Connection, None, None]:
    """Conexión al ERP GI_LX - SOLO LECTURA. Nunca ejecutar INSERT/UPDATE/DELETE."""
    conn = pyodbc.connect(ERP_CONN_STR, readonly=True)
    try:
        yield conn
    finally:
        conn.close()


@contextmanager
def get_ebr_conn() -> Generator[pyodbc.Connection, None, None]:
    """Conexión a la BD del eBR - SOLO LECTURA. Nunca ejecutar INSERT/UPDATE/DELETE."""
    conn = pyodbc.connect(EBR_CONN_STR, readonly=True)
    try:
        yield conn
    finally:
        conn.close()


@contextmanager
def get_limss_conn() -> Generator[pyodbc.Connection, None, None]:
    """Conexión a la BD LIMSS - lectura y escritura."""
    conn = pyodbc.connect(LIMSS_CONN_STR)
    conn.autocommit = False
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


@contextmanager
def get_erp_write_conn() -> Generator[pyodbc.Connection, None, None]:
    """Conexión al ERP GI_LX con el login limss_erp -- ÚNICAMENTE para
    asignar_ir_manual (UPDATE acotado sobre GIT30NUM.NUMCOM/ULTFEC). No usar
    para nada más: el resto del sistema sigue leyendo el ERP con
    get_erp_conn/ebr_readonly (solo lectura).

    autocommit=False + commit al final del `with` (mismo patrón que
    get_limss_conn, a diferencia de get_erp_conn que es puramente de
    lectura): si algo después de la escritura al ERP falla (p.ej. el UPDATE
    a lims_testigos o el audit.registrar en LIMSS), FastAPI cierra esta
    dependencia por la excepción ANTES de llegar a este commit -- entra por
    el except de abajo y hace rollback, así el contador de GIT30NUM no
    queda incrementado sin que se haya guardado nada del lado de LIMSS."""
    conn = pyodbc.connect(ERP_WRITE_CONN_STR)
    conn.autocommit = False
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# --- FastAPI dependency ---
def erp_db():
    with get_erp_conn() as conn:
        yield conn


def erp_write_db():
    with get_erp_write_conn() as conn:
        yield conn


def ebr_db():
    with get_ebr_conn() as conn:
        yield conn


def limss_db():
    with get_limss_conn() as conn:
        yield conn
