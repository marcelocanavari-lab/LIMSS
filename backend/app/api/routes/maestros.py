"""
Datos Maestros: especificaciones (REQ-MAS-001/002) y testigos/estándares (REQ-MAS-003).

Prerrequisito de los módulos operativos: sin especificaciones no hay límites contra
los cuales validar OOS (Módulo II), y sin testigos no se puede confirmar un envío a
laboratorio externo (Módulo I).
"""
import os
from datetime import date, datetime
from typing import Literal, Optional

import pyodbc
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse

from app.core.security import get_current_user, require_rol
from app.db.connections import erp_db, limss_db
from app.schemas.maestros import (
    ArticuloERP,
    EnsayoMaestroCreate,
    EnsayoMaestroResponse,
    EspecificacionCantidades,
    EspecificacionCopiar,
    EspecificacionCreate,
    EspecificacionDetalle,
    EspecificacionEnsayoCreate,
    EspecificacionEnsayoResponse,
    EspecificacionMuestraCreate,
    EspecificacionMuestraResponse,
    EspecificacionResponse,
    EspecificacionTestigoCreate,
    EspecificacionTestigoResponse,
    LaboratorioAsignado,
    TestigoAjusteStock,
    TestigoCategoriaCreate,
    TestigoCategoriaResponse,
    TestigoCategoriaUpdate,
    TestigoLaboratorioConsumoUpdate,
    TestigoLaboratorioCreate,
    TestigoMovimientoResponse,
    TestigoOrigenCreate,
    TestigoOrigenResponse,
    TestigoOrigenUpdate,
    TestigoResponse,
)
from app.services import audit, storage
from app.services.erp_articulos import buscar_articulos
from app.services.erp_ir import resolver_codsar_por_codart

router = APIRouter(prefix="/api/maestros", tags=["Datos Maestros"])


# ── Helpers internos ─────────────────────────────────────────────

