from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # ERP GI_LX (solo lectura)
    erp_db_server: str
    erp_db_name: str
    erp_db_user: str
    erp_db_password: str
    erp_db_driver: str = "ODBC Driver 17 for SQL Server"

    # LIMSS (lectura/escritura)
    limss_db_server: str
    limss_db_name: str
    limss_db_user: str
    limss_db_password: str
    limss_db_driver: str = "ODBC Driver 17 for SQL Server"

    # eBR (solo lectura -- lotes internos de Granel/Semi-Elaborado/Producto Terminado)
    ebr_db_server: str
    ebr_db_name: str = "eBR_Veterinario"
    ebr_db_user: str
    ebr_db_password: str
    ebr_db_driver: str = "ODBC Driver 17 for SQL Server"

    # JWT
    jwt_secret_key: str
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 480

    # Sesión
    session_timeout_minutes: int = 10

    # Storage de archivos (PDFs de testigos, protocolos, etc.)
    storage_path: str = r"\\LAMARSERVER\LIMSS\storage"

    # App
    app_name: str = "LIMSS Laboratorio Lamar"
    app_env: str = "development"
    app_host: str = "0.0.0.0"
    app_port: int = 8002
    allowed_origins: str = "http://localhost:5174"

    @property
    def allowed_origins_list(self) -> list[str]:
        return [o.strip() for o in self.allowed_origins.split(",")]

    class Config:
        env_file = ".env"
        case_sensitive = False


@lru_cache()
def get_settings() -> Settings:
    return Settings()
