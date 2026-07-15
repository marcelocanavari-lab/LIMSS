"""
Datos Maestros: especificaciones (REQ-MAS-001/002) y testigos/estándares (REQ-MAS-003).

Prerrequisito de los módulos operativos: sin especificaciones no hay límites contra
los cuales validar OOS (Módulo II), y sin testigos no se puede confirmar un envío a
laboratorio externo (Módulo I).
"""
import os
from datetime import date
from typing import Optional

import pyodbc
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse

from app.core.security import get_current_user, require_rol
from app.db.connections import erp_db, limss_db
from app.schemas.maestros import (
    ArticuloERP,
    EnsayoCreate,
    EnsayoResponse,
    EspecificacionCreate,
    EspecificacionDetalle,
    EspecificacionResponse,
    EspecificacionRevision,
    TestigoAjusteStock,
    TestigoMovimientoResponse,
    TestigoResponse,
    TestigoUpdate,
)
from app.services import audit, storage
from app.services.erp_articulos import buscar_articulos

router = APIRouter(prefix="/api/maestros", tags=["Datos Maestros"])


# ── Helpers internos ─────────────────────────────────────────────

def _insertar_especificacion(
    cursor, *, erp_IdM21: int, erp_CODART: str, erp_DESART: str, tipo_material: str,
    ensayos: list[EnsayoCreate], version: str, user_id: int,
) -> int:
    cursor.execute(
        """
        INSERT INTO lims_especificaciones
            (erp_IdM21, erp_CODART, erp_DESART, tipo_material, version, vigente, id_usuario_carga)
        VALUES (?, ?, ?, ?, ?, 1, ?)
        """,
        erp_IdM21, erp_CODART, erp_DESART, tipo_material, version, user_id,
    )
    cursor.execute("SELECT @@IDENTITY AS id")
    id_especificacion = int(cursor.fetchone().id)

    for ensayo in ensayos:
        cursor.execute(
            """
            INSERT INTO lims_ensayos
                (id_especificacion, orden, nombre_ensayo, metodologia, tipo_dato,
                 limite_inferior, limite_superior, unidad_medida, valor_requerido, obligatorio,
                 observaciones)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            id_especificacion, ensayo.orden, ensayo.nombre_ensayo, ensayo.metodologia,
            ensayo.tipo_dato, ensayo.limite_inferior, ensayo.limite_superior,
            ensayo.unidad_medida, ensayo.valor_requerido, 1 if ensayo.obligatorio else 0,
            ensayo.observaciones,
        )

    return id_especificacion


def _fila_a_especificacion(row) -> EspecificacionResponse:
    return EspecificacionResponse(
        id_especificacion=row.id_especificacion,
        erp_IdM21=row.erp_IdM21,
        erp_CODART=row.erp_CODART,
        erp_DESART=row.erp_DESART,
        tipo_material=row.tipo_material,
        version=row.version,
        vigente=bool(row.vigente),
        id_usuario_carga=row.id_usuario_carga,
        fecha_carga=row.fecha_carga,
    )


def _obtener_especificacion_detalle(cursor, id_especificacion: int) -> EspecificacionDetalle:
    cursor.execute("SELECT * FROM lims_especificaciones WHERE id_especificacion = ?", id_especificacion)
    row = cursor.fetchone()

    cursor.execute(
        "SELECT * FROM lims_ensayos WHERE id_especificacion = ? ORDER BY orden",
        id_especificacion,
    )
    ensayos = [
        EnsayoResponse(
            id_ensayo=e.id_ensayo,
            id_especificacion=e.id_especificacion,
            orden=e.orden,
            nombre_ensayo=e.nombre_ensayo,
            metodologia=e.metodologia,
            tipo_dato=e.tipo_dato,
            limite_inferior=float(e.limite_inferior) if e.limite_inferior is not None else None,
            limite_superior=float(e.limite_superior) if e.limite_superior is not None else None,
            unidad_medida=e.unidad_medida,
            valor_requerido=e.valor_requerido,
            obligatorio=bool(e.obligatorio),
            observaciones=e.observaciones,
        )
        for e in cursor.fetchall()
    ]

    base = _fila_a_especificacion(row)
    return EspecificacionDetalle(**base.model_dump(), ensayos=ensayos)


def _fila_a_testigo(row) -> TestigoResponse:
    hoy = date.today()
    vencido = row.fecha_vencimiento < hoy
    por_vencer = not vencido and (row.fecha_vencimiento - hoy).days < 30
    stock_bajo = float(row.stock_actual) < float(row.stock_minimo)
    return TestigoResponse(
        id_testigo=row.id_testigo,
        codigo=row.codigo,
        nombre=row.nombre,
        nro_lote=row.nro_lote,
        fecha_vencimiento=row.fecha_vencimiento,
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
    user: dict = Depends(require_rol("admin", "qa")),
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
    user: dict = Depends(require_rol("admin", "qa")),
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
        tipo_material=body.tipo_material, ensayos=body.ensayos,
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
    body: EspecificacionRevision,
    user: dict = Depends(require_rol("admin", "qa")),
    conn: pyodbc.Connection = Depends(limss_db),
):
    """Crea una nueva versión vigente a partir de la especificación {id_especificacion}
    (que debe ser la vigente actual) y marca a esta última como obsoleta."""
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
        tipo_material=actual.tipo_material, ensayos=body.ensayos,
        version=version_nueva, user_id=user["id_usuario"],
    )

    audit.registrar(
        conn, entidad="especificacion", accion="revisar",
        id_usuario=user["id_usuario"], id_entidad=id_nueva,
        valor_anterior={"id_especificacion": id_especificacion, "version": actual.version},
        valor_nuevo={"id_especificacion": id_nueva, "version": version_nueva},
    )

    return _obtener_especificacion_detalle(cursor, id_nueva)


# ── Testigos y estándares ─────────────────────────────────────────

@router.post("/testigos", response_model=TestigoResponse, status_code=201)
def crear_testigo(
    codigo: str = Form(..., min_length=1, max_length=20),
    nombre: str = Form(..., min_length=1, max_length=150),
    nro_lote: str = Form(..., min_length=1, max_length=50),
    fecha_vencimiento: date = Form(...),
    stock_actual: float = Form(...),
    stock_minimo: float = Form(...),
    unidad_medida: Optional[str] = Form(None),
    observaciones: Optional[str] = Form(None, max_length=500),
    pdf_certificado: UploadFile = File(...),
    user: dict = Depends(require_rol("admin", "qa")),
    conn: pyodbc.Connection = Depends(limss_db),
):
    if stock_actual < 0 or stock_minimo < 0:
        raise HTTPException(status_code=400, detail="El stock no puede ser negativo")

    cursor = conn.cursor()
    cursor.execute("SELECT 1 FROM lims_testigos WHERE codigo = ?", codigo)
    if cursor.fetchone():
        raise HTTPException(status_code=409, detail=f"El código '{codigo}' ya existe")

    ruta_pdf = storage.guardar_pdf_testigo(pdf_certificado, codigo)

    cursor.execute(
        """
        INSERT INTO lims_testigos
            (codigo, nombre, nro_lote, fecha_vencimiento, stock_actual, stock_minimo,
             unidad_medida, pdf_certificado, id_usuario_carga, observaciones)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        codigo, nombre, nro_lote, fecha_vencimiento, stock_actual, stock_minimo,
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
    body: TestigoUpdate,
    user: dict = Depends(require_rol("admin", "qa")),
    conn: pyodbc.Connection = Depends(limss_db),
):
    """Edita los datos descriptivos del testigo. El código, el stock actual
    (se ajusta vía /movimiento para mantener la trazabilidad) y el certificado
    PDF no son editables por acá."""
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM lims_testigos WHERE id_testigo = ?", id_testigo)
    row = cursor.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Testigo no encontrado")

    campos_anteriores = {
        "nombre": row.nombre, "nro_lote": row.nro_lote,
        "fecha_vencimiento": str(row.fecha_vencimiento), "stock_minimo": float(row.stock_minimo),
        "unidad_medida": row.unidad_medida, "observaciones": row.observaciones,
    }
    campos_nuevos = {
        "nombre": body.nombre, "nro_lote": body.nro_lote,
        "fecha_vencimiento": str(body.fecha_vencimiento), "stock_minimo": body.stock_minimo,
        "unidad_medida": body.unidad_medida, "observaciones": body.observaciones,
    }

    cursor.execute(
        """
        UPDATE lims_testigos
        SET nombre = ?, nro_lote = ?, fecha_vencimiento = ?, stock_minimo = ?,
            unidad_medida = ?, observaciones = ?
        WHERE id_testigo = ?
        """,
        body.nombre, body.nro_lote, body.fecha_vencimiento, body.stock_minimo,
        body.unidad_medida, body.observaciones, id_testigo,
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


@router.get("/testigos", response_model=list[TestigoResponse])
def listar_testigos(
    activo: Optional[bool] = Query(None),
    solo_alertas: bool = Query(False, description="Solo testigos vencidos, por vencer (<30 días) o con stock bajo"),
    buscar: str = Query(""),
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
    testigos = [_fila_a_testigo(r) for r in cursor.fetchall()]
    if solo_alertas:
        testigos = [t for t in testigos if t.vencido or t.por_vencer or t.stock_bajo]
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
    user: dict = Depends(require_rol("admin", "qa")),
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
    user: dict = Depends(require_rol("admin", "qa")),
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
