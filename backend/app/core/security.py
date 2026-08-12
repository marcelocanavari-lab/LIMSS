"""
Módulo de seguridad:
  - Hash/verificación de PIN con bcrypt directo
  - Generación y validación de JWT
  - Dependencia FastAPI: get_current_user
"""
from datetime import datetime, timedelta, timezone
from typing import Optional
import bcrypt as _bcrypt
import pyodbc
from fastapi import Depends, Header, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt

from app.core.config import get_settings
from app.db.connections import limss_db

settings = get_settings()
bearer_scheme = HTTPBearer()


# ── PIN ────────────────────────────────────────────

def hash_pin(pin: str) -> str:
    return _bcrypt.hashpw(pin.encode("utf-8"), _bcrypt.gensalt(rounds=12)).decode("utf-8")


def verify_pin(pin: str, hashed: str) -> bool:
    return _bcrypt.checkpw(pin.encode("utf-8"), hashed.encode("utf-8"))


# ── JWT ──────────────────────────────────────────────────────

def create_access_token(data: dict, expires_minutes: Optional[int] = None) -> str:
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=expires_minutes or settings.jwt_expire_minutes
    )
    payload = {**data, "exp": expire, "iat": datetime.now(timezone.utc)}
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token inválido o expirado",
            headers={"WWW-Authenticate": "Bearer"},
        )


# ── Dependencia FastAPI ───────────────────────────────────────

def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    conn: pyodbc.Connection = Depends(limss_db),
) -> dict:
    payload = decode_token(credentials.credentials)
    id_usuario = payload.get("sub")
    if not id_usuario:
        raise HTTPException(status_code=401, detail="Token sin usuario")

    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT u.id_usuario, u.codigo, u.nombre, u.apellido, u.rol, u.activo, u.debe_cambiar_pin,
               s.id_sesion, s.fecha_expira
        FROM lims_usuarios u
        JOIN lims_sesiones s ON s.id_usuario = u.id_usuario
        WHERE u.id_usuario = ?
          AND s.token = ?
          AND s.fecha_cierre IS NULL
          AND s.fecha_expira > GETDATE()
        """,
        int(id_usuario),
        credentials.credentials,
    )
    row = cursor.fetchone()
    if not row:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Sesión expirada. Volvé a ingresar tu PIN.",
        )
    if not row.activo:
        raise HTTPException(status_code=403, detail="Usuario inactivo")

    return {
        "id_usuario": row.id_usuario,
        "codigo": row.codigo,
        "nombre": row.nombre,
        "apellido": row.apellido,
        "rol": row.rol,
        "id_sesion": row.id_sesion,
        "token": credentials.credentials,
        "debe_cambiar_pin": bool(row.debe_cambiar_pin),
    }


def verificar_acceso_ebr(
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
    authorization: Optional[str] = Header(None),
    conn: pyodbc.Connection = Depends(limss_db),
) -> None:
    """Acceso al endpoint de sincronización de usuarios del eBR (sistema
    externo, sin sesión LIMSS propia): acepta la API key fija configurada
    en EBR_SYNC_API_KEY, o -- para poder probar el endpoint como admin
    logueado -- el mismo bearer token que usa el resto de la API."""
    if settings.ebr_sync_api_key and x_api_key == settings.ebr_sync_api_key:
        return

    if authorization and authorization.lower().startswith("bearer "):
        token = authorization.split(" ", 1)[1]
        payload = decode_token(token)
        id_usuario = payload.get("sub")
        if id_usuario:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT 1
                FROM lims_usuarios u
                JOIN lims_sesiones s ON s.id_usuario = u.id_usuario
                WHERE u.id_usuario = ?
                  AND s.token = ?
                  AND s.fecha_cierre IS NULL
                  AND s.fecha_expira > GETDATE()
                  AND u.activo = 1
                """,
                int(id_usuario),
                token,
            )
            if cursor.fetchone():
                return

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="No autorizado: se requiere API key (X-API-Key) o un token válido",
    )


def require_rol(*roles: str):
    """Dependencia que exige uno de los roles indicados."""
    def checker(user: dict = Depends(get_current_user)):
        if user["rol"] not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Se requiere rol: {', '.join(roles)}",
            )
        return user
    return checker
