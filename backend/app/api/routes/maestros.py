"""
Datos Maestros: especificaciones (REQ-MAS-001/002) y testigos/estándares (REQ-MAS-003).

Prerrequisito de los módulos operativos: sin especificaciones no hay límites contra
los cuales validar OOS (Módulo II), y sin testigos no se puede confirmar un envío a
laboratorio externo (Módulo I).
"""
import os
from datetime import date, datetime
from typing import Optional

import pyodbc
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse

from app.core.security import get_current_user, require_rol
from app.db.connections import erp_db, limss_db
from app.schemas.maestros import (
    ArticuloERP,
    EnsayoMaestroCreate,
    EnsayoMaestroResponse,
    EspecificacionCopiar,
    EspecificacionCreate,
    EspecificacionDetalle,
    EspecificacionEnsayoCreate,
    EspecificacionEnsayoResponse,
    EspecificacionResponse,
    EspecificacionTestigoCreate,
    EspecificacionTestigoResponse,
    TestigoAjusteStock,
    TestigoMovimientoResponse,
    TestigoResponse,
)
from app.services import audit, storage
from app.services.erp_articulos import buscar_articulos

router = APIRouter(prefix="/api/maestros", tags=["Datos Maestros"])


# ── Helpers internos ─────────────────────────────────────────────

def _insertar_especificacion(
    cursor, *, erp_IdM21: int, erp_CODART: str, erp_DESART: str, tipo_material: str,
    cantidad_muestra: Optional[float], unidad_muestra: Optional[str],
    version: str, user_id: int,
    accion_terapeutica: Optional[str] = None, sinonimia: Optional[str] = None,
    nro_cas: Optional[str] = None, nombre_quimico: Optional[str] = None,
    formula_molecular: Optional[str] = None, peso_molecular: Optional[str] = None,
    envasado_almacenamiento: Optional[str] = None,
) -> int:
    cursor.execute(
        """
        INSERT INTO lims_especificaciones
            (erp_IdM21, erp_CODART, erp_DESART, tipo_material, cantidad_muestra, unidad_muestra,
             version, vigente, id_usuario_carga, accion_terapeutica, sinonimia, nro_cas,
             nombre_quimico, formula_molecular, peso_molecular, envasado_almacenamiento)
        VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        erp_IdM21, erp_CODART, erp_DESART, tipo_material, cantidad_muestra, unidad_muestra, version, user_id,
        accion_terapeutica, sinonimia, nro_cas, nombre_quimico, formula_molecular, peso_molecular,
        envasado_almacenamiento,
    )
    cursor.execute("SELECT @@IDENTITY AS id")
    return int(cursor.fetchone().id)


def _copiar_ensayos_especificacion(cursor, *, id_especificacion_origen: int, id_especificacion_destino: int) -> None:
    """Usado por 'revisar': la nueva versión arranca con los mismos ensayos que
    la versión anterior; el usuario los ajusta después desde la ficha de la
    nueva especificación (agregar/editar/quitar), igual que cantidad_muestra."""
    cursor.execute(
        "SELECT * FROM lims_especificacion_ensayos WHERE id_especificacion = ? ORDER BY orden",
        id_especificacion_origen,
    )
    for e in cursor.fetchall():
        cursor.execute(
            """
            INSERT INTO lims_especificacion_ensayos
                (id_especificacion, id_ensayo_maestro, orden, metodologia, tipo_dato,
                 limite_inferior, limite_superior, unidad_medida, valor_requerido,
                 especificacion_texto, obligatorio, requerido_por_defecto, id_laboratorio)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            id_especificacion_destino, e.id_ensayo_maestro, e.orden, e.metodologia, e.tipo_dato,
            e.limite_inferior, e.limite_superior, e.unidad_medida, e.valor_requerido,
            e.especificacion_texto, e.obligatorio, e.requerido_por_defecto, e.id_laboratorio,
        )


def _fila_a_especificacion(row) -> EspecificacionResponse:
    return EspecificacionResponse(
        id_especificacion=row.id_especificacion,
        erp_IdM21=row.erp_IdM21,
        erp_CODART=row.erp_CODART,
        erp_DESART=row.erp_DESART,
        tipo_material=row.tipo_material,
        cantidad_muestra=float(row.cantidad_muestra) if row.cantidad_muestra is not None else None,
        unidad_muestra=row.unidad_muestra,
        version=row.version,
        vigente=bool(row.vigente),
        id_usuario_carga=row.id_usuario_carga,
        fecha_carga=row.fecha_carga,
    )


_SELECT_ESPECIFICACION_ENSAYOS = """
    SELECT se.*, m.nombre_ensayo, lab.nombre AS laboratorio_nombre
    FROM lims_especificacion_ensayos se
    INNER JOIN lims_ensayos_maestro m ON m.id_ensayo_maestro = se.id_ensayo_maestro
    LEFT JOIN lims_laboratorios lab ON lab.id_laboratorio = se.id_laboratorio
"""


def _fila_a_especificacion_ensayo(e) -> EspecificacionEnsayoResponse:
    return EspecificacionEnsayoResponse(
        id_espec_ensayo=e.id_espec_ensayo,
        id_especificacion=e.id_especificacion,
        id_ensayo_maestro=e.id_ensayo_maestro,
        nombre_ensayo=e.nombre_ensayo,
        orden=e.orden,
        metodologia=e.metodologia,
        tipo_dato=e.tipo_dato,
        limite_inferior=float(e.limite_inferior) if e.limite_inferior is not None else None,
        limite_superior=float(e.limite_superior) if e.limite_superior is not None else None,
        unidad_medida=e.unidad_medida,
        valor_requerido=e.valor_requerido,
        especificacion_texto=e.especificacion_texto,
        obligatorio=bool(e.obligatorio),
        requerido_por_defecto=bool(e.requerido_por_defecto),
        id_laboratorio=e.id_laboratorio,
        laboratorio_nombre=e.laboratorio_nombre,
    )