def _insertar_especificacion(
    cursor, *, erp_IdM21: int, erp_CODART: str, erp_DESART: str, tipo_material: str,
    cantidad_muestra: Optional[float], unidad_muestra: Optional[str],
    version: str, user_id: int,
    cantidad_contramuestra: Optional[float] = None, unidad_contramuestra: Optional[str] = None,
    accion_terapeutica: Optional[str] = None, sinonimia: Optional[str] = None,
    nro_cas: Optional[str] = None, nombre_quimico: Optional[str] = None,
    formula_molecular: Optional[str] = None, peso_molecular: Optional[str] = None,
    envasado_almacenamiento: Optional[str] = None, erp_codsar: Optional[str] = None,
) -> int:
    cursor.execute(
        """
        INSERT INTO lims_especificaciones
            (erp_IdM21, erp_CODART, erp_DESART, tipo_material, cantidad_muestra, unidad_muestra,
             cantidad_contramuestra, unidad_contramuestra,
             version, vigente, id_usuario_carga, accion_terapeutica, sinonimia, nro_cas,
             nombre_quimico, formula_molecular, peso_molecular, envasado_almacenamiento, erp_codsar)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        erp_IdM21, erp_CODART, erp_DESART, tipo_material, cantidad_muestra, unidad_muestra,
        cantidad_contramuestra, unidad_contramuestra, version, user_id,
        accion_terapeutica, sinonimia, nro_cas, nombre_quimico, formula_molecular, peso_molecular,
        envasado_almacenamiento, erp_codsar,
    )
    cursor.execute("SELECT @@IDENTITY AS id")
    return int(cursor.fetchone().id)


def _tiene_columna_analito(cursor) -> bool:
    """analito en lims_especificacion_ensayos puede no existir todavía (ver
    migrations_especificacion_ensayos_analito.sql, pendiente de ejecutar en
    algunos entornos) -- se chequea en catálogo antes de usarla en un
    INSERT/UPDATE explícito para no romper la consulta con un error de
    compilación SQL. En los SELECT no hace falta este chequeo porque se
    lee con getattr(fila, 'analito', None)."""
    cursor.execute("SELECT COL_LENGTH('lims_especificacion_ensayos', 'analito') AS c")
    return cursor.fetchone().c is not None


def _copiar_ensayos_especificacion(cursor, *, id_especificacion_origen: int, id_especificacion_destino: int) -> None:
    """Usado por 'revisar': la nueva versión arranca con los mismos ensayos que
    la versión anterior; el usuario los ajusta después desde la ficha de la
    nueva especificación (agregar/editar/quitar), igual que cantidad_muestra."""
    cursor.execute(
        "SELECT * FROM lims_especificacion_ensayos WHERE id_especificacion = ? ORDER BY orden",
        id_especificacion_origen,
    )
    filas = cursor.fetchall()
    tiene_analito = _tiene_columna_analito(cursor)
    for e in filas:
        if tiene_analito:
            cursor.execute(
                """
                INSERT INTO lims_especificacion_ensayos
                    (id_especificacion, id_ensayo_maestro, orden, etapa, metodologia, tipo_dato,
                     limite_inferior, limite_superior, unidad_medida, valor_requerido,
                     especificacion_texto, obligatorio, requerido_por_defecto, id_laboratorio, analito)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                id_especificacion_destino, e.id_ensayo_maestro, e.orden, e.etapa, e.metodologia, e.tipo_dato,
                e.limite_inferior, e.limite_superior, e.unidad_medida, e.valor_requerido,
                e.especificacion_texto, e.obligatorio, e.requerido_por_defecto, e.id_laboratorio,
                getattr(e, "analito", None),
            )
        else:
            cursor.execute(
                """
                INSERT INTO lims_especificacion_ensayos
                    (id_especificacion, id_ensayo_maestro, orden, etapa, metodologia, tipo_dato,
                     limite_inferior, limite_superior, unidad_medida, valor_requerido,
                     especificacion_texto, obligatorio, requerido_por_defecto, id_laboratorio)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                id_especificacion_destino, e.id_ensayo_maestro, e.orden, e.etapa, e.metodologia, e.tipo_dato,
                e.limite_inferior, e.limite_superior, e.unidad_medida, e.valor_requerido,
                e.especificacion_texto, e.obligatorio, e.requerido_por_defecto, e.id_laboratorio,
            )


def _obtener_bloques_config(cursor, erp_codsar: Optional[str]) -> dict:
    """Qué bloques mostrar en la ficha de una especificación, según
    lims_erp_subarticulo_config -- todos True (no ocultar nada) si
    erp_codsar es NULL (sin resolver contra el ERP todavía) o si no hay
    ninguna fila de config activa para ese subarticulo, para no esconder
    datos ya cargados de especificaciones que no se pudieron vincular."""
    bloques = {
        "incluye_bloque_muestras": True,
        "incluye_bloque_analisis_laboratorio": True,
        "incluye_bloque_muestreo_fisico": True,
        "incluye_bloque_testigos": True,
    }
    if not erp_codsar:
        return bloques
    cursor.execute(
        """
        SELECT incluye_bloque_muestras, incluye_bloque_analisis_laboratorio,
               incluye_bloque_muestreo_fisico, incluye_bloque_testigos
        FROM lims_erp_subarticulo_config
        WHERE erp_codsar = ? AND activo = 1
        """,
        erp_codsar,
    )
    fila = cursor.fetchone()
    if not fila:
        return bloques
    return {
        "incluye_bloque_muestras": bool(fila.incluye_bloque_muestras),
        "incluye_bloque_analisis_laboratorio": bool(fila.incluye_bloque_analisis_laboratorio),
        "incluye_bloque_muestreo_fisico": bool(fila.incluye_bloque_muestreo_fisico),
        "incluye_bloque_testigos": bool(fila.incluye_bloque_testigos),
    }


def _fila_a_especificacion(row, tiene_muestras: bool = False, tiene_testigos: bool = False) -> EspecificacionResponse:
    return EspecificacionResponse(
        id_especificacion=row.id_especificacion,
        erp_IdM21=row.erp_IdM21,
        erp_CODART=row.erp_CODART,
        erp_DESART=row.erp_DESART,
        tipo_material=row.tipo_material,
        erp_codsar=getattr(row, "erp_codsar", None),
        cantidad_muestra=float(row.cantidad_muestra) if row.cantidad_muestra is not None else None,
        unidad_muestra=row.unidad_muestra,
        cantidad_contramuestra=float(row.cantidad_contramuestra) if row.cantidad_contramuestra is not None else None,
        unidad_contramuestra=row.unidad_contramuestra,
        version=row.version,
        vigente=bool(row.vigente),
        id_usuario_carga=row.id_usuario_carga,
        fecha_carga=row.fecha_carga,
        tiene_muestras=tiene_muestras,
        tiene_testigos=tiene_testigos,
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
        etapa=e.etapa,
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
        analito=getattr(e, "analito", None),
    )


def _obtener_especificacion_detalle(cursor, id_especificacion: int) -> EspecificacionDetalle:
    cursor.execute("SELECT * FROM lims_especificaciones WHERE id_especificacion = ?", id_especificacion)
    row = cursor.fetchone()

    cursor.execute(
        _SELECT_ESPECIFICACION_ENSAYOS + " WHERE se.id_especificacion = ? AND se.activo = 1 ORDER BY se.orden",
        id_especificacion,
    )
    ensayos = [_fila_a_especificacion_ensayo(e) for e in cursor.fetchall()]

    base = _fila_a_especificacion(row)
    bloques = _obtener_bloques_config(cursor, base.erp_codsar)
    return EspecificacionDetalle(**base.model_dump(), ensayos=ensayos, **bloques)


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


def _tiene_columna_lab_testigo(cursor) -> bool:
    """id_laboratorio en lims_testigos puede no existir todavía (ver
    migrations_testigos_laboratorio.sql, pendiente de ejecutar en algunos
    entornos) -- se chequea en catálogo antes de armar el JOIN para no
    romper la consulta con un error de compilación SQL."""
    cursor.execute("SELECT COL_LENGTH('lims_testigos', 'id_laboratorio') AS c")
    return cursor.fetchone().c is not None


def _tiene_tabla_testigo_laboratorios(cursor) -> bool:
    """lims_testigo_laboratorios (relación muchos a muchos testigo-laboratorio)
    puede no existir todavía (ver migrations_testigo_laboratorios_m2m.sql,
    pendiente de ejecutar en algunos entornos)."""
    cursor.execute("SELECT OBJECT_ID('lims_testigo_laboratorios', 'U') AS id")
    return cursor.fetchone().id is not None


def _tiene_columna_fecha_envio_real(cursor) -> bool:
    """fecha_envio_real en lims_testigo_laboratorios puede no existir todavía
    (ver migrations_testigo_laboratorios_fecha_envio_real.sql, pendiente de
    ejecutar en algunos entornos) -- se chequea antes de usarla en un
    INSERT/UPDATE/SELECT explícito para no romper la consulta con un error
    de compilación SQL."""
    cursor.execute("SELECT COL_LENGTH('lims_testigo_laboratorios', 'fecha_envio_real') AS c")
    return cursor.fetchone().c is not None


def _laboratorios_de_testigo(cursor, id_testigo: int) -> list[LaboratorioAsignado]:
    if not _tiene_tabla_testigo_laboratorios(cursor):
        return []
    columna_fecha = "tl.fecha_envio_real" if _tiene_columna_fecha_envio_real(cursor) else "NULL AS fecha_envio_real"
    cursor.execute(
        f"""
        SELECT lab.id_laboratorio, lab.nombre, tl.consumo_estimado, tl.unidad_consumo, {columna_fecha}
        FROM lims_testigo_laboratorios tl
        JOIN lims_laboratorios lab ON lab.id_laboratorio = tl.id_laboratorio
        WHERE tl.id_testigo = ?
        ORDER BY lab.nombre
        """,
        id_testigo,
    )
    return [
        LaboratorioAsignado(
            id_laboratorio=r.id_laboratorio,
            nombre=r.nombre,
            consumo_estimado=float(r.consumo_estimado) if r.consumo_estimado is not None else None,
            unidad_consumo=r.unidad_consumo,
            fecha_envio_real=r.fecha_envio_real,
        )
        for r in cursor.fetchall()
    ]


def _select_testigos_sql(cursor) -> str:
    """Alias 't' consistente en todas las ramas para que el WHERE/ORDER BY
    apendeado después (con o sin el JOIN de laboratorio) sea siempre válido.
    Los JOIN de categoría (lims_testigo_categorias) y origen
    (lims_testigo_origenes) sí están siempre disponibles -- a diferencia de
    id_laboratorio, esas columnas ya existen en todos los entornos."""
    if _tiene_columna_lab_testigo(cursor):
        return (
            "SELECT t.*, lab.nombre AS laboratorio_nombre, cat.nombre AS categoria_nombre, "
            "org.nombre AS origen_nombre FROM lims_testigos t "
            "LEFT JOIN lims_laboratorios lab ON lab.id_laboratorio = t.id_laboratorio "
            "LEFT JOIN lims_testigo_categorias cat ON cat.id_categoria = t.id_categoria "
            "LEFT JOIN lims_testigo_origenes org ON org.id_origen = t.id_origen "
        )
    return (
        "SELECT t.*, cat.nombre AS categoria_nombre, org.nombre AS origen_nombre FROM lims_testigos t "
        "LEFT JOIN lims_testigo_categorias cat ON cat.id_categoria = t.id_categoria "
        "LEFT JOIN lims_testigo_origenes org ON org.id_origen = t.id_origen "
    )


ESTADOS_TESTIGO_VALIDOS = {"vencido", "por_vencer", "normal", "sin_vencimiento", "stock_bajo"}


_ESTADOS_VENCIMIENTO = {"vencido", "por_vencer", "normal", "sin_vencimiento"}


def _cumple_filtro_estado_testigo(t: TestigoResponse, estados_pedidos: set) -> bool:
    """stock_bajo es un eje independiente del vencimiento, no un estado más
    dentro del mismo OR -- se combina con AND sobre el resultado de los
    estados de vencimiento seleccionados (que sí se combinan entre sí con
    OR). Ej.: {'vencido','stock_bajo'} -> vencido Y stock_bajo (intersección),
    no vencido O stock_bajo. Si solo se pide 'stock_bajo', no hay restricción
    de vencimiento; si no se pide, no hay restricción de stock."""
    estados_venc_pedidos = estados_pedidos & _ESTADOS_VENCIMIENTO
    if not estados_venc_pedidos:
        cumple_vencimiento = True
    else:
        cumple_vencimiento = (
            ("vencido" in estados_venc_pedidos and t.vencido)
            or ("por_vencer" in estados_venc_pedidos and t.por_vencer)
            or ("normal" in estados_venc_pedidos and t.fecha_vencimiento is not None and not t.vencido and not t.por_vencer)
            or ("sin_vencimiento" in estados_venc_pedidos and t.fecha_vencimiento is None)
        )

    if "stock_bajo" in estados_pedidos:
        cumple_stock = t.stock_bajo
    else:
        cumple_stock = True

    return cumple_vencimiento and cumple_stock


def _fila_a_testigo(row, fecha_ref: Optional[date] = None, dias_anticipacion: int = 30, cursor=None) -> TestigoResponse:
    hoy = fecha_ref or date.today()
    fecha_vencimiento = _a_fecha(row.fecha_vencimiento)
    # Sin fecha de vencimiento cargada, no se puede considerar vencido ni
    # próximo a vencer.
    vencido = fecha_vencimiento is not None and fecha_vencimiento < hoy
    por_vencer = (
        fecha_vencimiento is not None and not vencido
        and (fecha_vencimiento - hoy).days <= dias_anticipacion
    )
    stock_bajo = float(row.stock_actual) <= float(row.stock_minimo)
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
        id_laboratorio=getattr(row, "id_laboratorio", None),
        laboratorio_nombre=getattr(row, "laboratorio_nombre", None),
        laboratorios=_laboratorios_de_testigo(cursor, row.id_testigo) if cursor is not None else [],
        id_origen=getattr(row, "id_origen", None),
        origen_nombre=getattr(row, "origen_nombre", None),
        id_categoria=getattr(row, "id_categoria", None),
        categoria_nombre=getattr(row, "categoria_nombre", None),
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
    erp: pyodbc.Connection = Depends(erp_db),
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

    # Vínculo al subarticulo real del ERP -- determina qué bloques se
    # muestran en la ficha (ver lims_erp_subarticulo_config). Si no se
    # encuentra en el ERP (dato de prueba, artículo discontinuado), queda
    # NULL y la ficha muestra todos los bloques por defecto.
    erp_codsar = resolver_codsar_por_codart(erp, body.erp_CODART)

    id_especificacion = _insertar_especificacion(
        cursor,
        erp_IdM21=body.erp_IdM21, erp_CODART=body.erp_CODART, erp_DESART=body.erp_DESART,
        tipo_material=body.tipo_material,
        cantidad_muestra=body.cantidad_muestra, unidad_muestra=body.unidad_muestra,
        cantidad_contramuestra=body.cantidad_contramuestra, unidad_contramuestra=body.unidad_contramuestra,
        version="1.0", user_id=user["id_usuario"], erp_codsar=erp_codsar,
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
    tipo_material: Optional[str] = Query(None, pattern=r"^(materia_prima|granel|semi_elaborado|producto_terminado|material_empaque)$"),
    user: dict = Depends(get_current_user),
    conn: pyodbc.Connection = Depends(limss_db),
):
    cursor = conn.cursor()
    like = f"%{buscar}%"
    condiciones = ["(e.erp_CODART LIKE ? OR e.erp_DESART LIKE ?)"]
    params: list = [like, like]
    if vigente is not None:
        condiciones.append("e.vigente = ?")
        params.append(1 if vigente else 0)
    if tipo_material:
        condiciones.append("e.tipo_material = ?")
        params.append(tipo_material)

    cursor.execute(
        f"""
        SELECT e.*,
               CASE WHEN EXISTS (
                   SELECT 1 FROM lims_especificacion_muestras m WHERE m.id_especificacion = e.id_especificacion
               ) THEN 1 ELSE 0 END AS tiene_muestras,
               CASE WHEN EXISTS (
                   SELECT 1 FROM lims_especificacion_testigos t WHERE t.id_especificacion = e.id_especificacion
               ) THEN 1 ELSE 0 END AS tiene_testigos
        FROM lims_especificaciones e
        WHERE {" AND ".join(condiciones)}
        ORDER BY e.erp_DESART, e.version DESC
        """,
        *params,
    )
    return [
        _fila_a_especificacion(r, tiene_muestras=bool(r.tiene_muestras), tiene_testigos=bool(r.tiene_testigos))
        for r in cursor.fetchall()
    ]


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
        cantidad_contramuestra=actual.cantidad_contramuestra, unidad_contramuestra=actual.unidad_contramuestra,
        version=version_nueva, user_id=user["id_usuario"],
        # Mismo artículo que la versión anterior -- se copia el erp_codsar ya
        # resuelto en vez de volver a consultar el ERP.
        erp_codsar=getattr(actual, "erp_codsar", None),
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
    erp: pyodbc.Connection = Depends(erp_db),
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

    # El artículo puede ser distinto al original (ver docstring) -- se
    # resuelve el subarticulo de nuevo contra el ERP, no se copia el del
    # original.
    erp_codsar = resolver_codsar_por_codart(erp, body.erp_CODART)

    id_nueva = _insertar_especificacion(
        cursor,
        erp_IdM21=body.erp_IdM21, erp_CODART=body.erp_CODART, erp_DESART=body.erp_DESART,
        tipo_material=body.tipo_material,
        cantidad_muestra=original.cantidad_muestra, unidad_muestra=original.unidad_muestra,
        cantidad_contramuestra=original.cantidad_contramuestra, unidad_contramuestra=original.unidad_contramuestra,
        version=body.version, user_id=user["id_usuario"],
        accion_terapeutica=original.accion_terapeutica, sinonimia=original.sinonimia,
        nro_cas=original.nro_cas, nombre_quimico=original.nombre_quimico,
        formula_molecular=original.formula_molecular, peso_molecular=original.peso_molecular,
        envasado_almacenamiento=original.envasado_almacenamiento, erp_codsar=erp_codsar,
    )
    _copiar_ensayos_especificacion(cursor, id_especificacion_origen=id_especificacion, id_especificacion_destino=id_nueva)

    audit.registrar(
        conn, entidad="especificacion", accion="copiar",
        id_usuario=user["id_usuario"], id_entidad=id_nueva,
        valor_anterior={"id_especificacion": id_especificacion, "erp_CODART": original.erp_CODART},
        valor_nuevo={"id_especificacion": id_nueva, "erp_CODART": body.erp_CODART, "tipo_material": body.tipo_material},
    )

    return _obtener_especificacion_detalle(cursor, id_nueva)


@router.put("/especificaciones/{id_especificacion}/cantidades", response_model=EspecificacionResponse)
def editar_cantidades_especificacion(
    id_especificacion: int,
    body: EspecificacionCantidades,
    user: dict = Depends(require_rol("analista_qc", "admin", "qa")),
    conn: pyodbc.Connection = Depends(limss_db),
):
    """Actualiza solo las cantidades de muestreo (análisis y contramuestra)
    de una especificación ya creada, sin necesidad de revisar (nueva versión)
    -- son datos logísticos para la Solicitud de Muestreo, no parte del
    contenido analítico versionado (límites/ensayos), así que se pueden
    completar/corregir en cualquier momento, incluso en una especificación
    obsoleta (por si hace falta reconstruir una solicitud vieja)."""
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM lims_especificaciones WHERE id_especificacion = ?", id_especificacion)
    row = cursor.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Especificación no encontrada")

    cursor.execute(
        """
        UPDATE lims_especificaciones
        SET cantidad_muestra = ?, unidad_muestra = ?, cantidad_contramuestra = ?, unidad_contramuestra = ?
        WHERE id_especificacion = ?
        """,
        body.cantidad_muestra, body.unidad_muestra, body.cantidad_contramuestra, body.unidad_contramuestra,
        id_especificacion,
    )

    audit.registrar(
        conn, entidad="especificacion", accion="modificar_cantidades",
        id_usuario=user["id_usuario"], id_entidad=id_especificacion,
        valor_anterior={
            "cantidad_muestra": float(row.cantidad_muestra) if row.cantidad_muestra is not None else None,
            "unidad_muestra": row.unidad_muestra,
            "cantidad_contramuestra": float(row.cantidad_contramuestra) if row.cantidad_contramuestra is not None else None,
            "unidad_contramuestra": row.unidad_contramuestra,
        },
        valor_nuevo=body.model_dump(),
    )

    cursor.execute("SELECT * FROM lims_especificaciones WHERE id_especificacion = ?", id_especificacion)
    return _fila_a_especificacion(cursor.fetchone())


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
        _SELECT_ESPECIFICACION_ENSAYOS + " WHERE se.id_especificacion = ? AND se.activo = 1 ORDER BY se.orden",
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

    if _tiene_columna_analito(cursor):
        cursor.execute(
            """
            INSERT INTO lims_especificacion_ensayos
                (id_especificacion, id_ensayo_maestro, orden, etapa, metodologia, tipo_dato,
                 limite_inferior, limite_superior, unidad_medida, valor_requerido,
                 especificacion_texto, obligatorio, requerido_por_defecto, id_laboratorio, analito)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            id_especificacion, body.id_ensayo_maestro, body.orden, body.etapa, body.metodologia, body.tipo_dato,
            body.limite_inferior, body.limite_superior, body.unidad_medida, body.valor_requerido,
            body.especificacion_texto, 1 if body.obligatorio else 0, 1 if body.requerido_por_defecto else 0,
            body.id_laboratorio, body.analito,
        )
    else:
        cursor.execute(
            """
            INSERT INTO lims_especificacion_ensayos
                (id_especificacion, id_ensayo_maestro, orden, etapa, metodologia, tipo_dato,
                 limite_inferior, limite_superior, unidad_medida, valor_requerido,
                 especificacion_texto, obligatorio, requerido_por_defecto, id_laboratorio)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            id_especificacion, body.id_ensayo_maestro, body.orden, body.etapa, body.metodologia, body.tipo_dato,
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

    if _tiene_columna_analito(cursor):
        cursor.execute(
            """
            UPDATE lims_especificacion_ensayos
            SET id_ensayo_maestro = ?, orden = ?, etapa = ?, metodologia = ?, tipo_dato = ?,
                limite_inferior = ?, limite_superior = ?, unidad_medida = ?, valor_requerido = ?,
                especificacion_texto = ?, obligatorio = ?, requerido_por_defecto = ?, id_laboratorio = ?,
                analito = ?
            WHERE id_espec_ensayo = ?
            """,
            body.id_ensayo_maestro, body.orden, body.etapa, body.metodologia, body.tipo_dato,
            body.limite_inferior, body.limite_superior, body.unidad_medida, body.valor_requerido,
            body.especificacion_texto, 1 if body.obligatorio else 0, 1 if body.requerido_por_defecto else 0,
            body.id_laboratorio, body.analito, id_espec_ensayo,
        )
    else:
        cursor.execute(
            """
            UPDATE lims_especificacion_ensayos
            SET id_ensayo_maestro = ?, orden = ?, etapa = ?, metodologia = ?, tipo_dato = ?,
                limite_inferior = ?, limite_superior = ?, unidad_medida = ?, valor_requerido = ?,
                especificacion_texto = ?, obligatorio = ?, requerido_por_defecto = ?, id_laboratorio = ?
            WHERE id_espec_ensayo = ?
            """,
            body.id_ensayo_maestro, body.orden, body.etapa, body.metodologia, body.tipo_dato,
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
        "UPDATE lims_especificacion_ensayos SET activo = 0 WHERE id_espec_ensayo = ? AND id_especificacion = ?",
        id_espec_ensayo, id_especificacion,
    )
    if cursor.rowcount == 0:
        raise HTTPException(status_code=404, detail="El ensayo no pertenece a esta especificación")

    audit.registrar(
        conn, entidad="especificacion_ensayo", accion="eliminar",
        id_usuario=user["id_usuario"], id_entidad=id_espec_ensayo,
        valor_anterior={"id_especificacion": id_especificacion},
    )


# ── Muestras definidas por especificación ─────────────────────────
#
# Reemplaza a los campos simples cantidad_muestra/unidad_muestra/cantidad_
# contramuestra/unidad_contramuestra de lims_especificaciones (deprecados,
# no se tocan): una especificación puede tener varias muestras, cada una
# con su propio laboratorio de destino.

_SELECT_ESPECIFICACION_MUESTRAS = """
    SELECT m.*, lab.nombre AS laboratorio_nombre
    FROM lims_especificacion_muestras m
    LEFT JOIN lims_laboratorios lab ON lab.id_laboratorio = m.id_laboratorio
"""


def _fila_a_espec_muestra(row) -> EspecificacionMuestraResponse:
    return EspecificacionMuestraResponse(
        id=row.id,
        id_especificacion=row.id_especificacion,
        tipo_muestra=row.tipo_muestra,
        cantidad=float(row.cantidad),
        unidad=row.unidad,
        genera_etiqueta=bool(row.genera_etiqueta),
        id_laboratorio=row.id_laboratorio,
        laboratorio_nombre=row.laboratorio_nombre,
        orden=row.orden,
    )


@router.get("/especificaciones/{id_especificacion}/muestras", response_model=list[EspecificacionMuestraResponse])
def listar_muestras_especificacion(
    id_especificacion: int,
    user: dict = Depends(get_current_user),
    conn: pyodbc.Connection = Depends(limss_db),
):
    cursor = conn.cursor()
    cursor.execute("SELECT 1 FROM lims_especificaciones WHERE id_especificacion = ?", id_especificacion)
    if not cursor.fetchone():
        raise HTTPException(status_code=404, detail="Especificación no encontrada")

    cursor.execute(
        _SELECT_ESPECIFICACION_MUESTRAS + " WHERE m.id_especificacion = ? ORDER BY m.orden",
        id_especificacion,
    )
    return [_fila_a_espec_muestra(r) for r in cursor.fetchall()]


@router.post("/especificaciones/{id_especificacion}/muestras", response_model=EspecificacionMuestraResponse, status_code=201)
def crear_muestra_especificacion(
    id_especificacion: int,
    body: EspecificacionMuestraCreate,
    user: dict = Depends(require_rol("analista_qc", "admin", "qa")),
    conn: pyodbc.Connection = Depends(limss_db),
):
    cursor = conn.cursor()
    cursor.execute("SELECT 1 FROM lims_especificaciones WHERE id_especificacion = ?", id_especificacion)
    if not cursor.fetchone():
        raise HTTPException(status_code=404, detail="Especificación no encontrada")

    if body.id_laboratorio is not None:
        cursor.execute("SELECT 1 FROM lims_laboratorios WHERE id_laboratorio = ? AND activo = 1", body.id_laboratorio)
        if not cursor.fetchone():
            raise HTTPException(status_code=404, detail="El laboratorio indicado no existe o está inactivo")

    cursor.execute(
        "SELECT ISNULL(MAX(orden), 0) AS m FROM lims_especificacion_muestras WHERE id_especificacion = ?",
        id_especificacion,
    )
    orden = cursor.fetchone().m + 1

    try:
        cursor.execute(
            """
            INSERT INTO lims_especificacion_muestras
                (id_especificacion, tipo_muestra, cantidad, unidad, genera_etiqueta, id_laboratorio, orden)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            id_especificacion, body.tipo_muestra, body.cantidad, body.unidad,
            1 if body.genera_etiqueta else 0, body.id_laboratorio, orden,
        )
    except pyodbc.IntegrityError:
        raise HTTPException(
            status_code=400,
            detail="No se pudo guardar la muestra: el tipo 'testigo' todavía no está habilitado en la base "
                   "de datos (falta aplicar migrations_especificacion_muestras_tipo_testigo.sql).",
        )
    cursor.execute("SELECT @@IDENTITY AS id")
    id_muestra = int(cursor.fetchone().id)

    audit.registrar(
        conn, entidad="especificacion_muestra", accion="crear",
        id_usuario=user["id_usuario"], id_entidad=id_muestra,
        valor_nuevo={"id_especificacion": id_especificacion, "tipo_muestra": body.tipo_muestra, "cantidad": body.cantidad},
    )

    cursor.execute(_SELECT_ESPECIFICACION_MUESTRAS + " WHERE m.id = ?", id_muestra)
    return _fila_a_espec_muestra(cursor.fetchone())


