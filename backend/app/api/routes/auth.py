"""
Rutas de autenticación
POST /api/auth/login   → valida código + PIN, devuelve JWT
POST /api/auth/logout  → cierra la sesión activa
GET  /api/auth/me      → datos del usuario autenticado
"""
from datetime import datetime, timedelta, timezone
import pyodbc
from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.core.config import get_settings
from app.core.security import hash_pin, verify_pin, create_access_token, get_current_user
from app.db.connections import limss_db
from app.schemas.auth import (
    LoginRequest, LoginResponse, UsuarioCreate, UsuarioResponse,
)
from app.services import audit

router = APIRouter(prefix="/api/auth", tags=["Autenticación"])
settings = get_settings()


@router.post("/login", response_model=LoginResponse)
def login(body: LoginRequest, request: Request, conn: pyodbc.Connection = Depends(limss_db)):
    # 1. Buscar usuario activo
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT id_usuario, codigo, nombre, apellido, pin_hash, rol, activo
        FROM lims_usuarios
        WHERE codigo = ? AND activo = 1
        """,
        body.codigo,
    )
    row = cursor.fetchone()

    if not row or not verify_pin(body.pin, row.pin_hash):
        # Audit trail del intento fallido
        audit.registrar(
            conn,
            entidad="sesion",
            accion="login_fallido",
            valor_nuevo={"codigo": body.codigo},
            ip_origen=request.client.host if request.client else None,
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Código o PIN incorrecto",
        )

    # 2. Crear token JWT
    expire_minutes = settings.jwt_expire_minutes
    token = create_access_token(
        data={"sub": str(row.id_usuario), "rol": row.rol},
        expires_minutes=expire_minutes,
    )
    fecha_expira = datetime.now(timezone.utc) + timedelta(minutes=expire_minutes)

    # 3. Registrar sesión en lims_sesiones
    dispositivo = request.headers.get("user-agent", "")[:200]
    ip = request.client.host if request.client else None

    cursor.execute(
        """
        INSERT INTO lims_sesiones
            (id_usuario, token, ip_origen, dispositivo, fecha_inicio, fecha_expira)
        VALUES (?, ?, ?, ?, GETDATE(), ?)
        """,
        row.id_usuario,
        token,
        ip,
        dispositivo,
        fecha_expira,
    )
    cursor.execute("SELECT @@IDENTITY AS id_sesion")
    id_sesion = int(cursor.fetchone().id_sesion)

    # 4. Actualizar último login
    cursor.execute(
        "UPDATE lims_usuarios SET ultimo_login = GETDATE() WHERE id_usuario = ?",
        row.id_usuario,
    )

    # 5. Audit trail
    audit.registrar(
        conn,
        entidad="sesion",
        accion="login",
        id_usuario=row.id_usuario,
        id_entidad=id_sesion,
        valor_nuevo={"rol": row.rol},
        ip_origen=ip,
    )

    return LoginResponse(
        access_token=token,
        id_usuario=row.id_usuario,
        nombre=row.nombre,
        apellido=row.apellido,
        rol=row.rol,
        expira_en_minutos=expire_minutes,
    )


@router.post("/logout", status_code=204)
def logout(
    request: Request,
    user: dict = Depends(get_current_user),
    conn: pyodbc.Connection = Depends(limss_db),
):
    cursor = conn.cursor()
    cursor.execute(
        """
        UPDATE lims_sesiones
        SET fecha_cierre = GETDATE(), motivo_cierre = 'logout'
        WHERE id_sesion = ?
        """,
        user["id_sesion"],
    )
    audit.registrar(
        conn,
        entidad="sesion",
        accion="logout",
        id_usuario=user["id_usuario"],
        id_entidad=user["id_sesion"],
        ip_origen=request.client.host if request.client else None,
    )


@router.get("/me")
def me(user: dict = Depends(get_current_user)):
    return {
        "id_usuario": user["id_usuario"],
        "codigo": user["codigo"],
        "nombre": user["nombre"],
        "apellido": user["apellido"],
        "rol": user["rol"],
    }


@router.post("/usuarios", response_model=UsuarioResponse, status_code=201)
def crear_usuario(
    body: UsuarioCreate,
    user: dict = Depends(get_current_user),
    conn: pyodbc.Connection = Depends(limss_db),
):
    """Solo admins pueden crear usuarios."""
    if user["rol"] != "admin":
        raise HTTPException(status_code=403, detail="Solo administradores pueden crear usuarios")

    cursor = conn.cursor()
    # Verificar que el código no exista
    cursor.execute("SELECT 1 FROM lims_usuarios WHERE codigo = ?", body.codigo)
    if cursor.fetchone():
        raise HTTPException(status_code=409, detail=f"El código '{body.codigo}' ya existe")

    pin_hash = hash_pin(body.pin)
    cursor.execute(
        """
        INSERT INTO lims_usuarios
            (codigo, nombre, apellido, pin_hash, rol)
        VALUES (?, ?, ?, ?, ?)
        """,
        body.codigo,
        body.nombre,
        body.apellido,
        pin_hash,
        body.rol,
    )
    cursor.execute("SELECT @@IDENTITY AS id")
    id_nuevo = int(cursor.fetchone().id)

    audit.registrar(
        conn,
        entidad="usuario",
        accion="crear",
        id_usuario=user["id_usuario"],
        id_entidad=id_nuevo,
        valor_nuevo={"codigo": body.codigo, "rol": body.rol},
    )

    cursor.execute(
        "SELECT * FROM lims_usuarios WHERE id_usuario = ?", id_nuevo
    )
    row = cursor.fetchone()
    return UsuarioResponse(
        id_usuario=row.id_usuario,
        codigo=row.codigo,
        nombre=row.nombre,
        apellido=row.apellido,
        rol=row.rol,
        activo=bool(row.activo),
        fecha_creacion=row.fecha_creacion,
    )


@router.get("/usuarios", response_model=list[UsuarioResponse])
def listar_usuarios(
    user: dict = Depends(get_current_user),
    conn: pyodbc.Connection = Depends(limss_db),
):
    """Solo admins pueden ver el listado completo de usuarios."""
    if user["rol"] != "admin":
        raise HTTPException(status_code=403, detail="Solo administradores pueden ver usuarios")

    cursor = conn.cursor()
    cursor.execute("SELECT * FROM lims_usuarios ORDER BY apellido, nombre")
    return [
        UsuarioResponse(
            id_usuario=r.id_usuario,
            codigo=r.codigo,
            nombre=r.nombre,
            apellido=r.apellido,
            rol=r.rol,
            activo=bool(r.activo),
            fecha_creacion=r.fecha_creacion,
        )
        for r in cursor.fetchall()
    ]


@router.put("/usuarios/{id_usuario}/estado", response_model=UsuarioResponse)
def cambiar_estado_usuario(
    id_usuario: int,
    activo: bool,
    user: dict = Depends(get_current_user),
    conn: pyodbc.Connection = Depends(limss_db),
):
    """Activa o desactiva un usuario. Solo admins."""
    if user["rol"] != "admin":
        raise HTTPException(status_code=403, detail="Solo administradores pueden modificar usuarios")

    if id_usuario == user["id_usuario"] and not activo:
        raise HTTPException(status_code=400, detail="No podés desactivar tu propio usuario")

    cursor = conn.cursor()
    cursor.execute("SELECT * FROM lims_usuarios WHERE id_usuario = ?", id_usuario)
    row = cursor.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")

    cursor.execute(
        "UPDATE lims_usuarios SET activo = ? WHERE id_usuario = ?",
        1 if activo else 0,
        id_usuario,
    )

    audit.registrar(
        conn,
        entidad="usuario",
        accion="activar" if activo else "desactivar",
        id_usuario=user["id_usuario"],
        id_entidad=id_usuario,
        valor_anterior={"activo": bool(row.activo)},
        valor_nuevo={"activo": activo},
    )

    cursor.execute("SELECT * FROM lims_usuarios WHERE id_usuario = ?", id_usuario)
    row = cursor.fetchone()
    return UsuarioResponse(
        id_usuario=row.id_usuario,
        codigo=row.codigo,
        nombre=row.nombre,
        apellido=row.apellido,
        rol=row.rol,
        activo=bool(row.activo),
        fecha_creacion=row.fecha_creacion,
    )