def _obtener_especificacion_detalle(cursor, id_especificacion: int) -> EspecificacionDetalle:
    cursor.execute("SELECT * FROM lims_especificaciones WHERE id_especificacion = ?", id_especificacion)
    row = cursor.fetchone()

    cursor.execute(
        _SELECT_ESPECIFICACION_ENSAYOS + " WHERE se.id_especificacion = ? ORDER BY se.orden",
        id_especificacion,
    )
    ensayos = [_fila_a_especificacion_ensayo(e) for e in cursor.fetchall()]

    base = _fila_a_especificacion(row)
    return EspecificacionDetalle(**base.model_dump(), ensayos=ensayos)


def _a_fecha(valor) -> Optional[date]:
    """El driver ODBC no devuelve un tipo consistente para columnas DATE en
    este entorno (a veces date/datetime, a veces str); se normaliza siempre
    a date antes de operar."""
    if valor is None:
        return None
    if isinstance(valor, datetime):
        return valor.date()
    if isinstance(valor, date):
        return valor
    return date.fromisoformat(str(valor))


def _fila_a_testigo(row, fecha_ref: Optional[date] = None) -> TestigoResponse:
    hoy = fecha_ref or date.today()
    fecha_vencimiento = _a_fecha(row.fecha_vencimiento)
    # Sin fecha de vencimiento cargada, no se puede considerar vencido ni
    # próximo a vencer.
    vencido = fecha_vencimiento is not None and fecha_vencimiento < hoy
    por_vencer = fecha_vencimiento is not None and not vencido and (fecha_vencimiento - hoy).days < 30
    stock_bajo = float(row.stock_actual) < float(row.stock_minimo)
    return TestigoResponse(
        id_testigo=row.id_testigo,
        codigo=row.codigo,
        nombre=row.nombre,
        nro_lote=row.nro_lote,
        nro_ir=row.nro_ir,
        fecha_vencimiento=fecha_vencimiento,
        stock_actual=float(row.stock_actual),
        stock_minimo=float(row.stock_minimo),
        unidad_medida=row.unidad_medida,
        pdf_certificado=row.pdf_certificado,
        activo=bool(row.activo),
        id_usuario_carga=row.id_usuario_carga,
        fecha_carga=row.fecha_carga,
        observaciones=row.observaciones,
        vencido=vencido,
        por_vencer=por_vencer,
        stock_bajo=stock_bajo,
    )


# ── Artículos ERP (búsqueda para asociar especificaciones) ───────

@router.get("/articulos", response_model=list[ArticuloERP])
def listar_articulos_erp(
    buscar: str = Query("", description="Código o descripción del artículo"),
    user: dict = Depends(require_rol("analista_qc", "admin", "qa")),
    erp: pyodbc.Connection = Depends(erp_db),
):
    rows = buscar_articulos(erp, buscar)
    return [
        ArticuloERP(IdM21=r.IdM21, CODART=r.CODART, DESART=r.DESART, unidad=r.unidad)
        for r in rows
    ]


# ── Especificaciones ──────────────────────────────────────────────

@router.post("/especificaciones", response_model=EspecificacionDetalle, status_code=201)
def crear_especificacion(
    body: EspecificacionCreate,
    user: dict = Depends(require_rol("analista_qc", "admin", "qa")),
    conn: pyodbc.Connection = Depends(limss_db),
):
    cursor = conn.cursor()
    cursor.execute(
        "SELECT 1 FROM lims_especificaciones WHERE erp_IdM21 = ? AND vigente = 1",
        body.erp_IdM21,
    )
    if cursor.fetchone():
        raise HTTPException(
            status_code=409,
            detail="Ya existe una especificación vigente para este artículo. Usá 'revisar' para crear una nueva versión.",
        )

    id_especificacion = _insertar_especificacion(
        cursor,
        erp_IdM21=body.erp_IdM21, erp_CODART=body.erp_CODART, erp_DESART=body.erp_DESART,
        tipo_material=body.tipo_material,
        cantidad_muestra=body.cantidad_muestra, unidad_muestra=body.unidad_muestra,
        version="1.0", user_id=user["id_usuario"],
    )

    audit.registrar(
        conn, entidad="especificacion", accion="crear",
        id_usuario=user["id_usuario"], id_entidad=id_especificacion,
        valor_nuevo={"erp_CODART": body.erp_CODART, "tipo_material": body.tipo_material, "version": "1.0"},
    )

    return _obtener_especificacion_detalle(cursor, id_especificacion)


@router.get("/especificaciones", response_model=list[EspecificacionResponse])
def listar_especificaciones(
    vigente: Optional[bool] = Query(True, description="true=solo vigentes, false=solo obsoletas, omitir=todas"),
    buscar: str = Query(""),
    user: dict = Depends(get_current_user),
    conn: pyodbc.Connection = Depends(limss_db),
):
    cursor = conn.cursor()
    like = f"%{buscar}%"
    if vigente is None:
        cursor.execute(
            """
            SELECT * FROM lims_especificaciones
            WHERE erp_CODART LIKE ? OR erp_DESART LIKE ?
            ORDER BY erp_DESART, version DESC
            """,
            like, like,
        )
    else:
        cursor.execute(
            """
            SELECT * FROM lims_especificaciones
            WHERE vigente = ? AND (erp_CODART LIKE ? OR erp_DESART LIKE ?)
            ORDER BY erp_DESART, version DESC
            """,
            1 if vigente else 0, like, like,
        )
    return [_fila_a_especificacion(r) for r in cursor.fetchall()]


@router.get("/especificaciones/{id_especificacion}", response_model=EspecificacionDetalle)
def detalle_especificacion(
    id_especificacion: int,
    user: dict = Depends(get_current_user),
    conn: pyodbc.Connection = Depends(limss_db),
):
    cursor = conn.cursor()
    cursor.execute("SELECT 1 FROM lims_especificaciones WHERE id_especificacion = ?", id_especificacion)
    if not cursor.fetchone():
        raise HTTPException(status_code=404, detail="Especificación no encontrada")
    return _obtener_especificacion_detalle(cursor, id_especificacion)


