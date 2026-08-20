"""
Novedades de Material de Empaque -- lista de gestión manual, completamente
standalone: no se cruza con Solicitudes, Muestras ni ningún otro módulo
(sin FK a lims_solicitudes_muestreo/lims_muestras, sin avisos automáticos
en otras pantallas). "Resolver" es una anotación de texto libre sobre qué
se verificó, no una vinculación a una solicitud o muestra puntual.

El buscador de artículo del formulario de alta reutiliza GET /api/materiales/
(tipo=material_empaque) -- el mismo wizard de búsqueda por CODSAR que ya usa
la pantalla de Especificaciones -- en vez de duplicar esa consulta acá.
"""
from typing import Optional

import pyodbc
from fastapi import APIRouter, Depends, HTTPException, Query

from app.core.security import require_rol
from app.db.connections import erp_db, limss_db
from app.schemas.novedades_empaque import NovedadEmpaqueCreate, NovedadEmpaqueResolver, NovedadEmpaqueResponse
from app.services import audit

router = APIRouter(prefix="/api/novedades-empaque", tags=["Novedades de Empaque"])

_ROLES = ("analista_qc", "qa", "admin")

_SELECT_NOVEDAD = """
    SELECT n.*, uc.nombre + ' ' + uc.apellido AS usuario_carga_nombre,
           ur.nombre + ' ' + ur.apellido AS usuario_resolucion_nombre
    FROM lims_novedades_empaque n
    INNER JOIN lims_usuarios uc ON uc.id_usuario = n.id_usuario_carga
    LEFT JOIN lims_usuarios ur ON ur.id_usuario = n.id_usuario_resolucion
"""


def _resolver_descripciones(erp: pyodbc.Connection, codarts: set[str]) -> dict:
    """CODART -> DESART contra el ERP (GIM21ART), solo para mostrar el
    nombre del artículo en el listado -- no se guarda en la tabla, así que
    si el catálogo cambió después de cargar la novedad, se muestra el
    nombre actual (o nada, si el código ya no existe)."""
    if not codarts:
        return {}
    cursor = erp.cursor()
    placeholders = ",".join("?" * len(codarts))
    # RTRIM: GIM21ART.CODART/DESART son CHAR de ancho fijo, ver la nota en
    # erp_ir.py -- se recorta al leer, único punto de esta consulta.
    cursor.execute(f"SELECT RTRIM(CODART) AS CODART, RTRIM(DESART) AS DESART FROM GIM21ART WHERE CODART IN ({placeholders})", *codarts)
    return {r.CODART: r.DESART for r in cursor.fetchall()}


def _fila_a_novedad(row, descripciones: dict) -> NovedadEmpaqueResponse:
    return NovedadEmpaqueResponse(
        id_novedad=row.id_novedad,
        erp_CODART=row.erp_CODART,
        erp_DESART=descripciones.get(row.erp_CODART.strip()),
        titulo=row.titulo,
        descripcion=row.descripcion,
        estado=row.estado,
        usuario_carga_nombre=row.usuario_carga_nombre,
        fecha_carga=row.fecha_carga,
        usuario_resolucion_nombre=row.usuario_resolucion_nombre,
        fecha_resolucion=row.fecha_resolucion,
        observaciones_resolucion=row.observaciones_resolucion,
    )


@router.get("", response_model=list[NovedadEmpaqueResponse])
def listar_novedades(
    estado: Optional[str] = Query(None, pattern=r"^(pendiente|resuelta)$"),
    user: dict = Depends(require_rol(*_ROLES)),
    erp: pyodbc.Connection = Depends(erp_db),
    conn: pyodbc.Connection = Depends(limss_db),
):
    cursor = conn.cursor()
    where = " WHERE n.estado = ?" if estado else ""
    params = [estado] if estado else []
    cursor.execute(_SELECT_NOVEDAD + where + " ORDER BY n.fecha_carga DESC", *params)
    filas = cursor.fetchall()
    descripciones = _resolver_descripciones(erp, {f.erp_CODART.strip() for f in filas})
    return [_fila_a_novedad(f, descripciones) for f in filas]


@router.post("", response_model=NovedadEmpaqueResponse, status_code=201)
def crear_novedad(
    body: NovedadEmpaqueCreate,
    user: dict = Depends(require_rol(*_ROLES)),
    erp: pyodbc.Connection = Depends(erp_db),
    conn: pyodbc.Connection = Depends(limss_db),
):
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO lims_novedades_empaque (erp_CODART, titulo, descripcion, estado, id_usuario_carga, fecha_carga)
        VALUES (?, ?, ?, 'pendiente', ?, GETDATE())
        """,
        body.erp_CODART.strip(), body.titulo.strip(), body.descripcion.strip(), user["id_usuario"],
    )
    cursor.execute("SELECT @@IDENTITY AS id")
    id_novedad = int(cursor.fetchone().id)

    audit.registrar(
        conn, entidad="novedad_empaque", accion="crear", id_usuario=user["id_usuario"], id_entidad=id_novedad,
        valor_nuevo={"erp_CODART": body.erp_CODART, "titulo": body.titulo},
    )

    cursor.execute(_SELECT_NOVEDAD + " WHERE n.id_novedad = ?", id_novedad)
    row = cursor.fetchone()
    descripciones = _resolver_descripciones(erp, {row.erp_CODART.strip()})
    return _fila_a_novedad(row, descripciones)


@router.post("/{id_novedad}/resolver", response_model=NovedadEmpaqueResponse)
def resolver_novedad(
    id_novedad: int,
    body: NovedadEmpaqueResolver,
    user: dict = Depends(require_rol(*_ROLES)),
    erp: pyodbc.Connection = Depends(erp_db),
    conn: pyodbc.Connection = Depends(limss_db),
):
    cursor = conn.cursor()
    cursor.execute("SELECT estado FROM lims_novedades_empaque WHERE id_novedad = ?", id_novedad)
    row = cursor.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Novedad no encontrada")
    if row.estado != "pendiente":
        raise HTTPException(status_code=400, detail="Esta novedad ya está resuelta")

    observaciones = body.observaciones_resolucion.strip() if body.observaciones_resolucion else None
    cursor.execute(
        """
        UPDATE lims_novedades_empaque
        SET estado = 'resuelta', id_usuario_resolucion = ?, fecha_resolucion = GETDATE(), observaciones_resolucion = ?
        WHERE id_novedad = ?
        """,
        user["id_usuario"], observaciones, id_novedad,
    )
    audit.registrar(
        conn, entidad="novedad_empaque", accion="resolver", id_usuario=user["id_usuario"], id_entidad=id_novedad,
        valor_nuevo={"observaciones_resolucion": observaciones},
    )

    cursor.execute(_SELECT_NOVEDAD + " WHERE n.id_novedad = ?", id_novedad)
    row = cursor.fetchone()
    descripciones = _resolver_descripciones(erp, {row.erp_CODART.strip()})
    return _fila_a_novedad(row, descripciones)
