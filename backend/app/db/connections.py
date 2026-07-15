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


# --- FastAPI dependency ---
def erp_db():
    with get_erp_conn() as conn:
        yield conn


def ebr_db():
    with get_ebr_conn() as conn:
        yield conn


def limss_db():
    with get_limss_conn() as conn:
        yield conn
