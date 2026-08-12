"""
Configuración editable de la integración LIMSS-ERP (lims_erp_config).

Hoy solo guarda el mapeo tipo_material -> CODSAR (GIT59SAR, ERP GI_LX) que
antes estaba hardcodeado en erp_materiales.CODSAR_POR_TIPO -- ver
obtener_codsar_por_tipo() en ese módulo, que lee de acá con ese mismo
hardcodeo como fallback si la consulta falla.

Pantalla exclusiva para admin (son parámetros de integración con el ERP,
no algo que deba tocar un analista/QA en el día a día).
"""
from typing import Optional

import pyodbc
from fastapi import APIRouter, Depends, HTTPException

from app.core.security import require_rol
from app.db.connections import erp_db, limss_db
from app.schemas.erp_config import ErpConfig, ErpConfigUpdate, SubarticuloConfig, SubarticuloUpsert
from app.services import audit
from app.services.erp_materiales import listar_subarticulos_erp

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


# ── Subartículos que requieren muestreo (agente de detección de IR) ────────
#
# La unidad de configuración es el subartículo (GIT59SAR.CODSAR -- catálogo
# chico de tipos de material: materia prima, granel, semi-elaborado, etc.),
# NO el artículo individual (GIM21ART, miles de filas): esta pantalla lista
# el catálogo GIT59SAR del ERP y, para cada fila, si ya está configurada en
# lims_erp_subarticulo_config -- que es lo que consulta el agente de
# detección automática de IR (ver app/services/agente_muestreo.py) para
# decidir si un material requiere muestreo. Sin esto cargado, todo
# comprobante nuevo queda con resultado='subarticulo_no_configurado'.

def _fila_a_subarticulo(erp_codsar: str, erp_dessar: Optional[str], config_row) -> SubarticuloConfig:
    """config_row puede existir pero con activo=0 (fila desactivada a mano
    en la base, este flujo simplificado siempre reactiva con activo=1 al
    guardar) -- en ese caso se trata igual que 'no configurado', porque es
    exactamente lo que ve el agente (buscar_subarticulo_config filtra
    activo=1)."""
    configurado = config_row is not None and bool(config_row.activo)
    if not configurado:
        return SubarticuloConfig(erp_codsar=erp_codsar, erp_dessar=erp_dessar, configurado=False, requiere_muestreo=False)
    return SubarticuloConfig(
        erp_codsar=erp_codsar, erp_dessar=erp_dessar, configurado=True,
        requiere_muestreo=bool(config_row.requiere_muestreo),
        id=config_row.id, fecha_carga=config_row.fecha_carga, id_usuario_carga=config_row.id_usuario_carga,
    )


@router.get("/subarticulos", response_model=list[SubarticuloConfig])
def listar_subarticulos(
    user: dict = Depends(require_rol("qa", "admin")),
    erp: pyodbc.Connection = Depends(erp_db),
    conn: pyodbc.Connection = Depends(limss_db),
):
    """Catálogo completo de GIT59SAR (ERP), combinado con el estado de
    configuración en LIMSS de cada uno -- el agente evalúa exactamente
    contra lims_erp_subarticulo_config, así que esta vista siempre refleja
    lo que el agente va a ver."""
    catalogo = listar_subarticulos_erp(erp)

    cursor = conn.cursor()
    cursor.execute("SELECT * FROM lims_erp_subarticulo_config")
    config_por_codsar = {row.erp_codsar.strip(): row for row in cursor.fetchall()}

    return [
        _fila_a_subarticulo(
            item.CODSAR.strip(), item.DESSAR.strip() if item.DESSAR else None,
            config_por_codsar.get(item.CODSAR.strip()),
        )
        for item in catalogo
    ]


@router.put("/subarticulos/{erp_codsar}", response_model=SubarticuloConfig)
def guardar_subarticulo(
    erp_codsar: str,
    body: SubarticuloUpsert,
    user: dict = Depends(require_rol("qa", "admin")),
    erp: pyodbc.Connection = Depends(erp_db),
    conn: pyodbc.Connection = Depends(limss_db),
):
    """Tilda/destilda 'requiere muestreo' para un subartículo del catálogo
    GIT59SAR -- inserta la fila en lims_erp_subarticulo_config si es la
    primera vez que se configura ese CODSAR, o actualiza la existente.
    Valida contra el ERP que el CODSAR sea real (evita configurar códigos
    inventados que el agente nunca va a poder matchear)."""
    codsar = erp_codsar.strip()

    cursor_erp = erp.cursor()
    cursor_erp.execute("SELECT CODSAR, DESSAR FROM GIT59SAR WHERE RTRIM(CODSAR) = ?", codsar)
    catalogo = cursor_erp.fetchone()
    if not catalogo:
        raise HTTPException(status_code=404, detail=f"El CODSAR '{codsar}' no existe en el catálogo del ERP (GIT59SAR)")
    dessar = catalogo.DESSAR.strip() if catalogo.DESSAR else None

    cursor = conn.cursor()
    cursor.execute("SELECT * FROM lims_erp_subarticulo_config WHERE erp_codsar = ?", codsar)
    existente = cursor.fetchone()

    if existente:
        cursor.execute(
            "UPDATE lims_erp_subarticulo_config SET requiere_muestreo = ?, descripcion = ?, activo = 1 WHERE id = ?",
            1 if body.requiere_muestreo else 0, dessar, existente.id,
        )
        id_fila = existente.id
        audit.registrar(
            conn, entidad="erp_subarticulo_config", accion="modificar",
            id_usuario=user["id_usuario"], id_entidad=id_fila,
            valor_anterior={"requiere_muestreo": bool(existente.requiere_muestreo)},
            valor_nuevo={"erp_codsar": codsar, "requiere_muestreo": body.requiere_muestreo},
        )
    else:
        cursor.execute(
            "INSERT INTO lims_erp_subarticulo_config (erp_codsar, descripcion, requiere_muestreo, id_usuario_carga) "
            "VALUES (?, ?, ?, ?)",
            codsar, dessar, 1 if body.requiere_muestreo else 0, user["id_usuario"],
        )
        cursor.execute("SELECT @@IDENTITY AS id")
        id_fila = int(cursor.fetchone().id)
        audit.registrar(
            conn, entidad="erp_subarticulo_config", accion="crear",
            id_usuario=user["id_usuario"], id_entidad=id_fila,
            valor_nuevo={"erp_codsar": codsar, "requiere_muestreo": body.requiere_muestreo},
        )

    cursor.execute("SELECT * FROM lims_erp_subarticulo_config WHERE id = ?", id_fila)
    return _fila_a_subarticulo(codsar, dessar, cursor.fetchone())
