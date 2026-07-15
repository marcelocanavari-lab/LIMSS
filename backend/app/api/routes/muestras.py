"""
Módulo I: Muestras y Envíos (REQ-ENV-001 a 005).

Digitaliza el flujo desde la toma de muestra hasta el despacho a un laboratorio
externo. El orden de declaración de rutas importa: FastAPI/Starlette matchea la
primera ruta cuyo patrón calza sintácticamente, y "/{id_muestra}" (un solo
segmento, tipo genérico a nivel de ruteo) calzaría con "/laboratorios" si se
declarara antes -- por eso los literales van primero.
"""
from datetime import date
from typing import Optional

import pyodbc
from fastapi import APIRouter, Depends, HTTPException, Query

from app.core.security import get_current_user, require_rol
from app.db.connections import ebr_db, erp_db, limss_db
from app.schemas.muestras import (
    EnvioCreate,
    EnvioResponse,
    LaboratorioCreate,
    LaboratorioResponse,
    LaboratorioUpdate,
    LineaIR,
    MaterialEncontrado,
    MuestraCreate,
    MuestraResponse,
    RemitoResponse,
)
from app.services import audit
from app.services.ebr_lotes import buscar_lote
from app.services.erp_ir import buscar_lineas_ir

router = APIRouter(prefix="/api/muestras", tags=["Muestras y Envíos"])


# ── Helpers internos ─────────────────────────────────────────────

def _fila_a_laboratorio(row) -> LaboratorioResponse:
    return LaboratorioResponse(
        id_laboratorio=row.id_laboratorio,
        nombre=row.nombre,
        direccion=row.direccion,
        contacto=row.contacto,
        email=row.email,
        telefono=row.telefono,
        activo=bool(row.activo),
    )


def _fila_a_muestra(row) -> MuestraResponse:
    return MuestraResponse(
        id_muestra=row.id_muestra,
        codigo_muestra=row.codigo_muestra,
        tipo_referencia=row.tipo_referencia,
        nro_referencia=row.nro_referencia,
        erp_IdM21=row.erp_IdM21,
        erp_CODART=row.erp_CODART,
        erp_DESART=row.erp_DESART,
        erp_cantidad_lote=float(row.erp_cantidad_lote) if row.erp_cantidad_lote is not None else None,
        erp_proveedor=row.erp_proveedor,
        id_especificacion=row.id_especificacion,
        estado=row.estado,
        id_usuario_muestreo=row.id_usuario_muestreo,
        usuario_muestreo_nombre=row.usuario_muestreo_nombre,
        fecha_muestreo=row.fecha_muestreo,
        observaciones=row.observaciones,
    )


_SELECT_MUESTRA = """
    SELECT m.*, u.nombre + ' ' + u.apellido AS usuario_muestreo_nombre
    FROM lims_muestras m
    INNER JOIN lims_usuarios u ON u.id_usuario = m.id_usuario_muestreo
"""


# ── Laboratorios (prerrequisito técnico de los envíos) ────────────

