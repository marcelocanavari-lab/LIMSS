"""
Facturación de laboratorios externos: registro de facturas recibidas y su
vinculación con los envíos que cubren, para poder controlar qué envíos ya
fueron facturados y el estado de pago de cada factura.
"""
from datetime import date
from typing import Optional

import pyodbc
from fastapi import APIRouter, Depends, HTTPException, Query

from app.core.security import require_rol
from app.db.connections import limss_db
from app.schemas.facturas import (
    EnvioFacturaItem,
    FacturaAnularUpdate,
    FacturaCreate,
    FacturaDetalleResponse,
    FacturaPagoUpdate,
    FacturaResponse,
    FacturaUpdate,
)
from app.services import audit

router = APIRouter(prefix="/api/facturas", tags=["Facturación"])

_ROLES_GESTION = ("analista_qc", "qa", "admin")
_ROLES_PAGO = ("qa", "admin")


def _obtener_envios_de_factura(cursor, id_factura: int) -> list[EnvioFacturaItem]:
    """Envíos vinculados a la factura, con los datos del material/muestra que
    permiten identificar el análisis (código/nombre de material, N° de IR,
    cantidad de ensayos solicitados)."""
    cursor.execute(
        """
        SELECT e.id_envio, e.nro_remito, e.fecha_despacho,
               m.codigo_muestra, m.erp_CODART, m.erp_DESART, m.erp_nro_ir,
               (SELECT COUNT(*) FROM lims_envio_ensayos ee WHERE ee.id_envio = e.id_envio) AS cant_ensayos
        FROM lims_factura_envios fe
        INNER JOIN lims_envios e ON e.id_envio = fe.id_envio
        LEFT JOIN lims_muestras m ON m.id_muestra = e.id_muestra
        WHERE fe.id_factura = ?
        ORDER BY e.fecha_despacho
        """,
        id_factura,
    )
    return [
        EnvioFacturaItem(
            id_envio=r.id_envio, nro_remito=r.nro_remito, codigo_muestra=r.codigo_muestra,
            fecha_despacho=r.fecha_despacho, erp_CODART=r.erp_CODART, erp_DESART=r.erp_DESART,
            erp_nro_ir=r.erp_nro_ir, cantidad_ensayos=r.cant_ensayos,
        )
        for r in cursor.fetchall()
    ]


def _fila_a_factura(row, envios: list[EnvioFacturaItem]) -> FacturaResponse:
    return FacturaResponse(
        id_factura=row.id_factura,
        id_laboratorio=row.id_laboratorio,
        laboratorio_nombre=getattr(row, "laboratorio_nombre", None),
        nro_factura=row.nro_factura,
        fecha_factura=row.fecha_factura,
        fecha_recepcion=row.fecha_recepcion,
        monto=float(row.monto),
        moneda=row.moneda,
        descripcion=row.descripcion,
        estado_pago=row.estado_pago,
        fecha_pago=row.fecha_pago,
        nro_comprobante_pago=row.nro_comprobante_pago,
        observaciones=row.observaciones,
        id_usuario=row.id_usuario,
        fecha_carga=row.fecha_carga,
        cantidad_envios=len(envios),
        envios=envios,
    )


def _obtener_factura_detalle(cursor, id_factura: int) -> FacturaDetalleResponse:
    cursor.execute(
        """
        SELECT f.*, lab.nombre AS laboratorio_nombre
        FROM lims_facturas f
        JOIN lims_laboratorios lab ON lab.id_laboratorio = f.id_laboratorio
        WHERE f.id_factura = ?
        """,
        id_factura,
    )
    row = cursor.fetchone()
    envios = _obtener_envios_de_factura(cursor, id_factura)
    factura = _fila_a_factura(row, envios)
    return FacturaDetalleResponse(**factura.model_dump())


def _validar_envios_para_factura(
    cursor, id_laboratorio: int, id_envios: list[int], id_factura_actual: Optional[int] = None
) -> list[int]:
    """Cada envío debe existir, pertenecer al mismo laboratorio de la factura,
    y no estar ya vinculado a OTRA factura (uq_factura_envio en BD solo evita
    duplicar el mismo par factura/envío, no que un envío esté en dos facturas
    distintas -- esa regla de negocio se aplica acá)."""
    for id_envio in id_envios:
        cursor.execute("SELECT id_laboratorio FROM lims_envios WHERE id_envio = ?", id_envio)
        row = cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail=f"El envío {id_envio} no existe")
        if row.id_laboratorio != id_laboratorio:
            raise HTTPException(status_code=400, detail=f"El envío {id_envio} no pertenece al laboratorio de la factura")

        cursor.execute("SELECT id_factura FROM lims_factura_envios WHERE id_envio = ?", id_envio)
        existente = cursor.fetchone()
        if existente and existente.id_factura != id_factura_actual:
            raise HTTPException(
                status_code=409,
                detail=f"El envío {id_envio} ya está facturado (factura {existente.id_factura})",
            )
    return id_envios


