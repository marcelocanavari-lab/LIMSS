"""
Auditoría del sistema (lims_audit_trail, append-only).

Pantalla exclusiva de admin: expone en solo lectura lo que
app.services.audit.registrar() va acumulando desde el resto de los
módulos (login, ediciones de muestra, cambios de config ERP, etc.).
"""
import pyodbc
from datetime import date, datetime, timedelta
from typing import Optional
from fastapi import APIRouter, Depends, Query

from app.core.security import require_rol
from app.db.connections import limss_db
from app.schemas.auditoria import AuditoriaListado, AuditoriaRegistro, AuditoriaUsuario

router = APIRouter(prefix="/api/auditoria", tags=["Auditoría"])


def _detalle(entidad: str, id_entidad: Optional[int], motivo: Optional[str]) -> str:
    detalle = f"{entidad} #{id_entidad}" if id_entidad is not None else entidad
    return f"{detalle} — {motivo}" if motivo else detalle


@router.get("", response_model=AuditoriaListado)
def listar_auditoria(
    fecha_desde: Optional[date] = Query(None),
    fecha_hasta: Optional[date] = Query(None),
    id_usuario: Optional[int] = Query(None),
    accion: Optional[str] = Query(None, description="Búsqueda parcial sobre lims_audit_trail.accion"),
    limite: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    user: dict = Depends(require_rol("admin")),
    conn: pyodbc.Connection = Depends(limss_db),
):
    condiciones = []
    params: list = []

    if fecha_desde:
        # El driver ODBC "SQL Server" (legacy, configurado en .env) no puede
        # bindear objetos date de Python (SQLBindParameter falla) -- se
        # convierte a datetime, que sí soporta.
        condiciones.append("a.fecha_hora >= ?")
        params.append(datetime.combine(fecha_desde, datetime.min.time()))
    if fecha_hasta:
        condiciones.append("a.fecha_hora < ?")
        params.append(datetime.combine(fecha_hasta + timedelta(days=1), datetime.min.time()))
    if id_usuario:
        condiciones.append("a.id_usuario = ?")
        params.append(id_usuario)
    if accion:
        condiciones.append("a.accion LIKE ?")
        params.append(f"%{accion}%")

    where = ("WHERE " + " AND ".join(condiciones)) if condiciones else ""

    cursor = conn.cursor()
    cursor.execute(f"SELECT COUNT(*) AS total FROM lims_audit_trail a {where}", *params)
    total = cursor.fetchone().total

    cursor.execute(
        f"""
        SELECT a.id_audit, a.fecha_hora, a.entidad, a.id_entidad, a.accion,
               a.motivo, a.valor_anterior, a.valor_nuevo,
               u.nombre + ' ' + u.apellido AS usuario_nombre
        FROM lims_audit_trail a
        LEFT JOIN lims_usuarios u ON u.id_usuario = a.id_usuario
        {where}
        ORDER BY a.fecha_hora DESC, a.id_audit DESC
        OFFSET ? ROWS FETCH NEXT ? ROWS ONLY
        """,
        *params, offset, limite,
    )

    registros = [
        AuditoriaRegistro(
            id_audit=r.id_audit,
            fecha_hora=r.fecha_hora,
            usuario_nombre=r.usuario_nombre,
            accion=r.accion,
            detalle=_detalle(r.entidad, r.id_entidad, r.motivo),
            valor_anterior=r.valor_anterior,
            valor_nuevo=r.valor_nuevo,
        )
        for r in cursor.fetchall()
    ]

    return AuditoriaListado(total=total, registros=registros)


@router.get("/usuarios", response_model=list[AuditoriaUsuario])
def listar_usuarios_auditoria(
    user: dict = Depends(require_rol("admin")),
    conn: pyodbc.Connection = Depends(limss_db),
):
    cursor = conn.cursor()
    cursor.execute("SELECT id_usuario, nombre, apellido FROM lims_usuarios ORDER BY apellido, nombre")
    return [
        AuditoriaUsuario(id_usuario=r.id_usuario, nombre_completo=f"{r.nombre} {r.apellido}")
        for r in cursor.fetchall()
    ]