@router.post("/especificaciones/{id_especificacion}/revisar", response_model=EspecificacionDetalle, status_code=201)
def revisar_especificacion(
    id_especificacion: int,
    user: dict = Depends(require_rol("analista_qc", "admin", "qa")),
    conn: pyodbc.Connection = Depends(limss_db),
):
    """Crea una nueva versión vigente a partir de la especificación {id_especificacion}
    (que debe ser la vigente actual) y marca a esta última como obsoleta. La nueva
    versión arranca con una copia de los ensayos de la anterior; se ajustan después
    desde la ficha de la especificación (agregar/editar/quitar ensayos)."""
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM lims_especificaciones WHERE id_especificacion = ?", id_especificacion)
    actual = cursor.fetchone()
    if not actual:
        raise HTTPException(status_code=404, detail="Especificación no encontrada")
    if not actual.vigente:
        raise HTTPException(status_code=400, detail="Solo se puede revisar la versión vigente")

    try:
        version_nueva = f"{int(float(actual.version)) + 1}.0"
    except (TypeError, ValueError):
        version_nueva = "2.0"

    cursor.execute(
        "UPDATE lims_especificaciones SET vigente = 0 WHERE id_especificacion = ?",
        id_especificacion,
    )

    id_nueva = _insertar_especificacion(
        cursor,
        erp_IdM21=actual.erp_IdM21, erp_CODART=actual.erp_CODART, erp_DESART=actual.erp_DESART,
        tipo_material=actual.tipo_material,
        cantidad_muestra=actual.cantidad_muestra, unidad_muestra=actual.unidad_muestra,
        version=version_nueva, user_id=user["id_usuario"],
    )
    _copiar_ensayos_especificacion(cursor, id_especificacion_origen=id_especificacion, id_especificacion_destino=id_nueva)

    audit.registrar(
        conn, entidad="especificacion", accion="revisar",
        id_usuario=user["id_usuario"], id_entidad=id_nueva,
        valor_anterior={"id_especificacion": id_especificacion, "version": actual.version},
        valor_nuevo={"id_especificacion": id_nueva, "version": version_nueva},
    )

    return _obtener_especificacion_detalle(cursor, id_nueva)


@router.post("/especificaciones/{id_especificacion}/copiar", response_model=EspecificacionDetalle, status_code=201)
def copiar_especificacion(
    id_especificacion: int,
    body: EspecificacionCopiar,
    user: dict = Depends(require_rol("analista_qc", "admin", "qa")),
    conn: pyodbc.Connection = Depends(limss_db),
):
    """Crea una especificación nueva e independiente a partir de {id_especificacion},
    para un artículo/tipo de material potencialmente distinto (ej. la versión
    Semi-Elaborado de un Producto Terminado). A diferencia de 'revisar', no
    toca la especificación original -- quedan las dos como filas separadas.
    Copia los datos descriptivos y los ensayos (con su id_laboratorio); no
    copia los testigos asociados, que son específicos del producto original."""
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM lims_especificaciones WHERE id_especificacion = ?", id_especificacion)
    original = cursor.fetchone()
    if not original:
        raise HTTPException(status_code=404, detail="Especificación no encontrada")

    cursor.execute(
        "SELECT 1 FROM lims_especificaciones WHERE erp_IdM21 = ? AND vigente = 1",
        body.erp_IdM21,
    )
    if cursor.fetchone():
        raise HTTPException(
            status_code=409,
            detail="Ya existe una especificación vigente para este artículo. Usá 'revisar' para crear una nueva versión.",
        )

    id_nueva = _insertar_especificacion(
        cursor,
        erp_IdM21=body.erp_IdM21, erp_CODART=body.erp_CODART, erp_DESART=body.erp_DESART,
        tipo_material=body.tipo_material,
        cantidad_muestra=original.cantidad_muestra, unidad_muestra=original.unidad_muestra,
        version=body.version, user_id=user["id_usuario"],
        accion_terapeutica=original.accion_terapeutica, sinonimia=original.sinonimia,
        nro_cas=original.nro_cas, nombre_quimico=original.nombre_quimico,
        formula_molecular=original.formula_molecular, peso_molecular=original.peso_molecular,
        envasado_almacenamiento=original.envasado_almacenamiento,
    )
    _copiar_ensayos_especificacion(cursor, id_especificacion_origen=id_especificacion, id_especificacion_destino=id_nueva)

    audit.registrar(
        conn, entidad="especificacion", accion="copiar",
        id_usuario=user["id_usuario"], id_entidad=id_nueva,
        valor_anterior={"id_especificacion": id_especificacion, "erp_CODART": original.erp_CODART},
        valor_nuevo={"id_especificacion": id_nueva, "erp_CODART": body.erp_CODART, "tipo_material": body.tipo_material},
    )

    return _obtener_especificacion_detalle(cursor, id_nueva)


# ── Ensayos: catálogo maestro ──────────────────────────────────────