@router.get("", response_model=list[FacturaResponse])
def listar_facturas(
    id_laboratorio: Optional[int] = Query(None),
    estado_pago: Optional[str] = Query(None, pattern=r"^(pendiente|pagado|anulado)$"),
    fecha_desde: Optional[date] = Query(None),
    fecha_hasta: Optional[date] = Query(None),
    user: dict = Depends(require_rol(*_ROLES_GESTION)),
    conn: pyodbc.Connection = Depends(limss_db),
):
    cursor = conn.cursor()
    condiciones = []
    params: list = []
    if id_laboratorio is not None:
        condiciones.append("f.id_laboratorio = ?")
        params.append(id_laboratorio)
    if estado_pago:
        condiciones.append("f.estado_pago = ?")
        params.append(estado_pago)
    if fecha_desde:
        condiciones.append("f.fecha_factura >= ?")
        params.append(str(fecha_desde))
    if fecha_hasta:
        condiciones.append("f.fecha_factura <= ?")
        params.append(str(fecha_hasta))
    where = f"WHERE {' AND '.join(condiciones)}" if condiciones else ""

    cursor.execute(
        f"""
        SELECT f.*, lab.nombre AS laboratorio_nombre
        FROM lims_facturas f
        JOIN lims_laboratorios lab ON lab.id_laboratorio = f.id_laboratorio
        {where}
        ORDER BY f.fecha_factura DESC
        """,
        *params,
    )
    filas = cursor.fetchall()
    return [_fila_a_factura(r, _obtener_envios_de_factura(cursor, r.id_factura)) for r in filas]


@router.post("", response_model=FacturaDetalleResponse, status_code=201)
def crear_factura(
    body: FacturaCreate,
    user: dict = Depends(require_rol(*_ROLES_GESTION)),
    conn: pyodbc.Connection = Depends(limss_db),
):
    cursor = conn.cursor()
    cursor.execute("SELECT 1 FROM lims_laboratorios WHERE id_laboratorio = ? AND activo = 1", body.id_laboratorio)
    if not cursor.fetchone():
        raise HTTPException(status_code=404, detail="El laboratorio indicado no existe o está inactivo")

    cursor.execute(
        "SELECT 1 FROM lims_facturas WHERE id_laboratorio = ? AND nro_factura = ?",
        body.id_laboratorio, body.nro_factura,
    )
    if cursor.fetchone():
        raise HTTPException(status_code=409, detail=f"Ya existe una factura '{body.nro_factura}' para este laboratorio")

    envios_validos = _validar_envios_para_factura(cursor, body.id_laboratorio, body.id_envios)

    cursor.execute(
        """
        INSERT INTO lims_facturas
            (id_laboratorio, nro_factura, fecha_factura, fecha_recepcion, monto, moneda, descripcion,
             estado_pago, id_usuario, fecha_carga)
        VALUES (?, ?, ?, ?, ?, ?, ?, 'pendiente', ?, GETDATE())
        """,
        body.id_laboratorio, body.nro_factura, str(body.fecha_factura),
        str(body.fecha_recepcion) if body.fecha_recepcion else None,
        body.monto, body.moneda, body.descripcion, user["id_usuario"],
    )
    cursor.execute("SELECT @@IDENTITY AS id")
    id_factura = int(cursor.fetchone().id)

    for id_envio in envios_validos:
        cursor.execute("INSERT INTO lims_factura_envios (id_factura, id_envio) VALUES (?, ?)", id_factura, id_envio)

    audit.registrar(
        conn, entidad="factura", accion="crear",
        id_usuario=user["id_usuario"], id_entidad=id_factura,
        valor_nuevo={
            "id_laboratorio": body.id_laboratorio, "nro_factura": body.nro_factura,
            "monto": body.monto, "moneda": body.moneda, "id_envios": envios_validos,
        },
    )

    return _obtener_factura_detalle(cursor, id_factura)


@router.get("/{id_factura}", response_model=FacturaDetalleResponse)
def detalle_factura(
    id_factura: int,
    user: dict = Depends(require_rol(*_ROLES_GESTION)),
    conn: pyodbc.Connection = Depends(limss_db),
):
    cursor = conn.cursor()
    cursor.execute("SELECT 1 FROM lims_facturas WHERE id_factura = ?", id_factura)
    if not cursor.fetchone():
        raise HTTPException(status_code=404, detail="Factura no encontrada")
    return _obtener_factura_detalle(cursor, id_factura)


