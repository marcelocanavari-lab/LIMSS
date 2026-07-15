"""
Servicio de Audit Trail
Toda acción relevante del sistema pasa por aquí.
La tabla lims_audit_trail es APPEND ONLY: sin UPDATE ni DELETE.
"""
import json
import pyodbc
from typing import Optional


def registrar(
    conn: pyodbc.Connection,
    *,
    entidad: str,
    accion: str,
    id_usuario: Optional[int] = None,
    id_entidad: Optional[int] = None,
    valor_anterior: Optional[dict] = None,
    valor_nuevo: Optional[dict] = None,
    motivo: Optional[str] = None,
    ip_origen: Optional[str] = None,
) -> None:
    """
    Inserta un registro inmutable en lims_audit_trail.

    Uso:
        audit.registrar(conn,
            entidad="sesion", accion="login",
            id_usuario=1, ip_origen="192.168.1.10")
    """
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO lims_audit_trail
            (id_usuario, entidad, id_entidad, accion,
             valor_anterior, valor_nuevo, motivo, ip_origen)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        id_usuario, entidad, id_entidad, accion,
        json.dumps(valor_anterior, default=str) if valor_anterior else None,
        json.dumps(valor_nuevo, default=str) if valor_nuevo else None,
        motivo, ip_origen,
    )
