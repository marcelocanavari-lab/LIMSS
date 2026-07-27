"""
Configuración editable de la integración LIMSS-ERP (lims_erp_config).

Hoy solo guarda el mapeo tipo_material -> CODSAR (GIT59SAR, ERP GI_LX) que
antes estaba hardcodeado en erp_materiales.CODSAR_POR_TIPO -- ver
obtener_codsar_por_tipo() en ese módulo, que lee de acá con ese mismo
hardcodeo como fallback si la consulta falla.

Pantalla exclusiva para admin (son parámetros de integración con el ERP,
no algo que deba tocar un analista/QA en el día a día).
"""
import pyodbc
from fastapi import APIRouter, Depends, HTTPException

from app.core.security import require_rol
from app.db.connections import limss_db
from app.schemas.erp_config import ErpConfig, ErpConfigUpdate
from app.services import audit

router = APIRouter(prefix="/api/erp-config", tags=["Configuración ERP"])


def _fila_a_config(row) -> ErpConfig:
    return ErpConfig(
        id=row.id,
        clave=row.clave,
        valor=row.valor,
        descripcion=row.descripcion,
        editable=bool(row.editable),
        fecha_modificacion=row.fecha_modificacion,
        id_usuario_modificacion=row.id_usuario_modificacion,
    )


@router.get("", response_model=list[ErpConfig])
def listar_config(
    user: dict = Depends(require_rol("admin")),
    conn: pyodbc.Connection = Depends(limss_db),
):
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM lims_erp_config ORDER BY clave")
    return [_fila_a_config(r) for r in cursor.fetchall()]


@router.put("/{id_config}", response_model=ErpConfig)
def actualizar_config(
    id_config: int,
    body: ErpConfigUpdate,
    user: dict = Depends(require_rol("admin")),
    conn: pyodbc.Connection = Depends(limss_db),
):
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM lims_erp_config WHERE id = ?", id_config)
    row = cursor.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Configuración no encontrada")
    if not row.editable:
        raise HTTPException(status_code=400, detail="Este parámetro no es editable")

    valor_nuevo = body.valor.strip()
    descripcion_nueva = body.descripcion.strip() if body.descripcion is not None else row.descripcion

    cursor.execute(
        """
        UPDATE lims_erp_config
        SET valor = ?, descripcion = ?, fecha_modificacion = GETDATE(), id_usuario_modificacion = ?
        WHERE id = ?
        """,
        valor_nuevo, descripcion_nueva, user["id_usuario"], id_config,
    )

    audit.registrar(
        conn, entidad="erp_config", accion="modificar",
        id_usuario=user["id_usuario"], id_entidad=id_config,
        valor_anterior={"clave": row.clave, "valor": row.valor},
        valor_nuevo={"clave": row.clave, "valor": valor_nuevo},
    )

    cursor.execute("SELECT * FROM lims_erp_config WHERE id = ?", id_config)
    return _fila_a_config(cursor.fetchone())