@router.post("/laboratorios", response_model=LaboratorioResponse, status_code=201)
def crear_laboratorio(
    body: LaboratorioCreate,
    user: dict = Depends(require_rol("admin", "qa")),
    conn: pyodbc.Connection = Depends(limss_db),
):
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO lims_laboratorios (nombre, direccion, contacto, email, telefono)
        VALUES (?, ?, ?, ?, ?)
        """,
        body.nombre, body.direccion, body.contacto, body.email, body.telefono,
    )
    cursor.execute("SELECT @@IDENTITY AS id")
    id_laboratorio = int(cursor.fetchone().id)

    audit.registrar(
        conn, entidad="laboratorio", accion="crear",
        id_usuario=user["id_usuario"], id_entidad=id_laboratorio,
        valor_nuevo={"nombre": body.nombre},
    )

    cursor.execute("SELECT * FROM lims_laboratorios WHERE id_laboratorio = ?", id_laboratorio)
    return _fila_a_laboratorio(cursor.fetchone())


@router.get("/laboratorios", response_model=list[LaboratorioResponse])
def listar_laboratorios(
    activo: Optional[bool] = Query(None),
    user: dict = Depends(get_current_user),
    conn: pyodbc.Connection = Depends(limss_db),
):
    cursor = conn.cursor()
    if activo is None:
        cursor.execute("SELECT * FROM lims_laboratorios ORDER BY nombre")
    else:
        cursor.execute("SELECT * FROM lims_laboratorios WHERE activo = ? ORDER BY nombre", 1 if activo else 0)
    return [_fila_a_laboratorio(r) for r in cursor.fetchall()]


@router.put("/laboratorios/{id_laboratorio}", response_model=LaboratorioResponse)
def editar_laboratorio(
    id_laboratorio: int,
    body: LaboratorioUpdate,
    user: dict = Depends(require_rol("admin", "qa")),
    conn: pyodbc.Connection = Depends(limss_db),
):
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM lims_laboratorios WHERE id_laboratorio = ?", id_laboratorio)
    row = cursor.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Laboratorio no encontrado")

    campos_anteriores = {
        "nombre": row.nombre, "direccion": row.direccion, "contacto": row.contacto,
        "email": row.email, "telefono": row.telefono, "activo": bool(row.activo),
    }
    campos_nuevos = {
        "nombre": body.nombre, "direccion": body.direccion, "contacto": body.contacto,
        "email": body.email, "telefono": body.telefono, "activo": body.activo,
    }

    cursor.execute(
        """
        UPDATE lims_laboratorios
        SET nombre = ?, direccion = ?, contacto = ?, email = ?, telefono = ?, activo = ?
        WHERE id_laboratorio = ?
        """,
        body.nombre, body.direccion, body.contacto, body.email, body.telefono,
        1 if body.activo else 0, id_laboratorio,
    )

    valor_anterior = {k: v for k, v in campos_anteriores.items() if v != campos_nuevos[k]}
    valor_nuevo = {k: v for k, v in campos_nuevos.items() if v != campos_anteriores[k]}
    audit.registrar(
        conn, entidad="laboratorio", accion="modificar",
        id_usuario=user["id_usuario"], id_entidad=id_laboratorio,
        valor_anterior=valor_anterior or None, valor_nuevo=valor_nuevo or None,
    )

    cursor.execute("SELECT * FROM lims_laboratorios WHERE id_laboratorio = ?", id_laboratorio)
    return _fila_a_laboratorio(cursor.fetchone())


@router.put("/laboratorios/{id_laboratorio}/estado", response_model=LaboratorioResponse)
def cambiar_estado_laboratorio(
    id_laboratorio: int,
    activo: bool,
    user: dict = Depends(require_rol("admin", "qa")),
    conn: pyodbc.Connection = Depends(limss_db),
):
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM lims_laboratorios WHERE id_laboratorio = ?", id_laboratorio)
    row = cursor.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Laboratorio no encontrado")

    cursor.execute(
        "UPDATE lims_laboratorios SET activo = ? WHERE id_laboratorio = ?",
        1 if activo else 0, id_laboratorio,
    )

    audit.registrar(
        conn, entidad="laboratorio", accion="activar" if activo else "desactivar",
        id_usuario=user["id_usuario"], id_entidad=id_laboratorio,
        valor_anterior={"activo": bool(row.activo)}, valor_nuevo={"activo": activo},
    )

    cursor.execute("SELECT * FROM lims_laboratorios WHERE id_laboratorio = ?", id_laboratorio)
    return _fila_a_laboratorio(cursor.fetchone())


# ── Búsqueda de IR en el ERP (REQ-ENV-002) ────────────────────────

@router.get("/erp/ir/{nro_ir}", response_model=list[LineaIR])
def buscar_ir(
    nro_ir: str,
    user: dict = Depends(require_rol("muestreador", "qa", "admin")),
    erp: pyodbc.Connection = Depends(erp_db),
):
    rows = buscar_lineas_ir(erp, nro_ir)
    if not rows:
        raise HTTPException(status_code=404, detail=f"No se encontró el IR '{nro_ir}' en el ERP")
    return [
        LineaIR(
            N01Id=r.N01Id, NUMCOMO=r.NUMCOMO.strip(), IdM21=r.IdM21,
            CODART=r.CODART, DESART=r.DESART, CANTID=float(r.CANTID),
            unidad=r.unidad, proveedor=r.proveedor,
        )
        for r in rows
    ]


@router.get("/buscar-material", response_model=list[MaterialEncontrado])
def buscar_material(
    tipo: str = Query(..., pattern=r"^(materia_prima|granel|semi_elaborado|producto_terminado)$"),
    referencia: str = Query(..., min_length=1),
    user: dict = Depends(require_rol("muestreador", "qa", "admin")),
    erp: pyodbc.Connection = Depends(erp_db),
    ebr: pyodbc.Connection = Depends(ebr_db),
):
    """Búsqueda unificada por tipo: Materia Prima se busca por IR en el ERP
    (GIN01CPB); el resto (Granel/Semi-Elaborado/Producto Terminado) se busca
    por número de lote de producción interna en la base del eBR (ebr_lotes) --
    esos materiales no pasan por recepción de proveedor."""
    if tipo == "materia_prima":
        rows = buscar_lineas_ir(erp, referencia)
        if not rows:
            raise HTTPException(status_code=404, detail=f"No se encontró el IR '{referencia}' en el ERP")
        return [
            MaterialEncontrado(
                referencia=r.NUMCOMO.strip(), IdM21=r.IdM21, CODART=r.CODART, DESART=r.DESART,
                cantidad=float(r.CANTID), unidad=r.unidad, proveedor=r.proveedor,
            )
            for r in rows
        ]

    lote = buscar_lote(ebr, referencia)
    if not lote:
        raise HTTPException(status_code=404, detail=f"No se encontró el lote '{referencia}' en el eBR")
    return [
        MaterialEncontrado(
            referencia=lote.nro_lote.strip(), IdM21=lote.erp_IdM21, CODART=lote.erp_CODART,
            DESART=lote.erp_DESART, cantidad=float(lote.tamanio_lote) if lote.tamanio_lote is not None else None,
            unidad=lote.erp_unidad, proveedor=None,
        )
    ]


# ── Muestras (REQ-ENV-001) ────────────────────────────────────────

@router.post("/", response_model=MuestraResponse, status_code=201)
def crear_muestra(
    body: MuestraCreate,
    user: dict = Depends(require_rol("muestreador", "qa", "admin")),
    conn: pyodbc.Connection = Depends(limss_db),
):
    cursor = conn.cursor()

    anio = date.today().year
    cursor.execute(
        "SELECT MAX(codigo_muestra) AS ultimo FROM lims_muestras WHERE codigo_muestra LIKE ?",
        f"SAMP-{anio}-%",
    )
    ultimo = cursor.fetchone().ultimo
    correlativo = int(ultimo.split("-")[-1]) + 1 if ultimo else 1
    codigo_muestra = f"SAMP-{anio}-{correlativo:04d}"

    cursor.execute(
        "SELECT id_especificacion FROM lims_especificaciones WHERE erp_IdM21 = ? AND vigente = 1",
        body.erp_IdM21,
    )
    espec = cursor.fetchone()
    id_especificacion = espec.id_especificacion if espec else None

    cursor.execute(
        """
        INSERT INTO lims_muestras
            (codigo_muestra, tipo_referencia, nro_referencia, erp_IdM21, erp_CODART, erp_DESART,
             erp_cantidad_lote, erp_proveedor, id_especificacion, estado,
             id_usuario_muestreo, observaciones)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'pendiente_envio', ?, ?)
        """,
        codigo_muestra, body.tipo_referencia, body.nro_referencia, body.erp_IdM21, body.erp_CODART, body.erp_DESART,
        body.erp_cantidad_lote, body.erp_proveedor, id_especificacion,
        user["id_usuario"], body.observaciones,
    )
    cursor.execute("SELECT @@IDENTITY AS id")
    id_muestra = int(cursor.fetchone().id)

    audit.registrar(
        conn, entidad="muestra", accion="crear",
        id_usuario=user["id_usuario"], id_entidad=id_muestra,
        valor_nuevo={"codigo_muestra": codigo_muestra, "tipo_referencia": body.tipo_referencia, "nro_referencia": body.nro_referencia},
    )

    cursor.execute(_SELECT_MUESTRA + " WHERE m.id_muestra = ?", id_muestra)
    return _fila_a_muestra(cursor.fetchone())


@router.get("/", response_model=list[MuestraResponse])
def listar_muestras(
    estado: Optional[str] = Query(None),
    buscar: str = Query(""),
    user: dict = Depends(get_current_user),
    conn: pyodbc.Connection = Depends(limss_db),
):
    cursor = conn.cursor()
    like = f"%{buscar}%"
    if estado:
        cursor.execute(
            _SELECT_MUESTRA + """
            WHERE m.estado = ?
              AND (m.codigo_muestra LIKE ? OR m.nro_referencia LIKE ? OR m.erp_CODART LIKE ? OR m.erp_DESART LIKE ?)
            ORDER BY m.fecha_muestreo DESC
            """,
            estado, like, like, like, like,
        )
    else:
        cursor.execute(
            _SELECT_MUESTRA + """
            WHERE m.codigo_muestra LIKE ? OR m.nro_referencia LIKE ? OR m.erp_CODART LIKE ? OR m.erp_DESART LIKE ?
            ORDER BY m.fecha_muestreo DESC
            """,
            like, like, like, like,
        )
    return [_fila_a_muestra(r) for r in cursor.fetchall()]


@router.get("/{id_muestra}", response_model=MuestraResponse)
def detalle_muestra(
    id_muestra: int,
    user: dict = Depends(get_current_user),
    conn: pyodbc.Connection = Depends(limss_db),
):
    cursor = conn.cursor()
    cursor.execute(_SELECT_MUESTRA + " WHERE m.id_muestra = ?", id_muestra)
    row = cursor.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Muestra no encontrada")
    return _fila_a_muestra(row)


# ── Envío a laboratorio externo (REQ-ENV-004/005) ─────────────────

@router.post("/{id_muestra}/envio", response_model=EnvioResponse, status_code=201)
def confirmar_envio(
    id_muestra: int,
    body: EnvioCreate,
    user: dict = Depends(require_rol("muestreador", "qa", "admin")),
    conn: pyodbc.Connection = Depends(limss_db),
):
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM lims_muestras WHERE id_muestra = ?", id_muestra)
    muestra = cursor.fetchone()
    if not muestra:
        raise HTTPException(status_code=404, detail="Muestra no encontrada")
    if muestra.estado != "pendiente_envio":
        raise HTTPException(
            status_code=409,
            detail=f"La muestra está en estado '{muestra.estado}', no se puede confirmar el envío",
        )

    cursor.execute(
        "SELECT 1 FROM lims_laboratorios WHERE id_laboratorio = ? AND activo = 1",
        body.id_laboratorio,
    )
    if not cursor.fetchone():
        raise HTTPException(status_code=404, detail="Laboratorio no encontrado o inactivo")

    alerta_testigo_por_vencer = False
    alerta_reorden = False
    testigo = None

    if body.id_testigo:
        if not body.cantidad_testigo:
            raise HTTPException(status_code=400, detail="Indicá la cantidad de testigo a enviar")

        cursor.execute("SELECT * FROM lims_testigos WHERE id_testigo = ?", body.id_testigo)
        testigo = cursor.fetchone()
        if not testigo:
            raise HTTPException(status_code=404, detail="Testigo no encontrado")
        if not testigo.activo:
            raise HTTPException(status_code=400, detail="El testigo está inactivo")

        hoy = date.today()
        if testigo.fecha_vencimiento < hoy:
            # REQ-ENV-004-A: bloqueo absoluto, testigo vencido no puede enviarse.
            raise HTTPException(
                status_code=400,
                detail=f"El testigo '{testigo.codigo}' está VENCIDO ({testigo.fecha_vencimiento}). No se puede confirmar el envío.",
            )
        if (testigo.fecha_vencimiento - hoy).days < 30:
            alerta_testigo_por_vencer = True

        if body.cantidad_testigo > float(testigo.stock_actual):
            raise HTTPException(
                status_code=400,
                detail=f"Stock insuficiente de testigo (disponible: {testigo.stock_actual})",
            )

    cursor.execute(
        """
        INSERT INTO lims_envios
            (id_muestra, id_laboratorio, id_testigo, cantidad_testigo,
             temperatura_transporte, nro_remito, transportista,
             analisis_solicitados, protocolo_utilizar, id_usuario_envio)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        id_muestra, body.id_laboratorio, body.id_testigo, body.cantidad_testigo,
        body.temperatura_transporte, body.nro_remito, body.transportista,
        body.analisis_solicitados, body.protocolo_utilizar, user["id_usuario"],
    )
    cursor.execute("SELECT @@IDENTITY AS id")
    id_envio = int(cursor.fetchone().id)

    if body.id_testigo:
        # REQ-ENV-004-B: descuenta stock y avisa si queda por debajo del mínimo.
        stock_nuevo = float(testigo.stock_actual) - body.cantidad_testigo
        cursor.execute(
            "UPDATE lims_testigos SET stock_actual = ? WHERE id_testigo = ?",
            stock_nuevo, body.id_testigo,
        )
        cursor.execute(
            """
            INSERT INTO lims_testigo_movimientos
                (id_testigo, id_envio, tipo, cantidad, stock_resultante, id_usuario, observaciones)
            VALUES (?, ?, 'egreso', ?, ?, ?, ?)
            """,
            body.id_testigo, id_envio, -body.cantidad_testigo, stock_nuevo,
            user["id_usuario"], f"Envío #{id_envio}",
        )
        if stock_nuevo < float(testigo.stock_minimo):
            alerta_reorden = True

    cursor.execute("UPDATE lims_muestras SET estado = 'en_transito' WHERE id_muestra = ?", id_muestra)

    audit.registrar(
        conn, entidad="envio", accion="confirmar",
        id_usuario=user["id_usuario"], id_entidad=id_envio,
        valor_nuevo={"id_muestra": id_muestra, "id_laboratorio": body.id_laboratorio},
    )

    cursor.execute("SELECT * FROM lims_envios WHERE id_envio = ?", id_envio)
    row = cursor.fetchone()
    return EnvioResponse(
        id_envio=row.id_envio,
        id_muestra=row.id_muestra,
        id_laboratorio=row.id_laboratorio,
        id_testigo=row.id_testigo,
        cantidad_testigo=float(row.cantidad_testigo) if row.cantidad_testigo is not None else None,
        fecha_despacho=row.fecha_despacho,
        temperatura_transporte=row.temperatura_transporte,
        nro_remito=row.nro_remito,
        transportista=row.transportista,
        analisis_solicitados=row.analisis_solicitados,
        protocolo_utilizar=row.protocolo_utilizar,
        id_usuario_envio=row.id_usuario_envio,
        alerta_testigo_por_vencer=alerta_testigo_por_vencer,
        alerta_reorden=alerta_reorden,
    )