@router.get("/ensayos", response_model=list[EnsayoMaestroResponse])
def listar_ensayos_maestro(
    buscar: str = Query(""),
    user: dict = Depends(get_current_user),
    conn: pyodbc.Connection = Depends(limss_db),
):
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT m.id_ensayo_maestro, m.nombre_ensayo, m.bibliografia, m.observaciones,
               (SELECT COUNT(*) FROM lims_especificacion_ensayos se WHERE se.id_ensayo_maestro = m.id_ensayo_maestro) AS cantidad_especificaciones
        FROM lims_ensayos_maestro m
        WHERE m.nombre_ensayo LIKE ?
        ORDER BY m.nombre_ensayo
        """,
        f"%{buscar}%",
    )
    return [
        EnsayoMaestroResponse(
            id_ensayo_maestro=r.id_ensayo_maestro, nombre_ensayo=r.nombre_ensayo,
            bibliografia=r.bibliografia, observaciones=r.observaciones,
            cantidad_especificaciones=r.cantidad_especificaciones,
        )
        for r in cursor.fetchall()
    ]


@router.post("/ensayos", response_model=EnsayoMaestroResponse, status_code=201)
def crear_ensayo_maestro(
    body: EnsayoMaestroCreate,
    user: dict = Depends(require_rol("analista_qc", "admin", "qa")),
    conn: pyodbc.Connection = Depends(limss_db),
):
    cursor = conn.cursor()
    cursor.execute("SELECT 1 FROM lims_ensayos_maestro WHERE nombre_ensayo = ?", body.nombre_ensayo)
    if cursor.fetchone():
        raise HTTPException(status_code=409, detail=f"Ya existe un ensayo llamado '{body.nombre_ensayo}' en el catálogo")

    cursor.execute(
        "INSERT INTO lims_ensayos_maestro (nombre_ensayo, bibliografia, observaciones) VALUES (?, ?, ?)",
        body.nombre_ensayo, body.bibliografia, body.observaciones,
    )
    cursor.execute("SELECT @@IDENTITY AS id")
    id_ensayo_maestro = int(cursor.fetchone().id)

    audit.registrar(
        conn, entidad="ensayo_maestro", accion="crear",
        id_usuario=user["id_usuario"], id_entidad=id_ensayo_maestro,
        valor_nuevo={"nombre_ensayo": body.nombre_ensayo},
    )

    return EnsayoMaestroResponse(
        id_ensayo_maestro=id_ensayo_maestro, nombre_ensayo=body.nombre_ensayo,
        bibliografia=body.bibliografia, observaciones=body.observaciones, cantidad_especificaciones=0,
    )


@router.put("/ensayos/{id_ensayo_maestro}", response_model=EnsayoMaestroResponse)
def editar_ensayo_maestro(
    id_ensayo_maestro: int,
    body: EnsayoMaestroCreate,
    user: dict = Depends(require_rol("analista_qc", "admin", "qa")),
    conn: pyodbc.Connection = Depends(limss_db),
):
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM lims_ensayos_maestro WHERE id_ensayo_maestro = ?", id_ensayo_maestro)
    row = cursor.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Ensayo no encontrado en el catálogo")

    cursor.execute(
        "SELECT 1 FROM lims_ensayos_maestro WHERE nombre_ensayo = ? AND id_ensayo_maestro <> ?",
        body.nombre_ensayo, id_ensayo_maestro,
    )
    if cursor.fetchone():
        raise HTTPException(status_code=409, detail=f"Ya existe un ensayo llamado '{body.nombre_ensayo}' en el catálogo")

    cursor.execute(
        "UPDATE lims_ensayos_maestro SET nombre_ensayo = ?, bibliografia = ?, observaciones = ? WHERE id_ensayo_maestro = ?",
        body.nombre_ensayo, body.bibliografia, body.observaciones, id_ensayo_maestro,
    )

    audit.registrar(
        conn, entidad="ensayo_maestro", accion="modificar",
        id_usuario=user["id_usuario"], id_entidad=id_ensayo_maestro,
        valor_anterior={"nombre_ensayo": row.nombre_ensayo},
        valor_nuevo={"nombre_ensayo": body.nombre_ensayo},
    )

    cursor.execute(
        "SELECT COUNT(*) AS n FROM lims_especificacion_ensayos WHERE id_ensayo_maestro = ?", id_ensayo_maestro,
    )
    cantidad = cursor.fetchone().n
    return EnsayoMaestroResponse(
        id_ensayo_maestro=id_ensayo_maestro, nombre_ensayo=body.nombre_ensayo,
        bibliografia=body.bibliografia, observaciones=body.observaciones, cantidad_especificaciones=cantidad,
    )


@router.delete("/ensayos/{id_ensayo_maestro}", status_code=204)
def eliminar_ensayo_maestro(
    id_ensayo_maestro: int,
    user: dict = Depends(require_rol("qa", "admin")),
    conn: pyodbc.Connection = Depends(limss_db),
):
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM lims_ensayos_maestro WHERE id_ensayo_maestro = ?", id_ensayo_maestro)
    row = cursor.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Ensayo no encontrado en el catálogo")

    cursor.execute("SELECT COUNT(*) AS n FROM lims_especificacion_ensayos WHERE id_ensayo_maestro = ?", id_ensayo_maestro)
    cantidad = cursor.fetchone().n
    if cantidad > 0:
        raise HTTPException(
            status_code=400,
            detail=f"No se puede eliminar: este ensayo está asignado a {cantidad} especificaciones",
        )

    cursor.execute("DELETE FROM lims_ensayos_maestro WHERE id_ensayo_maestro = ?", id_ensayo_maestro)

    audit.registrar(
        conn, entidad="ensayo_maestro", accion="eliminar",
        id_usuario=user["id_usuario"], id_entidad=id_ensayo_maestro,
        valor_anterior={"nombre_ensayo": row.nombre_ensayo},
    )


# ── Ensayos aplicados a una especificación ─────────────────────────

@router.get("/especificaciones/{id_especificacion}/ensayos", response_model=list[EspecificacionEnsayoResponse])
def listar_ensayos_especificacion(
    id_especificacion: int,
    user: dict = Depends(get_current_user),
    conn: pyodbc.Connection = Depends(limss_db),
):
    cursor = conn.cursor()
    cursor.execute("SELECT 1 FROM lims_especificaciones WHERE id_especificacion = ?", id_especificacion)
    if not cursor.fetchone():
        raise HTTPException(status_code=404, detail="Especificación no encontrada")

    cursor.execute(
        _SELECT_ESPECIFICACION_ENSAYOS + " WHERE se.id_especificacion = ? ORDER BY se.orden",
        id_especificacion,
    )
    return [_fila_a_especificacion_ensayo(e) for e in cursor.fetchall()]


def _verificar_especificacion_vigente(cursor, id_especificacion: int):
    cursor.execute("SELECT vigente FROM lims_especificaciones WHERE id_especificacion = ?", id_especificacion)
    row = cursor.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Especificación no encontrada")
    if not row.vigente:
        raise HTTPException(status_code=400, detail="Solo se pueden modificar los ensayos de la versión vigente")


@router.post("/especificaciones/{id_especificacion}/ensayos", response_model=EspecificacionEnsayoResponse, status_code=201)
def agregar_ensayo_especificacion(
    id_especificacion: int,
    body: EspecificacionEnsayoCreate,
    user: dict = Depends(require_rol("analista_qc", "admin", "qa")),
    conn: pyodbc.Connection = Depends(limss_db),
):
    cursor = conn.cursor()
    _verificar_especificacion_vigente(cursor, id_especificacion)

    cursor.execute("SELECT 1 FROM lims_ensayos_maestro WHERE id_ensayo_maestro = ?", body.id_ensayo_maestro)
    if not cursor.fetchone():
        raise HTTPException(status_code=404, detail="El ensayo indicado no existe en el catálogo")

    if body.id_laboratorio is not None:
        cursor.execute("SELECT 1 FROM lims_laboratorios WHERE id_laboratorio = ? AND activo = 1", body.id_laboratorio)
        if not cursor.fetchone():
            raise HTTPException(status_code=404, detail="El laboratorio indicado no existe o está inactivo")

    cursor.execute(
        """
        INSERT INTO lims_especificacion_ensayos
            (id_especificacion, id_ensayo_maestro, orden, metodologia, tipo_dato,
             limite_inferior, limite_superior, unidad_medida, valor_requerido,
             especificacion_texto, obligatorio, requerido_por_defecto, id_laboratorio)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        id_especificacion, body.id_ensayo_maestro, body.orden, body.metodologia, body.tipo_dato,
        body.limite_inferior, body.limite_superior, body.unidad_medida, body.valor_requerido,
        body.especificacion_texto, 1 if body.obligatorio else 0, 1 if body.requerido_por_defecto else 0,
        body.id_laboratorio,
    )
    cursor.execute("SELECT @@IDENTITY AS id")
    id_espec_ensayo = int(cursor.fetchone().id)

    audit.registrar(
        conn, entidad="especificacion_ensayo", accion="agregar",
        id_usuario=user["id_usuario"], id_entidad=id_espec_ensayo,
        valor_nuevo={"id_especificacion": id_especificacion, "id_ensayo_maestro": body.id_ensayo_maestro},
    )

    cursor.execute(_SELECT_ESPECIFICACION_ENSAYOS + " WHERE se.id_espec_ensayo = ?", id_espec_ensayo)
    return _fila_a_especificacion_ensayo(cursor.fetchone())