@router.put("/especificaciones/{id_especificacion}/muestras/{id_muestra}", response_model=EspecificacionMuestraResponse)
def editar_muestra_especificacion(
    id_especificacion: int,
    id_muestra: int,
    body: EspecificacionMuestraCreate,
    user: dict = Depends(require_rol("analista_qc", "admin", "qa")),
    conn: pyodbc.Connection = Depends(limss_db),
):
    cursor = conn.cursor()
    cursor.execute(
        "SELECT * FROM lims_especificacion_muestras WHERE id = ? AND id_especificacion = ?",
        id_muestra, id_especificacion,
    )
    row = cursor.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="La muestra no pertenece a esta especificación")

    if body.id_laboratorio is not None:
        cursor.execute("SELECT 1 FROM lims_laboratorios WHERE id_laboratorio = ? AND activo = 1", body.id_laboratorio)
        if not cursor.fetchone():
            raise HTTPException(status_code=404, detail="El laboratorio indicado no existe o está inactivo")

    try:
        cursor.execute(
            """
            UPDATE lims_especificacion_muestras
            SET tipo_muestra = ?, cantidad = ?, unidad = ?, genera_etiqueta = ?, id_laboratorio = ?
            WHERE id = ?
            """,
            body.tipo_muestra, body.cantidad, body.unidad, 1 if body.genera_etiqueta else 0, body.id_laboratorio,
            id_muestra,
        )
    except pyodbc.IntegrityError:
        raise HTTPException(
            status_code=400,
            detail="No se pudo guardar la muestra: el tipo 'testigo' todavía no está habilitado en la base "
                   "de datos (falta aplicar migrations_especificacion_muestras_tipo_testigo.sql).",
        )

    audit.registrar(
        conn, entidad="especificacion_muestra", accion="modificar",
        id_usuario=user["id_usuario"], id_entidad=id_muestra,
        valor_anterior={"tipo_muestra": row.tipo_muestra, "cantidad": float(row.cantidad), "unidad": row.unidad},
        valor_nuevo={"tipo_muestra": body.tipo_muestra, "cantidad": body.cantidad, "unidad": body.unidad},
    )

    cursor.execute(_SELECT_ESPECIFICACION_MUESTRAS + " WHERE m.id = ?", id_muestra)
    return _fila_a_espec_muestra(cursor.fetchone())