@router.put("/{id_factura}", response_model=FacturaDetalleResponse)
def editar_factura(
    id_factura: int,
    body: FacturaUpdate,
    user: dict = Depends(require_rol(*_ROLES_GESTION)),
    conn: pyodbc.Connection = Depends(limss_db),
):
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM lims_facturas WHERE id_factura = ?", id_factura)
    row = cursor.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Factura no encontrada")
    if row.estado_pago == "anulado":
        raise HTTPException(status_code=400, detail="No se puede editar una factura anulada")

    cursor.execute(
        "SELECT 1 FROM lims_facturas WHERE id_laboratorio = ? AND nro_factura = ? AND id_factura != ?",
        row.id_laboratorio, body.nro_factura, id_factura,
    )
    if cursor.fetchone():
        raise HTTPException(status_code=409, detail=f"Ya existe otra factura '{body.nro_factura}' para este laboratorio")

    envios_validos = _validar_envios_para_factura(cursor, row.id_laboratorio, body.id_envios, id_factura_actual=id_factura)

    campos_anteriores = {
        "nro_factura": row.nro_factura, "fecha_factura": str(row.fecha_factura),
        "fecha_recepcion": str(row.fecha_recepcion) if row.fecha_recepcion else None,
        "monto": float(row.monto), "moneda": row.moneda, "descripcion": row.descripcion,
    }
    campos_nuevos = {
        "nro_factura": body.nro_factura, "fecha_factura": str(body.fecha_factura),
        "fecha_recepcion": str(body.fecha_recepcion) if body.fecha_recepcion else None,
        "monto": body.monto, "moneda": body.moneda, "descripcion": body.descripcion,
    }

    cursor.execute(
        """
        UPDATE lims_facturas
        SET nro_factura = ?, fecha_factura = ?, fecha_recepcion = ?, monto = ?, moneda = ?, descripcion = ?
        WHERE id_factura = ?
        """,
        body.nro_factura, str(body.fecha_factura),
        str(body.fecha_recepcion) if body.fecha_recepcion else None,
        body.monto, body.moneda, body.descripcion, id_factura,
    )

    cursor.execute("DELETE FROM lims_factura_envios WHERE id_factura = ?", id_factura)
    for id_envio in envios_validos:
        cursor.execute("INSERT INTO lims_factura_envios (id_factura, id_envio) VALUES (?, ?)", id_factura, id_envio)

    valor_anterior = {k: v for k, v in campos_anteriores.items() if v != campos_nuevos[k]}
    valor_nuevo = {k: v for k, v in campos_nuevos.items() if v != campos_anteriores[k]}
    audit.registrar(
        conn, entidad="factura", accion="modificar",
        id_usuario=user["id_usuario"], id_entidad=id_factura,
        valor_anterior=valor_anterior or None, valor_nuevo=valor_nuevo or None,
    )

    return _obtener_factura_detalle(cursor, id_factura)


@router.put("/{id_factura}/pago", response_model=FacturaDetalleResponse)
def registrar_pago_factura(
    id_factura: int,
    body: FacturaPagoUpdate,
    user: dict = Depends(require_rol(*_ROLES_PAGO)),
    conn: pyodbc.Connection = Depends(limss_db),
):
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM lims_facturas WHERE id_factura = ?", id_factura)
    row = cursor.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Factura no encontrada")
    if row.estado_pago != "pendiente":
        raise HTTPException(
            status_code=400,
            detail=f"La factura está en estado '{row.estado_pago}', no se puede registrar el pago",
        )

    cursor.execute(
        """
        UPDATE lims_facturas
        SET estado_pago = 'pagado', fecha_pago = ?, nro_comprobante_pago = ?, observaciones = ?
        WHERE id_factura = ?
        """,
        str(body.fecha_pago), body.nro_comprobante_pago, body.observaciones, id_factura,
    )

    audit.registrar(
        conn, entidad="factura", accion="registrar_pago",
        id_usuario=user["id_usuario"], id_entidad=id_factura,
        valor_anterior={"estado_pago": "pendiente"},
        valor_nuevo={
            "estado_pago": "pagado", "fecha_pago": str(body.fecha_pago),
            "nro_comprobante_pago": body.nro_comprobante_pago,
        },
    )

    return _obtener_factura_detalle(cursor, id_factura)


@router.put("/{id_factura}/anular", response_model=FacturaDetalleResponse)
def anular_factura(
    id_factura: int,
    body: FacturaAnularUpdate,
    user: dict = Depends(require_rol(*_ROLES_PAGO)),
    conn: pyodbc.Connection = Depends(limss_db),
):
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM lims_facturas WHERE id_factura = ?", id_factura)
    row = cursor.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Factura no encontrada")
    if row.estado_pago != "pendiente":
        raise HTTPException(status_code=400, detail="Solo se puede anular una factura pendiente")

    cursor.execute(
        "UPDATE lims_facturas SET estado_pago = 'anulado', observaciones = ? WHERE id_factura = ?",
        body.observaciones, id_factura,
    )

    audit.registrar(
        conn, entidad="factura", accion="anular",
        id_usuario=user["id_usuario"], id_entidad=id_factura,
        valor_anterior={"estado_pago": "pendiente"},
        valor_nuevo={"estado_pago": "anulado", "observaciones": body.observaciones},
    )

    return _obtener_factura_detalle(cursor, id_factura)