@router.put("/especificaciones/{id_especificacion}/ensayos/{id_espec_ensayo}", response_model=EspecificacionEnsayoResponse)
def editar_ensayo_especificacion(
    id_especificacion: int,
    id_espec_ensayo: int,
    body: EspecificacionEnsayoCreate,
    user: dict = Depends(require_rol("analista_qc", "admin", "qa")),
    conn: pyodbc.Connection = Depends(limss_db),
):
    cursor = conn.cursor()
    _verificar_especificacion_vigente(cursor, id_especificacion)

    cursor.execute(
        "SELECT 1 FROM lims_especificacion_ensayos WHERE id_espec_ensayo = ? AND id_especificacion = ?",
        id_espec_ensayo, id_especificacion,
    )
    if not cursor.fetchone():
        raise HTTPException(status_code=404, detail="El ensayo no pertenece a esta especificación")

    cursor.execute("SELECT 1 FROM lims_ensayos_maestro WHERE id_ensayo_maestro = ?", body.id_ensayo_maestro)
    if not cursor.fetchone():
        raise HTTPException(status_code=404, detail="El ensayo indicado no existe en el catálogo")

    if body.id_laboratorio is not None:
        cursor.execute("SELECT 1 FROM lims_laboratorios WHERE id_laboratorio = ? AND activo = 1", body.id_laboratorio)
        if not cursor.fetchone():
            raise HTTPException(status_code=404, detail="El laboratorio indicado no existe o está inactivo")

    cursor.execute(
        """
        UPDATE lims_especificacion_ensayos
        SET id_ensayo_maestro = ?, orden = ?, metodologia = ?, tipo_dato = ?,
            limite_inferior = ?, limite_superior = ?, unidad_medida = ?, valor_requerido = ?,
            especificacion_texto = ?, obligatorio = ?, requerido_por_defecto = ?, id_laboratorio = ?
        WHERE id_espec_ensayo = ?
        """,
        body.id_ensayo_maestro, body.orden, body.metodologia, body.tipo_dato,
        body.limite_inferior, body.limite_superior, body.unidad_medida, body.valor_requerido,
        body.especificacion_texto, 1 if body.obligatorio else 0, 1 if body.requerido_por_defecto else 0,
        body.id_laboratorio, id_espec_ensayo,
    )

    audit.registrar(
        conn, entidad="especificacion_ensayo", accion="modificar",
        id_usuario=user["id_usuario"], id_entidad=id_espec_ensayo,
        valor_nuevo={"id_especificacion": id_especificacion, "id_ensayo_maestro": body.id_ensayo_maestro},
    )

    cursor.execute(_SELECT_ESPECIFICACION_ENSAYOS + " WHERE se.id_espec_ensayo = ?", id_espec_ensayo)
    return _fila_a_especificacion_ensayo(cursor.fetchone())


@router.delete("/especificaciones/{id_especificacion}/ensayos/{id_espec_ensayo}", status_code=204)
def eliminar_ensayo_especificacion(
    id_especificacion: int,
    id_espec_ensayo: int,
    user: dict = Depends(require_rol("analista_qc", "admin", "qa")),
    conn: pyodbc.Connection = Depends(limss_db),
):
    cursor = conn.cursor()
    _verificar_especificacion_vigente(cursor, id_especificacion)

    cursor.execute(
        "DELETE FROM lims_especificacion_ensayos WHERE id_espec_ensayo = ? AND id_especificacion = ?",
        id_espec_ensayo, id_especificacion,
    )
    if cursor.rowcount == 0:
        raise HTTPException(status_code=404, detail="El ensayo no pertenece a esta especificación")

    audit.registrar(
        conn, entidad="especificacion_ensayo", accion="eliminar",
        id_usuario=user["id_usuario"], id_entidad=id_espec_ensayo,
        valor_anterior={"id_especificacion": id_especificacion},
    )


# ── Testigos asociados a una especificación ───────────────────────

