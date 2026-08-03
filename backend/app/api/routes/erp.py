"""
Búsquedas genéricas contra el ERP GI_LX que no encajan en un módulo más
específico (ver también materiales.py, erp_ir.py, erp_lotes.py).
"""
import pyodbc
from fastapi import APIRouter, Depends, Query

from app.core.security import get_current_user
from app.db.connections import erp_db
from app.schemas.maestros import ProveedorERP

router = APIRouter(prefix="/api/erp", tags=["ERP"])


@router.get("/proveedores", response_model=list[ProveedorERP])
def buscar_proveedores(
    buscar: str = Query(..., min_length=2),
    user: dict = Depends(get_current_user),
    erp: pyodbc.Connection = Depends(erp_db),
):
    """GIM02ANA.IdT04 = 2 identifica el tipo "proveedor" -- mismo filtro que
    ya usa erp_ir.py para resolver el proveedor de un IR."""
    like = f"%{buscar}%"
    cursor = erp.cursor()
    cursor.execute(
        """
        SELECT M02Id, CODANA, DESANA
        FROM GIM02ANA
        WHERE IdT04 = 2
          AND (CODANA LIKE ? OR DESANA LIKE ?)
        ORDER BY DESANA
        """,
        like, like,
    )
    return [
        ProveedorERP(id_proveedor=r.M02Id, codigo=r.CODANA, nombre=r.DESANA)
        for r in cursor.fetchall()
    ]
