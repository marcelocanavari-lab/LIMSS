"""
Materiales del ERP filtrados por tipo (CODSAR), para el wizard de creación de
especificaciones: Paso 1 elige el tipo, Paso 2 busca solo entre esos artículos.
"""
import pyodbc
from fastapi import APIRouter, Depends, Query

from app.core.security import require_rol
from app.db.connections import erp_db
from app.schemas.maestros import ArticuloERP
from app.services.erp_materiales import CODSAR_POR_TIPO, buscar_materiales

router = APIRouter(prefix="/api/materiales", tags=["Materiales ERP"])


@router.get("/", response_model=list[ArticuloERP])
def listar_materiales(
    tipo: str = Query(..., pattern=r"^(materia_prima|granel|semi_elaborado|producto_terminado)$"),
    buscar: str = Query(""),
    user: dict = Depends(require_rol("admin", "qa")),
    erp: pyodbc.Connection = Depends(erp_db),
):
    codsar = CODSAR_POR_TIPO[tipo]
    rows = buscar_materiales(erp, codsar, buscar)
    return [ArticuloERP(IdM21=r.IdM21, CODART=r.CODART, DESART=r.DESART) for r in rows]