@router.post("/especificaciones/{id_especificacion}/testigos", response_model=EspecificacionTestigoResponse, status_code=201)
def asociar_testigo(
    id_especificacion: int,
    body: EspecificacionTestigoCreate,
    user: dict = Depends(require_rol("analista_qc", "admin", "qa")),
    conn: pyodbc.Connection = Depends(limss_db),
):
    cursor = conn.cursor()
    cursor.execute("SELECT 1 FROM lims_especificaciones WHERE id_especificacion = ?", id_especificacion)
    if not cursor.fetchone():
        raise HTTPException(status_code=404, detail="Especificación no encontrada")

    cursor.execute("SELECT codigo, nombre FROM lims_testigos WHERE id_testigo = ?", body.id_testigo)
    testigo = cursor.fetchone()
    if not testigo:
        raise HTTPException(status_code=404, detail="Testigo no encontrado")

    cursor.execute(
        "SELECT 1 FROM lims_especificacion_testigos WHERE id_especificacion = ? AND id_testigo = ?",
        id_especificacion, body.id_testigo,
    )
    if cursor.fetchone():
        raise HTTPException(status_code=409, detail="El testigo ya está asociado a esta especificación")

    cursor.execute(
        "INSERT INTO lims_especificacion_testigos (id_especificacion, id_testigo) VALUES (?, ?)",
        id_especificacion, body.id_testigo,
    )
    cursor.execute("SELECT @@IDENTITY AS id")
    id_rel = int(cursor.fetchone().id)

    audit.registrar(
        conn, entidad="especificacion_testigo", accion="asociar",
        id_usuario=user["id_usuario"], id_entidad=id_rel,
        valor_nuevo={"id_especificacion": id_especificacion, "id_testigo": body.id_testigo},
    )

    return EspecificacionTestigoResponse(
        id=id_rel, id_especificacion=id_especificacion, id_testigo=body.id_testigo,
        codigo=testigo.codigo, nombre=testigo.nombre,
    )


@router.delete("/especificaciones/{id_especificacion}/testigos/{id_testigo}", status_code=204)
def desasociar_testigo(
    id_especificacion: int,
    id_testigo: int,
    user: dict = Depends(require_rol("analista_qc", "admin", "qa")),
    conn: pyodbc.Connection = Depends(limss_db),
):
    cursor = conn.cursor()
    cursor.execute(
        "DELETE FROM lims_especificacion_testigos WHERE id_especificacion = ? AND id_testigo = ?",
        id_especificacion, id_testigo,
    )
    if cursor.rowcount == 0:
        raise HTTPException(status_code=404, detail="El testigo no está asociado a esta especificación")

    audit.registrar(
        conn, entidad="especificacion_testigo", accion="desasociar",
        id_usuario=user["id_usuario"], id_entidad=id_especificacion,
        valor_anterior={"id_especificacion": id_especificacion, "id_testigo": id_testigo},
    )


@router.get("/especificaciones/{id_especificacion}/testigos", response_model=list[EspecificacionTestigoResponse])
def listar_testigos_especificacion(
    id_especificacion: int,
    user: dict = Depends(get_current_user),
    conn: pyodbc.Connection = Depends(limss_db),
):
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT et.id, et.id_especificacion, et.id_testigo, t.codigo, t.nombre
        FROM lims_especificacion_testigos et
        INNER JOIN lims_testigos t ON t.id_testigo = et.id_testigo
        WHERE et.id_especificacion = ?
        ORDER BY t.codigo
        """,
        id_especificacion,
    )
    return [
        EspecificacionTestigoResponse(
            id=r.id, id_especificacion=r.id_especificacion, id_testigo=r.id_testigo,
            codigo=r.codigo, nombre=r.nombre,
        )
        for r in cursor.fetchall()
    ]


# ── Testigos y estándares ─────────────────────────────────────────

@router.post("/testigos", response_model=TestigoResponse, status_code=201)
def crear_testigo(
    codigo: str = Form(..., min_length=1, max_length=20),
    nombre: str = Form(..., min_length=1, max_length=150),
    nro_lote: str = Form(..., min_length=1, max_length=50),
    nro_ir: Optional[str] = Form(None, max_length=6),
    fecha_vencimiento: date = Form(...),
    stock_actual: float = Form(...),
    stock_minimo: float = Form(...),
    unidad_medida: Optional[str] = Form(None),
    observaciones: Optional[str] = Form(None, max_length=500),
    pdf_certificado: Optional[UploadFile] = File(None),
    user: dict = Depends(require_rol("analista_qc", "admin", "qa")),
    conn: pyodbc.Connection = Depends(limss_db),
):
    if stock_actual < 0 or stock_minimo < 0:
        raise HTTPException(status_code=400, detail="El stock no puede ser negativo")

    cursor = conn.cursor()
    cursor.execute("SELECT 1 FROM lims_testigos WHERE codigo = ?", codigo)
    if cursor.fetchone():
        raise HTTPException(status_code=409, detail=f"El código '{codigo}' ya existe")

    ruta_pdf = None
    if pdf_certificado is not None and pdf_certificado.filename:
        ruta_pdf = storage.guardar_pdf_testigo(pdf_certificado, codigo)

    cursor.execute(
        """
        INSERT INTO lims_testigos
            (codigo, nombre, nro_lote, nro_ir, fecha_vencimiento, stock_actual, stock_minimo,
             unidad_medida, pdf_certificado, id_usuario_carga, observaciones)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        codigo, nombre, nro_lote, nro_ir, str(fecha_vencimiento), stock_actual, stock_minimo,
        unidad_medida, ruta_pdf, user["id_usuario"], observaciones,
    )
    cursor.execute("SELECT @@IDENTITY AS id")
    id_testigo = int(cursor.fetchone().id)

    cursor.execute(
        """
        INSERT INTO lims_testigo_movimientos
            (id_testigo, tipo, cantidad, stock_resultante, id_usuario, observaciones)
        VALUES (?, 'ingreso', ?, ?, ?, 'Carga inicial')
        """,
        id_testigo, stock_actual, stock_actual, user["id_usuario"],
    )

    audit.registrar(
        conn, entidad="testigo", accion="crear",
        id_usuario=user["id_usuario"], id_entidad=id_testigo,
        valor_nuevo={"codigo": codigo, "stock_actual": stock_actual},
    )

    cursor.execute("SELECT * FROM lims_testigos WHERE id_testigo = ?", id_testigo)
    return _fila_a_testigo(cursor.fetchone())