@router.get("/{id_muestra}/remito", response_model=RemitoResponse)
def obtener_remito(
    id_muestra: int,
    user: dict = Depends(get_current_user),
    conn: pyodbc.Connection = Depends(limss_db),
):
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT m.codigo_muestra, m.tipo_referencia, m.nro_referencia, m.erp_CODART, m.erp_DESART, m.fecha_muestreo,
               e.fecha_despacho, e.temperatura_transporte, e.nro_remito, e.transportista,
               e.analisis_solicitados, e.protocolo_utilizar, e.cantidad_testigo,
               lab.nombre AS laboratorio_nombre, lab.direccion AS laboratorio_direccion,
               t.codigo AS testigo_codigo, t.nombre AS testigo_nombre
        FROM lims_muestras m
        INNER JOIN lims_envios e ON e.id_muestra = m.id_muestra
        INNER JOIN lims_laboratorios lab ON lab.id_laboratorio = e.id_laboratorio
        LEFT JOIN lims_testigos t ON t.id_testigo = e.id_testigo
        WHERE m.id_muestra = ?
        """,
        id_muestra,
    )
    row = cursor.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="La muestra no tiene un envío confirmado todavía")

    return RemitoResponse(
        codigo_muestra=row.codigo_muestra,
        tipo_referencia=row.tipo_referencia,
        nro_referencia=row.nro_referencia,
        erp_CODART=row.erp_CODART,
        erp_DESART=row.erp_DESART,
        fecha_muestreo=row.fecha_muestreo,
        laboratorio_nombre=row.laboratorio_nombre,
        laboratorio_direccion=row.laboratorio_direccion,
        fecha_despacho=row.fecha_despacho,
        temperatura_transporte=row.temperatura_transporte,
        nro_remito=row.nro_remito,
        transportista=row.transportista,
        analisis_solicitados=row.analisis_solicitados,
        protocolo_utilizar=row.protocolo_utilizar,
        testigo_codigo=row.testigo_codigo,
        testigo_nombre=row.testigo_nombre,
        cantidad_testigo=float(row.cantidad_testigo) if row.cantidad_testigo is not None else None,
    )