@router.delete("/especificaciones/{id_especificacion}/muestras/{id_muestra}", status_code=204)
def eliminar_muestra_especificacion(
    id_especificacion: int,
    id_muestra: int,
    user: dict = Depends(require_rol("qa", "admin")),
    conn: pyodbc.Connection = Depends(limss_db),
):
    cursor = conn.cursor()
    cursor.execute(
        "SELECT 1 FROM lims_especificacion_muestras WHERE id = ? AND id_especificacion = ?",
        id_muestra, id_especificacion,
    )
    if not cursor.fetchone():
        raise HTTPException(status_code=404, detail="La muestra no pertenece a esta especificación")

    # lims_solicitud_muestras puede no existir todavía en este entorno (ver
    # migrations_solicitud_muestras.sql) -- si no existe, no hay nada que
    # pueda estar referenciando esta fila, así que se permite eliminar.
    cursor.execute("SELECT OBJECT_ID('lims_solicitud_muestras') AS oid")
    if cursor.fetchone().oid is not None:
        cursor.execute(
            """
            SELECT COUNT(*) AS n
            FROM lims_solicitud_muestras sm
            INNER JOIN lims_solicitudes_muestreo s ON s.id_solicitud = sm.id_solicitud
            WHERE sm.id_espec_muestra = ? AND s.estado = 'pendiente'
            """,
            id_muestra,
        )
        if cursor.fetchone().n > 0:
            raise HTTPException(
                status_code=400,
                detail="No se puede eliminar: tiene solicitudes de muestreo activas referenciándola",
            )

    cursor.execute("DELETE FROM lims_especificacion_muestras WHERE id = ?", id_muestra)

    audit.registrar(
        conn, entidad="especificacion_muestra", accion="eliminar",
        id_usuario=user["id_usuario"], id_entidad=id_muestra,
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

    cursor.execute("SELECT * FROM lims_testigos WHERE id_testigo = ?", body.id_testigo)
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

    t = _fila_a_testigo(testigo)
    return EspecificacionTestigoResponse(
        id=id_rel, id_especificacion=id_especificacion, id_testigo=body.id_testigo,
        codigo=t.codigo, nombre=t.nombre,
        fecha_vencimiento=t.fecha_vencimiento, stock_actual=t.stock_actual, unidad_medida=t.unidad_medida,
        vencido=t.vencido, por_vencer=t.por_vencer,
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
        SELECT et.id AS id_relacion, et.id_especificacion, t.*
        FROM lims_especificacion_testigos et
        INNER JOIN lims_testigos t ON t.id_testigo = et.id_testigo
        WHERE et.id_especificacion = ?
        ORDER BY t.codigo
        """,
        id_especificacion,
    )
    resultado = []
    for r in cursor.fetchall():
        t = _fila_a_testigo(r)
        resultado.append(EspecificacionTestigoResponse(
            id=r.id_relacion, id_especificacion=r.id_especificacion, id_testigo=t.id_testigo,
            codigo=t.codigo, nombre=t.nombre,
            fecha_vencimiento=t.fecha_vencimiento, stock_actual=t.stock_actual, unidad_medida=t.unidad_medida,
            vencido=t.vencido, por_vencer=t.por_vencer,
        ))
    return resultado


# ── Categorías de testigos ─────────────────────────────────────────

def _fila_a_categoria_testigo(row) -> TestigoCategoriaResponse:
    return TestigoCategoriaResponse(
        id_categoria=row.id_categoria, codigo=row.codigo, nombre=row.nombre, activo=bool(row.activo),
    )


@router.get("/testigo-categorias", response_model=list[TestigoCategoriaResponse])
def listar_categorias_testigo(
    activo: Optional[bool] = Query(None, description="true=solo activas, false=solo inactivas, omitir=todas"),
    user: dict = Depends(get_current_user),
    conn: pyodbc.Connection = Depends(limss_db),
):
    cursor = conn.cursor()
    if activo is None:
        cursor.execute("SELECT * FROM lims_testigo_categorias ORDER BY nombre")
    else:
        cursor.execute("SELECT * FROM lims_testigo_categorias WHERE activo = ? ORDER BY nombre", 1 if activo else 0)
    return [_fila_a_categoria_testigo(r) for r in cursor.fetchall()]


@router.post("/testigo-categorias", response_model=TestigoCategoriaResponse, status_code=201)
def crear_categoria_testigo(
    body: TestigoCategoriaCreate,
    user: dict = Depends(require_rol("admin")),
    conn: pyodbc.Connection = Depends(limss_db),
):
    cursor = conn.cursor()
    cursor.execute("SELECT 1 FROM lims_testigo_categorias WHERE codigo = ?", body.codigo)
    if cursor.fetchone():
        raise HTTPException(status_code=409, detail=f"El código '{body.codigo}' ya existe")

    cursor.execute(
        "INSERT INTO lims_testigo_categorias (codigo, nombre) VALUES (?, ?)",
        body.codigo, body.nombre,
    )
    cursor.execute("SELECT @@IDENTITY AS id")
    id_categoria = int(cursor.fetchone().id)

    audit.registrar(
        conn, entidad="testigo_categoria", accion="crear",
        id_usuario=user["id_usuario"], id_entidad=id_categoria,
        valor_nuevo={"codigo": body.codigo, "nombre": body.nombre},
    )

    cursor.execute("SELECT * FROM lims_testigo_categorias WHERE id_categoria = ?", id_categoria)
    return _fila_a_categoria_testigo(cursor.fetchone())


@router.put("/testigo-categorias/{id_categoria}", response_model=TestigoCategoriaResponse)
def editar_categoria_testigo(
    id_categoria: int,
    body: TestigoCategoriaUpdate,
    user: dict = Depends(require_rol("admin")),
    conn: pyodbc.Connection = Depends(limss_db),
):
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM lims_testigo_categorias WHERE id_categoria = ?", id_categoria)
    row = cursor.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Categoría no encontrada")

    cursor.execute(
        "SELECT 1 FROM lims_testigo_categorias WHERE codigo = ? AND id_categoria != ?",
        body.codigo, id_categoria,
    )
    if cursor.fetchone():
        raise HTTPException(status_code=409, detail=f"El código '{body.codigo}' ya existe")

    campos_anteriores = {"codigo": row.codigo, "nombre": row.nombre, "activo": bool(row.activo)}
    campos_nuevos = {"codigo": body.codigo, "nombre": body.nombre, "activo": body.activo}

    cursor.execute(
        "UPDATE lims_testigo_categorias SET codigo = ?, nombre = ?, activo = ? WHERE id_categoria = ?",
        body.codigo, body.nombre, 1 if body.activo else 0, id_categoria,
    )

    audit.registrar(
        conn, entidad="testigo_categoria", accion="modificar",
        id_usuario=user["id_usuario"], id_entidad=id_categoria,
        valor_anterior=campos_anteriores, valor_nuevo=campos_nuevos,
    )

    cursor.execute("SELECT * FROM lims_testigo_categorias WHERE id_categoria = ?", id_categoria)
    return _fila_a_categoria_testigo(cursor.fetchone())


@router.delete("/testigo-categorias/{id_categoria}", status_code=204)
def eliminar_categoria_testigo(
    id_categoria: int,
    user: dict = Depends(require_rol("admin")),
    conn: pyodbc.Connection = Depends(limss_db),
):
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM lims_testigo_categorias WHERE id_categoria = ?", id_categoria)
    row = cursor.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Categoría no encontrada")

    cursor.execute("SELECT 1 FROM lims_testigos WHERE id_categoria = ?", id_categoria)
    if cursor.fetchone():
        raise HTTPException(
            status_code=400,
            detail="No se puede eliminar: hay testigos asociados a esta categoría. Podés desactivarla en su lugar.",
        )

    cursor.execute("DELETE FROM lims_testigo_categorias WHERE id_categoria = ?", id_categoria)

    audit.registrar(
        conn, entidad="testigo_categoria", accion="eliminar",
        id_usuario=user["id_usuario"], id_entidad=id_categoria,
        valor_anterior={"codigo": row.codigo, "nombre": row.nombre},
    )


# ── Orígenes de testigos ────────────────────────────────────────────

def _fila_a_origen_testigo(row) -> TestigoOrigenResponse:
    return TestigoOrigenResponse(
        id_origen=row.id_origen, codigo=row.codigo, nombre=row.nombre, activo=bool(row.activo),
    )


@router.get("/testigo-origenes", response_model=list[TestigoOrigenResponse])
def listar_origenes_testigo(
    activo: Optional[bool] = Query(None, description="true=solo activos, false=solo inactivos, omitir=todos"),
    user: dict = Depends(get_current_user),
    conn: pyodbc.Connection = Depends(limss_db),
):
    cursor = conn.cursor()
    if activo is None:
        cursor.execute("SELECT * FROM lims_testigo_origenes ORDER BY nombre")
    else:
        cursor.execute("SELECT * FROM lims_testigo_origenes WHERE activo = ? ORDER BY nombre", 1 if activo else 0)
    return [_fila_a_origen_testigo(r) for r in cursor.fetchall()]


@router.post("/testigo-origenes", response_model=TestigoOrigenResponse, status_code=201)
def crear_origen_testigo(
    body: TestigoOrigenCreate,
    user: dict = Depends(require_rol("admin")),
    conn: pyodbc.Connection = Depends(limss_db),
):
    cursor = conn.cursor()
    cursor.execute("SELECT 1 FROM lims_testigo_origenes WHERE codigo = ?", body.codigo)
    if cursor.fetchone():
        raise HTTPException(status_code=409, detail=f"El código '{body.codigo}' ya existe")

    cursor.execute(
        "INSERT INTO lims_testigo_origenes (codigo, nombre) VALUES (?, ?)",
        body.codigo, body.nombre,
    )
    cursor.execute("SELECT @@IDENTITY AS id")
    id_origen = int(cursor.fetchone().id)

    audit.registrar(
        conn, entidad="testigo_origen", accion="crear",
        id_usuario=user["id_usuario"], id_entidad=id_origen,
        valor_nuevo={"codigo": body.codigo, "nombre": body.nombre},
    )

    cursor.execute("SELECT * FROM lims_testigo_origenes WHERE id_origen = ?", id_origen)
    return _fila_a_origen_testigo(cursor.fetchone())


@router.put("/testigo-origenes/{id_origen}", response_model=TestigoOrigenResponse)
def editar_origen_testigo(
    id_origen: int,
    body: TestigoOrigenUpdate,
    user: dict = Depends(require_rol("admin")),
    conn: pyodbc.Connection = Depends(limss_db),
):
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM lims_testigo_origenes WHERE id_origen = ?", id_origen)
    row = cursor.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Origen no encontrado")

    cursor.execute(
        "SELECT 1 FROM lims_testigo_origenes WHERE codigo = ? AND id_origen != ?",
        body.codigo, id_origen,
    )
    if cursor.fetchone():
        raise HTTPException(status_code=409, detail=f"El código '{body.codigo}' ya existe")

    campos_anteriores = {"codigo": row.codigo, "nombre": row.nombre, "activo": bool(row.activo)}
    campos_nuevos = {"codigo": body.codigo, "nombre": body.nombre, "activo": body.activo}

    cursor.execute(
        "UPDATE lims_testigo_origenes SET codigo = ?, nombre = ?, activo = ? WHERE id_origen = ?",
        body.codigo, body.nombre, 1 if body.activo else 0, id_origen,
    )

    audit.registrar(
        conn, entidad="testigo_origen", accion="modificar",
        id_usuario=user["id_usuario"], id_entidad=id_origen,
        valor_anterior=campos_anteriores, valor_nuevo=campos_nuevos,
    )

    cursor.execute("SELECT * FROM lims_testigo_origenes WHERE id_origen = ?", id_origen)
    return _fila_a_origen_testigo(cursor.fetchone())


@router.delete("/testigo-origenes/{id_origen}", status_code=204)
def eliminar_origen_testigo(
    id_origen: int,
    user: dict = Depends(require_rol("admin")),
    conn: pyodbc.Connection = Depends(limss_db),
):
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM lims_testigo_origenes WHERE id_origen = ?", id_origen)
    row = cursor.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Origen no encontrado")

    cursor.execute("SELECT 1 FROM lims_testigos WHERE id_origen = ?", id_origen)
    if cursor.fetchone():
        raise HTTPException(
            status_code=400,
            detail="No se puede eliminar: hay testigos asociados a este origen. Podés desactivarlo en su lugar.",
        )

    cursor.execute("DELETE FROM lims_testigo_origenes WHERE id_origen = ?", id_origen)

    audit.registrar(
        conn, entidad="testigo_origen", accion="eliminar",
        id_usuario=user["id_usuario"], id_entidad=id_origen,
        valor_anterior={"codigo": row.codigo, "nombre": row.nombre},
    )


# ── Testigos y estándares ─────────────────────────────────────────

@router.post("/testigos", response_model=TestigoResponse, status_code=201)
def crear_testigo(
    codigo: str = Form(..., min_length=1, max_length=20),
    nombre: str = Form(..., min_length=1, max_length=150),
    nro_lote: str = Form(..., min_length=1, max_length=50),
    nro_ir: Optional[str] = Form(None, max_length=6),
    fecha_vencimiento: Optional[date] = Form(None, description="Opcional: dejar vacío si el testigo no vence"),
    stock_actual: float = Form(...),
    stock_minimo: float = Form(...),
    unidad_medida: Literal["mg", "ml"] = Form("mg"),
    id_origen: Optional[int] = Form(None),
    id_categoria: Optional[int] = Form(None),
    observaciones: Optional[str] = Form(None, max_length=500),
    id_laboratorio: Optional[int] = Form(None),
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

    if id_laboratorio is not None:
        cursor.execute("SELECT 1 FROM lims_laboratorios WHERE id_laboratorio = ? AND activo = 1", id_laboratorio)
        if not cursor.fetchone():
            raise HTTPException(status_code=404, detail="El laboratorio indicado no existe o está inactivo")

    if id_categoria is not None:
        cursor.execute("SELECT 1 FROM lims_testigo_categorias WHERE id_categoria = ? AND activo = 1", id_categoria)
        if not cursor.fetchone():
            raise HTTPException(status_code=404, detail="La categoría indicada no existe o está inactiva")

    if id_origen is not None:
        cursor.execute("SELECT 1 FROM lims_testigo_origenes WHERE id_origen = ? AND activo = 1", id_origen)
        if not cursor.fetchone():
            raise HTTPException(status_code=404, detail="El origen indicado no existe o está inactivo")

    ruta_pdf = None
    if pdf_certificado is not None and pdf_certificado.filename:
        ruta_pdf = storage.guardar_pdf_testigo(pdf_certificado, codigo)

    fecha_vencimiento_sql = str(fecha_vencimiento) if fecha_vencimiento else None

    tiene_lab = _tiene_columna_lab_testigo(cursor)
    if tiene_lab:
        cursor.execute(
            """
            INSERT INTO lims_testigos
                (codigo, nombre, nro_lote, nro_ir, fecha_vencimiento, stock_actual, stock_minimo,
                 unidad_medida, pdf_certificado, id_usuario_carga, observaciones, id_laboratorio, id_origen, id_categoria)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            codigo, nombre, nro_lote, nro_ir, fecha_vencimiento_sql, stock_actual, stock_minimo,
            unidad_medida, ruta_pdf, user["id_usuario"], observaciones, id_laboratorio, id_origen, id_categoria,
        )
    else:
        cursor.execute(
            """
            INSERT INTO lims_testigos
                (codigo, nombre, nro_lote, nro_ir, fecha_vencimiento, stock_actual, stock_minimo,
                 unidad_medida, pdf_certificado, id_usuario_carga, observaciones, id_origen, id_categoria)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            codigo, nombre, nro_lote, nro_ir, fecha_vencimiento_sql, stock_actual, stock_minimo,
            unidad_medida, ruta_pdf, user["id_usuario"], observaciones, id_origen, id_categoria,
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

    cursor.execute(_select_testigos_sql(cursor) + "WHERE t.id_testigo = ?", id_testigo)
    return _fila_a_testigo(cursor.fetchone(), cursor=cursor)


@router.put("/testigos/{id_testigo}", response_model=TestigoResponse)
def editar_testigo(
    id_testigo: int,
    nombre: str = Form(..., min_length=1, max_length=150),
    nro_lote: str = Form(..., min_length=1, max_length=50),
    nro_ir: Optional[str] = Form(None, max_length=6),
    fecha_vencimiento: Optional[date] = Form(None, description="Opcional: dejar vacío si el testigo no vence"),
    stock_minimo: float = Form(...),
    unidad_medida: Literal["mg", "ml"] = Form("mg"),
    id_origen: Optional[int] = Form(None),
    id_categoria: Optional[int] = Form(None),
    observaciones: Optional[str] = Form(None, max_length=500),
    id_laboratorio: Optional[int] = Form(None),
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
    tiene_lab = _tiene_columna_lab_testigo(cursor)
    cursor.execute("SELECT * FROM lims_testigos WHERE id_testigo = ?", id_testigo)
    row = cursor.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Testigo no encontrado")

    if tiene_lab and id_laboratorio is not None:
        cursor.execute("SELECT 1 FROM lims_laboratorios WHERE id_laboratorio = ? AND activo = 1", id_laboratorio)
        if not cursor.fetchone():
            raise HTTPException(status_code=404, detail="El laboratorio indicado no existe o está inactivo")

    if id_categoria is not None:
        cursor.execute("SELECT 1 FROM lims_testigo_categorias WHERE id_categoria = ? AND activo = 1", id_categoria)
        if not cursor.fetchone():
            raise HTTPException(status_code=404, detail="La categoría indicada no existe o está inactiva")

    if id_origen is not None:
        cursor.execute("SELECT 1 FROM lims_testigo_origenes WHERE id_origen = ? AND activo = 1", id_origen)
        if not cursor.fetchone():
            raise HTTPException(status_code=404, detail="El origen indicado no existe o está inactivo")

    ruta_pdf = row.pdf_certificado
    if pdf_certificado is not None:
        ruta_pdf = storage.guardar_pdf_testigo(pdf_certificado, row.codigo)

    fecha_vencimiento_sql = str(fecha_vencimiento) if fecha_vencimiento else None

    campos_anteriores = {
        "nombre": row.nombre, "nro_lote": row.nro_lote, "nro_ir": row.nro_ir,
        "fecha_vencimiento": str(row.fecha_vencimiento) if row.fecha_vencimiento else None,
        "stock_minimo": float(row.stock_minimo),
        "unidad_medida": row.unidad_medida, "observaciones": row.observaciones,
        "pdf_certificado": row.pdf_certificado,
        "id_origen": getattr(row, "id_origen", None), "id_categoria": getattr(row, "id_categoria", None),
    }
    campos_nuevos = {
        "nombre": nombre, "nro_lote": nro_lote, "nro_ir": nro_ir,
        "fecha_vencimiento": fecha_vencimiento_sql, "stock_minimo": stock_minimo,
        "unidad_medida": unidad_medida, "observaciones": observaciones,
        "pdf_certificado": ruta_pdf,
        "id_origen": id_origen, "id_categoria": id_categoria,
    }
    if tiene_lab:
        campos_anteriores["id_laboratorio"] = getattr(row, "id_laboratorio", None)
        campos_nuevos["id_laboratorio"] = id_laboratorio

    if tiene_lab:
        cursor.execute(
            """
            UPDATE lims_testigos
            SET nombre = ?, nro_lote = ?, nro_ir = ?, fecha_vencimiento = ?, stock_minimo = ?,
                unidad_medida = ?, observaciones = ?, pdf_certificado = ?, id_laboratorio = ?,
                id_origen = ?, id_categoria = ?
            WHERE id_testigo = ?
            """,
            nombre, nro_lote, nro_ir, fecha_vencimiento_sql, stock_minimo,
            unidad_medida, observaciones, ruta_pdf, id_laboratorio, id_origen, id_categoria, id_testigo,
        )
    else:
        cursor.execute(
            """
            UPDATE lims_testigos
            SET nombre = ?, nro_lote = ?, nro_ir = ?, fecha_vencimiento = ?, stock_minimo = ?,
                unidad_medida = ?, observaciones = ?, pdf_certificado = ?, id_origen = ?, id_categoria = ?
            WHERE id_testigo = ?
            """,
            nombre, nro_lote, nro_ir, fecha_vencimiento_sql, stock_minimo,
            unidad_medida, observaciones, ruta_pdf, id_origen, id_categoria, id_testigo,
        )

    valor_anterior = {k: v for k, v in campos_anteriores.items() if v != campos_nuevos[k]}
    valor_nuevo = {k: v for k, v in campos_nuevos.items() if v != campos_anteriores[k]}
    audit.registrar(
        conn, entidad="testigo", accion="modificar",
        id_usuario=user["id_usuario"], id_entidad=id_testigo,
        valor_anterior=valor_anterior or None, valor_nuevo=valor_nuevo or None,
    )

    cursor.execute(_select_testigos_sql(cursor) + "WHERE t.id_testigo = ?", id_testigo)
    return _fila_a_testigo(cursor.fetchone(), cursor=cursor)


_MSG_TESTIGO_CON_MOVIMIENTOS = (
    "No se puede eliminar: el testigo tiene movimientos registrados. "
    "Podés desactivarlo en su lugar."
)

# Tablas que referencian lims_testigos por FK -- si el testigo aparece en
# cualquiera de ellas, el DELETE físico rompe integridad referencial.
_TABLAS_CON_REFERENCIA_A_TESTIGO = [
    "lims_testigo_movimientos",
    "lims_remito_testigos_det",
    "lims_especificacion_testigos",
    "lims_envio_testigos",
    "lims_envios",
]


@router.delete("/testigos/{id_testigo}", status_code=204)
def eliminar_testigo(
    id_testigo: int,
    user: dict = Depends(require_rol("qa", "admin")),
    conn: pyodbc.Connection = Depends(limss_db),
):
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM lims_testigos WHERE id_testigo = ?", id_testigo)
    row = cursor.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Testigo no encontrado")

    for tabla in _TABLAS_CON_REFERENCIA_A_TESTIGO:
        cursor.execute(f"SELECT 1 FROM {tabla} WHERE id_testigo = ?", id_testigo)
        if cursor.fetchone():
            raise HTTPException(status_code=400, detail=_MSG_TESTIGO_CON_MOVIMIENTOS)

    try:
        cursor.execute("DELETE FROM lims_testigos WHERE id_testigo = ?", id_testigo)
    except pyodbc.IntegrityError:
        raise HTTPException(status_code=400, detail=_MSG_TESTIGO_CON_MOVIMIENTOS)

    audit.registrar(
        conn, entidad="testigo", accion="eliminar",
        id_usuario=user["id_usuario"], id_entidad=id_testigo,
        valor_anterior={"codigo": row.codigo, "nombre": row.nombre, "nro_lote": row.nro_lote},
    )


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
    estados: Optional[str] = Query(
        None,
        description=(
            "Lista separada por comas (vencido,por_vencer,normal,sin_vencimiento,stock_bajo), "
            "combinados con OR -- usado por el filtro de checkboxes de TestigosPage. "
            "Si se envía, reemplaza a 'estado' + 'stock_bajo' (que siguen andando solos para "
            "ReporteTestigosPage, sin tocar su comportamiento)."
        ),
    ),
    orden: Optional[str] = Query(None, pattern=r"^(vencimiento_asc|vencimiento_desc|nombre_asc|codigo_asc|stock_asc|ir_asc)$"),
    fecha_ref: Optional[date] = Query(None, description="Fecha de referencia para calcular vencido/por_vencer; por defecto, hoy"),
    dias_anticipacion: int = Query(30, ge=0, description="Días de anticipación para considerar 'por vencer'"),
    id_categoria: Optional[int] = Query(None, description="Filtrar por categoría de testigo"),
    id_laboratorio: Optional[int] = Query(
        None,
        description="Filtrar por laboratorio asignado -- un testigo puede tener varios "
                    "(lims_testigo_laboratorios), matchea si el laboratorio está entre los asignados",
    ),
    user: dict = Depends(get_current_user),
    conn: pyodbc.Connection = Depends(limss_db),
):
    cursor = conn.cursor()
    like = f"%{buscar}%"
    base_sql = _select_testigos_sql(cursor)
    if activo is None:
        cursor.execute(
            base_sql + "WHERE t.codigo LIKE ? OR t.nombre LIKE ? ORDER BY t.nombre",
            like, like,
        )
    else:
        cursor.execute(
            base_sql + "WHERE t.activo = ? AND (t.codigo LIKE ? OR t.nombre LIKE ?) ORDER BY t.nombre",
            1 if activo else 0, like, like,
        )
    testigos = [_fila_a_testigo(r, fecha_ref=fecha_ref, dias_anticipacion=dias_anticipacion, cursor=cursor) for r in cursor.fetchall()]

    if id_categoria is not None:
        testigos = [t for t in testigos if t.id_categoria == id_categoria]

    if id_laboratorio is not None:
        testigos = [t for t in testigos if any(l.id_laboratorio == id_laboratorio for l in t.laboratorios)]

    if solo_alertas:
        testigos = [t for t in testigos if t.vencido or t.por_vencer or t.stock_bajo]

    if estados:
        estados_pedidos = {e.strip() for e in estados.split(",") if e.strip()} & ESTADOS_TESTIGO_VALIDOS
        if not estados_pedidos:
            estados_pedidos = {"vencido", "por_vencer"}
        testigos = [t for t in testigos if _cumple_filtro_estado_testigo(t, estados_pedidos)]
    else:
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
    cursor.execute(_select_testigos_sql(cursor) + "WHERE t.id_testigo = ?", id_testigo)
    row = cursor.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Testigo no encontrado")
    return _fila_a_testigo(row, cursor=cursor)


_MSG_FALTA_MIGRACION_LAB_TESTIGO = (
    "Falta ejecutar la migración de laboratorios de testigo "
    "(migrations_testigo_laboratorios_m2m.sql)"
)


@router.get("/testigos/{id_testigo}/laboratorios", response_model=list[LaboratorioAsignado])
def listar_laboratorios_testigo(
    id_testigo: int,
    user: dict = Depends(get_current_user),
    conn: pyodbc.Connection = Depends(limss_db),
):
    cursor = conn.cursor()
    cursor.execute("SELECT 1 FROM lims_testigos WHERE id_testigo = ?", id_testigo)
    if not cursor.fetchone():
        raise HTTPException(status_code=404, detail="Testigo no encontrado")
    return _laboratorios_de_testigo(cursor, id_testigo)


@router.post("/testigos/{id_testigo}/laboratorios", response_model=list[LaboratorioAsignado], status_code=201)
def asignar_laboratorio_testigo(
    id_testigo: int,
    body: TestigoLaboratorioCreate,
    user: dict = Depends(require_rol("analista_qc", "admin", "qa")),
    conn: pyodbc.Connection = Depends(limss_db),
):
    cursor = conn.cursor()
    if not _tiene_tabla_testigo_laboratorios(cursor):
        raise HTTPException(status_code=503, detail=_MSG_FALTA_MIGRACION_LAB_TESTIGO)

    cursor.execute("SELECT 1 FROM lims_testigos WHERE id_testigo = ?", id_testigo)
    if not cursor.fetchone():
        raise HTTPException(status_code=404, detail="Testigo no encontrado")

    cursor.execute("SELECT 1 FROM lims_laboratorios WHERE id_laboratorio = ? AND activo = 1", body.id_laboratorio)
    if not cursor.fetchone():
        raise HTTPException(status_code=404, detail="El laboratorio indicado no existe o está inactivo")

    cursor.execute(
        "SELECT 1 FROM lims_testigo_laboratorios WHERE id_testigo = ? AND id_laboratorio = ?",
        id_testigo, body.id_laboratorio,
    )
    if cursor.fetchone():
        raise HTTPException(status_code=409, detail="El laboratorio ya está asignado a este testigo")

    unidad_consumo = body.unidad_consumo or ("mg" if body.consumo_estimado is not None else None)

    if _tiene_columna_fecha_envio_real(cursor):
        cursor.execute(
            "INSERT INTO lims_testigo_laboratorios (id_testigo, id_laboratorio, consumo_estimado, unidad_consumo, fecha_envio_real) VALUES (?, ?, ?, ?, ?)",
            id_testigo, body.id_laboratorio, body.consumo_estimado, unidad_consumo, body.fecha_envio_real,
        )
    else:
        cursor.execute(
            "INSERT INTO lims_testigo_laboratorios (id_testigo, id_laboratorio, consumo_estimado, unidad_consumo) VALUES (?, ?, ?, ?)",
            id_testigo, body.id_laboratorio, body.consumo_estimado, unidad_consumo,
        )

    audit.registrar(
        conn, entidad="testigo_laboratorio", accion="asignar",
        id_usuario=user["id_usuario"], id_entidad=id_testigo,
        valor_nuevo={
            "id_testigo": id_testigo, "id_laboratorio": body.id_laboratorio,
            "consumo_estimado": body.consumo_estimado, "unidad_consumo": unidad_consumo,
            "fecha_envio_real": str(body.fecha_envio_real) if body.fecha_envio_real else None,
        },
    )

    return _laboratorios_de_testigo(cursor, id_testigo)


@router.put("/testigos/{id_testigo}/laboratorios/{id_laboratorio}", response_model=list[LaboratorioAsignado])
def editar_consumo_laboratorio_testigo(
    id_testigo: int,
    id_laboratorio: int,
    body: TestigoLaboratorioConsumoUpdate,
    user: dict = Depends(require_rol("analista_qc", "admin", "qa")),
    conn: pyodbc.Connection = Depends(limss_db),
):
    """Actualiza el consumo estimado por análisis de un laboratorio ya
    asignado al testigo (usado por confirmar_envio para descontar stock
    automáticamente). No reasigna ni desvincula -- eso sigue siendo POST/DELETE."""
    cursor = conn.cursor()
    if not _tiene_tabla_testigo_laboratorios(cursor):
        raise HTTPException(status_code=503, detail=_MSG_FALTA_MIGRACION_LAB_TESTIGO)

    cursor.execute(
        "SELECT 1 FROM lims_testigo_laboratorios WHERE id_testigo = ? AND id_laboratorio = ?",
        id_testigo, id_laboratorio,
    )
    if not cursor.fetchone():
        raise HTTPException(status_code=404, detail="El laboratorio no está asignado a este testigo")

    unidad_consumo = body.unidad_consumo or ("mg" if body.consumo_estimado is not None else None)

    if _tiene_columna_fecha_envio_real(cursor):
        cursor.execute(
            "UPDATE lims_testigo_laboratorios SET consumo_estimado = ?, unidad_consumo = ?, fecha_envio_real = ? WHERE id_testigo = ? AND id_laboratorio = ?",
            body.consumo_estimado, unidad_consumo, body.fecha_envio_real, id_testigo, id_laboratorio,
        )
    else:
        cursor.execute(
            "UPDATE lims_testigo_laboratorios SET consumo_estimado = ?, unidad_consumo = ? WHERE id_testigo = ? AND id_laboratorio = ?",
            body.consumo_estimado, unidad_consumo, id_testigo, id_laboratorio,
        )

    audit.registrar(
        conn, entidad="testigo_laboratorio", accion="modificar_consumo",
        id_usuario=user["id_usuario"], id_entidad=id_testigo,
        valor_nuevo={
            "id_testigo": id_testigo, "id_laboratorio": id_laboratorio,
            "consumo_estimado": body.consumo_estimado, "unidad_consumo": unidad_consumo,
            "fecha_envio_real": str(body.fecha_envio_real) if body.fecha_envio_real else None,
        },
    )

    return _laboratorios_de_testigo(cursor, id_testigo)


@router.delete("/testigos/{id_testigo}/laboratorios/{id_laboratorio}", response_model=list[LaboratorioAsignado])
def desvincular_laboratorio_testigo(
    id_testigo: int,
    id_laboratorio: int,
    user: dict = Depends(require_rol("qa", "admin")),
    conn: pyodbc.Connection = Depends(limss_db),
):
    cursor = conn.cursor()
    if not _tiene_tabla_testigo_laboratorios(cursor):
        raise HTTPException(status_code=503, detail=_MSG_FALTA_MIGRACION_LAB_TESTIGO)

    cursor.execute(
        "DELETE FROM lims_testigo_laboratorios WHERE id_testigo = ? AND id_laboratorio = ?",
        id_testigo, id_laboratorio,
    )
    if cursor.rowcount == 0:
        raise HTTPException(status_code=404, detail="El laboratorio no está asignado a este testigo")

    audit.registrar(
        conn, entidad="testigo_laboratorio", accion="desvincular",
        id_usuario=user["id_usuario"], id_entidad=id_testigo,
        valor_anterior={"id_testigo": id_testigo, "id_laboratorio": id_laboratorio},
    )

    return _laboratorios_de_testigo(cursor, id_testigo)


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

    cursor.execute(_select_testigos_sql(cursor) + "WHERE t.id_testigo = ?", id_testigo)
    return _fila_a_testigo(cursor.fetchone(), cursor=cursor)


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

    cursor.execute(_select_testigos_sql(cursor) + "WHERE t.id_testigo = ?", id_testigo)
    return _fila_a_testigo(cursor.fetchone(), cursor=cursor)


# Reexport sin prefijo para reutilizar la misma clasificación/orden de
# testigos desde dashboard.py, sin duplicar esta lógica.
select_testigos_sql = _select_testigos_sql
fila_a_testigo = _fila_a_testigo
ordenar_por_fecha_vencimiento = _ordenar_por_fecha_vencimiento
cumple_filtro_estado_testigo = _cumple_filtro_estado_testigo