@router.put("/testigos/{id_testigo}", response_model=TestigoResponse)
def editar_testigo(
    id_testigo: int,
    nombre: str = Form(..., min_length=1, max_length=150),
    nro_lote: str = Form(..., min_length=1, max_length=50),
    nro_ir: Optional[str] = Form(None, max_length=6),
    fecha_vencimiento: date = Form(...),
    stock_minimo: float = Form(...),
    unidad_medida: Optional[str] = Form(None),
    observaciones: Optional[str] = Form(None, max_length=500),
    pdf_certificado: Optional[UploadFile] = File(None),
    user: dict = Depends(require_rol("analista_qc", "admin", "qa")),
    conn: pyodbc.Connection = Depends(limss_db),
):
    """Edita los datos descriptivos del testigo. El código y el stock actual
    (se ajusta vía /movimiento para mantener la trazabilidad) no son editables
    por acá. El certificado PDF es opcional: si no se manda, se conserva el
    actual; si se manda, reemplaza al anterior."""
    if stock_minimo < 0:
        raise HTTPException(status_code=400, detail="El stock no puede ser negativo")

    cursor = conn.cursor()
    cursor.execute("SELECT * FROM lims_testigos WHERE id_testigo = ?", id_testigo)
    row = cursor.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Testigo no encontrado")

    ruta_pdf = row.pdf_certificado
    if pdf_certificado is not None:
        ruta_pdf = storage.guardar_pdf_testigo(pdf_certificado, row.codigo)

    campos_anteriores = {
        "nombre": row.nombre, "nro_lote": row.nro_lote, "nro_ir": row.nro_ir,
        "fecha_vencimiento": str(row.fecha_vencimiento), "stock_minimo": float(row.stock_minimo),
        "unidad_medida": row.unidad_medida, "observaciones": row.observaciones,
        "pdf_certificado": row.pdf_certificado,
    }
    campos_nuevos = {
        "nombre": nombre, "nro_lote": nro_lote, "nro_ir": nro_ir,
        "fecha_vencimiento": str(fecha_vencimiento), "stock_minimo": stock_minimo,
        "unidad_medida": unidad_medida, "observaciones": observaciones,
        "pdf_certificado": ruta_pdf,
    }

    cursor.execute(
        """
        UPDATE lims_testigos
        SET nombre = ?, nro_lote = ?, nro_ir = ?, fecha_vencimiento = ?, stock_minimo = ?,
            unidad_medida = ?, observaciones = ?, pdf_certificado = ?
        WHERE id_testigo = ?
        """,
        nombre, nro_lote, nro_ir, str(fecha_vencimiento), stock_minimo,
        unidad_medida, observaciones, ruta_pdf, id_testigo,
    )

    valor_anterior = {k: v for k, v in campos_anteriores.items() if v != campos_nuevos[k]}
    valor_nuevo = {k: v for k, v in campos_nuevos.items() if v != campos_anteriores[k]}
    audit.registrar(
        conn, entidad="testigo", accion="modificar",
        id_usuario=user["id_usuario"], id_entidad=id_testigo,
        valor_anterior=valor_anterior or None, valor_nuevo=valor_nuevo or None,
    )

    cursor.execute("SELECT * FROM lims_testigos WHERE id_testigo = ?", id_testigo)
    return _fila_a_testigo(cursor.fetchone())


def _ordenar_por_fecha_vencimiento(testigos: list[TestigoResponse], reverse: bool) -> list[TestigoResponse]:
    """Los que no tienen fecha cargada quedan siempre al final, sea ASC o DESC."""
    con_fecha = [t for t in testigos if t.fecha_vencimiento is not None]
    sin_fecha = [t for t in testigos if t.fecha_vencimiento is None]
    con_fecha.sort(key=lambda t: t.fecha_vencimiento, reverse=reverse)
    return con_fecha + sin_fecha


@router.get("/testigos", response_model=list[TestigoResponse])
def listar_testigos(
    activo: Optional[bool] = Query(None),
    solo_alertas: bool = Query(False, description="Solo testigos vencidos, por vencer (<30 días) o con stock bajo"),
    buscar: str = Query(""),
    estado: Optional[str] = Query(None, pattern=r"^(normal|por_vencer|vencido|sin_vencimiento)$"),
    stock_bajo: Optional[bool] = Query(None),
    orden: Optional[str] = Query(None, pattern=r"^(vencimiento_asc|vencimiento_desc|nombre_asc|codigo_asc|stock_asc|ir_asc)$"),
    fecha_ref: Optional[date] = Query(None, description="Fecha de referencia para calcular vencido/por_vencer; por defecto, hoy"),
    user: dict = Depends(get_current_user),
    conn: pyodbc.Connection = Depends(limss_db),
):
    cursor = conn.cursor()
    like = f"%{buscar}%"
    if activo is None:
        cursor.execute(
            "SELECT * FROM lims_testigos WHERE codigo LIKE ? OR nombre LIKE ? ORDER BY nombre",
            like, like,
        )
    else:
        cursor.execute(
            "SELECT * FROM lims_testigos WHERE activo = ? AND (codigo LIKE ? OR nombre LIKE ?) ORDER BY nombre",
            1 if activo else 0, like, like,
        )
    testigos = [_fila_a_testigo(r, fecha_ref=fecha_ref) for r in cursor.fetchall()]

    if solo_alertas:
        testigos = [t for t in testigos if t.vencido or t.por_vencer or t.stock_bajo]

    if estado == "normal":
        testigos = [t for t in testigos if t.fecha_vencimiento is not None and not t.vencido and not t.por_vencer]
    elif estado == "por_vencer":
        testigos = [t for t in testigos if t.por_vencer]
    elif estado == "vencido":
        testigos = [t for t in testigos if t.vencido]
    elif estado == "sin_vencimiento":
        testigos = [t for t in testigos if t.fecha_vencimiento is None]

    if stock_bajo:
        testigos = [t for t in testigos if t.stock_bajo]

    if orden == "vencimiento_asc":
        testigos = _ordenar_por_fecha_vencimiento(testigos, reverse=False)
    elif orden == "vencimiento_desc":
        testigos = _ordenar_por_fecha_vencimiento(testigos, reverse=True)
    elif orden == "nombre_asc":
        testigos = sorted(testigos, key=lambda t: t.nombre)
    elif orden == "codigo_asc":
        testigos = sorted(testigos, key=lambda t: t.codigo)
    elif orden == "stock_asc":
        testigos = sorted(testigos, key=lambda t: t.stock_actual)
    elif orden == "ir_asc":
        # Formato NNN/AA: ordena primero por año (AA) y después por número
        # (NNN) -- no alfabéticamente, si no 356/24 quedaría después de 013/25.
        def _anio_numero_ir(t):
            if t.nro_ir and "/" in t.nro_ir:
                numero, _, anio = t.nro_ir.partition("/")
                if numero.strip().isdigit() and anio.strip().isdigit():
                    return int(anio), int(numero)
            return None

        con_ir = [(t, _anio_numero_ir(t)) for t in testigos]
        sin_ir = [t for t, clave in con_ir if clave is None]
        con_ir = [(t, clave) for t, clave in con_ir if clave is not None]
        con_ir.sort(key=lambda par: par[1])
        testigos = [t for t, _ in con_ir] + sin_ir

    return testigos


@router.get("/testigos/{id_testigo}", response_model=TestigoResponse)
def detalle_testigo(
    id_testigo: int,
    user: dict = Depends(get_current_user),
    conn: pyodbc.Connection = Depends(limss_db),
):
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM lims_testigos WHERE id_testigo = ?", id_testigo)
    row = cursor.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Testigo no encontrado")
    return _fila_a_testigo(row)


@router.get("/testigos/{id_testigo}/movimientos", response_model=list[TestigoMovimientoResponse])
def historial_movimientos_testigo(
    id_testigo: int,
    user: dict = Depends(get_current_user),
    conn: pyodbc.Connection = Depends(limss_db),
):
    cursor = conn.cursor()
    cursor.execute(
        "SELECT * FROM lims_testigo_movimientos WHERE id_testigo = ? ORDER BY fecha_hora DESC",
        id_testigo,
    )
    return [
        TestigoMovimientoResponse(
            id_movimiento=r.id_movimiento,
            id_testigo=r.id_testigo,
            id_envio=r.id_envio,
            tipo=r.tipo,
            cantidad=float(r.cantidad),
            stock_resultante=float(r.stock_resultante),
            id_usuario=r.id_usuario,
            fecha_hora=r.fecha_hora,
            observaciones=r.observaciones,
        )
        for r in cursor.fetchall()
    ]


@router.get("/testigos/{id_testigo}/certificado")
def descargar_certificado_testigo(
    id_testigo: int,
    user: dict = Depends(get_current_user),
    conn: pyodbc.Connection = Depends(limss_db),
):
    cursor = conn.cursor()
    cursor.execute("SELECT pdf_certificado FROM lims_testigos WHERE id_testigo = ?", id_testigo)
    row = cursor.fetchone()
    if not row or not row.pdf_certificado:
        raise HTTPException(status_code=404, detail="Certificado no encontrado")

    ruta = storage.ruta_absoluta(row.pdf_certificado)
    if not os.path.exists(ruta):
        raise HTTPException(status_code=404, detail="El archivo no se encuentra en el servidor")

    return FileResponse(ruta, media_type="application/pdf", filename=os.path.basename(ruta))


@router.put("/testigos/{id_testigo}/estado", response_model=TestigoResponse)
def cambiar_estado_testigo(
    id_testigo: int,
    activo: bool,
    user: dict = Depends(require_rol("analista_qc", "admin", "qa")),
    conn: pyodbc.Connection = Depends(limss_db),
):
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM lims_testigos WHERE id_testigo = ?", id_testigo)
    row = cursor.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Testigo no encontrado")

    cursor.execute("UPDATE lims_testigos SET activo = ? WHERE id_testigo = ?", 1 if activo else 0, id_testigo)

    audit.registrar(
        conn, entidad="testigo", accion="activar" if activo else "desactivar",
        id_usuario=user["id_usuario"], id_entidad=id_testigo,
        valor_anterior={"activo": bool(row.activo)}, valor_nuevo={"activo": activo},
    )

    cursor.execute("SELECT * FROM lims_testigos WHERE id_testigo = ?", id_testigo)
    return _fila_a_testigo(cursor.fetchone())


@router.post("/testigos/{id_testigo}/movimiento", response_model=TestigoResponse, status_code=201)
def ajustar_stock_testigo(
    id_testigo: int,
    body: TestigoAjusteStock,
    user: dict = Depends(require_rol("analista_qc", "admin", "qa")),
    conn: pyodbc.Connection = Depends(limss_db),
):
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM lims_testigos WHERE id_testigo = ?", id_testigo)
    row = cursor.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Testigo no encontrado")

    stock_nuevo = float(row.stock_actual) + body.cantidad
    if stock_nuevo < 0:
        raise HTTPException(status_code=400, detail="El ajuste dejaría el stock en negativo")

    cursor.execute(
        "UPDATE lims_testigos SET stock_actual = ? WHERE id_testigo = ?",
        stock_nuevo, id_testigo,
    )
    cursor.execute(
        """
        INSERT INTO lims_testigo_movimientos
            (id_testigo, tipo, cantidad, stock_resultante, id_usuario, observaciones)
        VALUES (?, 'ajuste', ?, ?, ?, ?)
        """,
        id_testigo, body.cantidad, stock_nuevo, user["id_usuario"], body.observaciones,
    )

    audit.registrar(
        conn, entidad="testigo", accion="ajuste_stock",
        id_usuario=user["id_usuario"], id_entidad=id_testigo,
        valor_anterior={"stock_actual": float(row.stock_actual)},
        valor_nuevo={"stock_actual": stock_nuevo}, motivo=body.observaciones,
    )

    cursor.execute("SELECT * FROM lims_testigos WHERE id_testigo = ?", id_testigo)
    return _fila_a_testigo(cursor.fetchone())
