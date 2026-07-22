"""
Remitos de envío de testigos/estándares a laboratorio externo para
recertificación. Un remito agrupa uno o más testigos enviados juntos al
mismo laboratorio en la misma fecha -- distinto del remito de muestra a
laboratorio (ver envios.py/pdf_remito.py), que es un documento aparte con
su propia numeración.

A diferencia de lims_remitos (remito de muestra, append-only con una fila
por cada "generar"), acá el PDF se genera una sola vez al crear el remito y
la ruta queda en lims_remito_testigos_cab.pdf_path directamente: no hay
concepto de "reimprimir con una versión nueva" para este documento.
"""
import os
from datetime import date

import pyodbc
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse

from app.core.security import get_current_user, require_rol
from app.db.connections import limss_db
from app.schemas.testigos_remitos import (
    HistorialEnvioTestigo,
    RemitoTestigoCreate,
    RemitoTestigoDetalle,
    RemitoTestigoResponse,
    TestigoEnRemito,
)
from app.services import audit, storage
from app.services.pdf_remito_testigo import generar_pdf_remito_testigo

router = APIRouter(prefix="/api/testigos", tags=["Remitos de Testigos"])


def _a_fecha(valor):
    """El driver ODBC no devuelve un tipo consistente para columnas DATE en
    este entorno (a veces date/datetime, a veces str); se normaliza siempre
    a date antes de operar."""
    if valor is None:
        return None
    if isinstance(valor, date):
        return valor
    if hasattr(valor, "date"):
        return valor.date()
    return date.fromisoformat(str(valor))


def _generar_nro_remito(cursor) -> str:
    anio = date.today().year
    cursor.execute(
        "SELECT MAX(nro_remito) AS ultimo FROM lims_remito_testigos_cab WHERE nro_remito LIKE ?",
        f"REM-TEST-{anio}-%",
    )
    ultimo = cursor.fetchone().ultimo
    correlativo = int(ultimo.split("-")[-1]) + 1 if ultimo else 1
    return f"REM-TEST-{anio}-{correlativo:03d}"


def _fila_a_remito_response(cursor, id_remito: int) -> RemitoTestigoResponse:
    cursor.execute(
        """
        SELECT c.*, lab.nombre AS laboratorio_nombre,
               (SELECT COUNT(*) FROM lims_remito_testigos_det d WHERE d.id_remito = c.id_remito) AS cantidad_testigos
        FROM lims_remito_testigos_cab c
        INNER JOIN lims_laboratorios lab ON lab.id_laboratorio = c.id_laboratorio
        WHERE c.id_remito = ?
        """,
        id_remito,
    )
    row = cursor.fetchone()
    return RemitoTestigoResponse(
        id_remito=row.id_remito,
        nro_remito=row.nro_remito,
        id_laboratorio=row.id_laboratorio,
        laboratorio_nombre=row.laboratorio_nombre,
        fecha_envio=_a_fecha(row.fecha_envio),
        observaciones=row.observaciones,
        cantidad_testigos=row.cantidad_testigos,
        id_usuario=row.id_usuario,
        fecha_creacion=row.fecha_creacion,
        tiene_copia_firmada=bool(row.pdf_copia_firmada),
        fecha_recepcion=_a_fecha(row.fecha_recepcion),
        recibido_por=row.recibido_por,
    )


def _obtener_remito_detalle(cursor, id_remito: int) -> RemitoTestigoDetalle:
    cursor.execute(
        """
        SELECT c.*, lab.nombre AS laboratorio_nombre, lab.direccion AS laboratorio_direccion,
               lab.contacto AS laboratorio_contacto,
               u.nombre + ' ' + u.apellido AS usuario_nombre
        FROM lims_remito_testigos_cab c
        INNER JOIN lims_laboratorios lab ON lab.id_laboratorio = c.id_laboratorio
        INNER JOIN lims_usuarios u ON u.id_usuario = c.id_usuario
        WHERE c.id_remito = ?
        """,
        id_remito,
    )
    row = cursor.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Remito no encontrado")

    cursor.execute(
        """
        SELECT t.id_testigo, t.codigo, t.nombre, t.nro_lote, t.nro_ir, t.fecha_vencimiento,
               d.cantidad_enviada, d.unidad
        FROM lims_remito_testigos_det d
        INNER JOIN lims_testigos t ON t.id_testigo = d.id_testigo
        WHERE d.id_remito = ?
        ORDER BY t.codigo
        """,
        id_remito,
    )
    testigos = [
        TestigoEnRemito(
            id_testigo=t.id_testigo, codigo=t.codigo, nombre=t.nombre, nro_lote=t.nro_lote,
            nro_ir=t.nro_ir, fecha_vencimiento=_a_fecha(t.fecha_vencimiento),
            cantidad_enviada=float(t.cantidad_enviada), unidad=t.unidad,
        )
        for t in cursor.fetchall()
    ]

    return RemitoTestigoDetalle(
        id_remito=row.id_remito, nro_remito=row.nro_remito, id_laboratorio=row.id_laboratorio,
        laboratorio_nombre=row.laboratorio_nombre, laboratorio_direccion=row.laboratorio_direccion,
        laboratorio_contacto=row.laboratorio_contacto, fecha_envio=_a_fecha(row.fecha_envio),
        observaciones=row.observaciones, id_usuario=row.id_usuario, usuario_nombre=row.usuario_nombre,
        fecha_creacion=row.fecha_creacion,
        tiene_copia_firmada=bool(row.pdf_copia_firmada),
        fecha_recepcion=_a_fecha(row.fecha_recepcion),
        recibido_por=row.recibido_por,
        testigos=testigos,
    )


@router.post("/remitos", response_model=RemitoTestigoResponse, status_code=201)
def crear_remito_testigos(
    body: RemitoTestigoCreate,
    user: dict = Depends(require_rol("analista_qc", "qa", "admin")),
    conn: pyodbc.Connection = Depends(limss_db),
):
    cursor = conn.cursor()

    cursor.execute(
        "SELECT * FROM lims_laboratorios WHERE id_laboratorio = ? AND activo = 1",
        body.id_laboratorio,
    )
    laboratorio = cursor.fetchone()
    if not laboratorio:
        raise HTTPException(status_code=404, detail="Laboratorio no encontrado o inactivo")

    ids_pedidos = [item.id_testigo for item in body.testigos]
    if len(set(ids_pedidos)) != len(ids_pedidos):
        raise HTTPException(status_code=400, detail="No se puede repetir el mismo testigo en un remito")

    testigos_detalle = []
    for item in body.testigos:
        cursor.execute("SELECT * FROM lims_testigos WHERE id_testigo = ?", item.id_testigo)
        testigo = cursor.fetchone()
        if not testigo:
            raise HTTPException(status_code=404, detail=f"Testigo {item.id_testigo} no encontrado")
        if not testigo.activo:
            raise HTTPException(status_code=400, detail=f"El testigo '{testigo.codigo}' está inactivo")
        if item.cantidad_enviada > float(testigo.stock_actual):
            raise HTTPException(
                status_code=400,
                detail=f"Stock insuficiente del testigo '{testigo.codigo}' (disponible: {testigo.stock_actual})",
            )
        testigos_detalle.append((item, testigo))

    nro_remito = _generar_nro_remito(cursor)

    pdf_bytes = generar_pdf_remito_testigo(laboratorio, body, nro_remito, testigos_detalle)
    ruta_pdf = storage.guardar_pdf_remito_testigo(pdf_bytes, nro_remito)

    cursor.execute(
        """
        INSERT INTO lims_remito_testigos_cab
            (nro_remito, id_laboratorio, fecha_envio, observaciones, pdf_path, id_usuario, fecha_creacion)
        VALUES (?, ?, ?, ?, ?, ?, GETDATE())
        """,
        nro_remito, body.id_laboratorio, str(body.fecha_envio), body.observaciones, ruta_pdf, user["id_usuario"],
    )
    cursor.execute("SELECT @@IDENTITY AS id")
    id_remito = int(cursor.fetchone().id)

    for item, testigo in testigos_detalle:
        cursor.execute(
            """
            INSERT INTO lims_remito_testigos_det (id_remito, id_testigo, cantidad_enviada, unidad)
            VALUES (?, ?, ?, ?)
            """,
            id_remito, item.id_testigo, item.cantidad_enviada, item.unidad,
        )

        stock_nuevo = float(testigo.stock_actual) - item.cantidad_enviada
        cursor.execute(
            "UPDATE lims_testigos SET stock_actual = ? WHERE id_testigo = ?",
            stock_nuevo, item.id_testigo,
        )
        cursor.execute(
            """
            INSERT INTO lims_testigo_movimientos
                (id_testigo, tipo, cantidad, stock_resultante, id_usuario, observaciones)
            VALUES (?, 'egreso', ?, ?, ?, ?)
            """,
            item.id_testigo, -item.cantidad_enviada, stock_nuevo, user["id_usuario"], f"Remito {nro_remito}",
        )

    audit.registrar(
        conn, entidad="remito_testigos", accion="crear",
        id_usuario=user["id_usuario"], id_entidad=id_remito,
        valor_nuevo={
            "nro_remito": nro_remito, "id_laboratorio": body.id_laboratorio,
            "cantidad_testigos": len(body.testigos),
        },
    )

    return _fila_a_remito_response(cursor, id_remito)


@router.get("/remitos", response_model=list[RemitoTestigoResponse])
def listar_remitos_testigos(
    user: dict = Depends(require_rol("analista_qc", "qa", "admin")),
    conn: pyodbc.Connection = Depends(limss_db),
):
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT c.*, lab.nombre AS laboratorio_nombre,
               (SELECT COUNT(*) FROM lims_remito_testigos_det d WHERE d.id_remito = c.id_remito) AS cantidad_testigos
        FROM lims_remito_testigos_cab c
        INNER JOIN lims_laboratorios lab ON lab.id_laboratorio = c.id_laboratorio
        ORDER BY c.fecha_creacion DESC
        """
    )
    return [
        RemitoTestigoResponse(
            id_remito=r.id_remito, nro_remito=r.nro_remito, id_laboratorio=r.id_laboratorio,
            laboratorio_nombre=r.laboratorio_nombre, fecha_envio=_a_fecha(r.fecha_envio),
            observaciones=r.observaciones, cantidad_testigos=r.cantidad_testigos,
            id_usuario=r.id_usuario, fecha_creacion=r.fecha_creacion,
            tiene_copia_firmada=bool(r.pdf_copia_firmada),
            fecha_recepcion=_a_fecha(r.fecha_recepcion), recibido_por=r.recibido_por,
        )
        for r in cursor.fetchall()
    ]


@router.get("/remitos/{id_remito}", response_model=RemitoTestigoDetalle)
def detalle_remito_testigos(
    id_remito: int,
    user: dict = Depends(require_rol("analista_qc", "qa", "admin")),
    conn: pyodbc.Connection = Depends(limss_db),
):
    return _obtener_remito_detalle(conn.cursor(), id_remito)


@router.get("/remitos/{id_remito}/pdf")
def descargar_pdf_remito_testigos(
    id_remito: int,
    user: dict = Depends(require_rol("analista_qc", "qa", "admin")),
    conn: pyodbc.Connection = Depends(limss_db),
):
    cursor = conn.cursor()
    cursor.execute("SELECT nro_remito, pdf_path FROM lims_remito_testigos_cab WHERE id_remito = ?", id_remito)
    row = cursor.fetchone()
    if not row or not row.pdf_path:
        raise HTTPException(status_code=404, detail="Remito no encontrado o sin PDF generado")

    ruta = storage.ruta_absoluta(row.pdf_path)
    if not os.path.exists(ruta):
        raise HTTPException(status_code=404, detail="El archivo no se encuentra en el servidor")

    return FileResponse(
        ruta, media_type="application/pdf",
        filename=f"LIMSS_{row.nro_remito}.pdf",
    )


@router.post("/remitos/{id_remito}/copia-firmada", response_model=RemitoTestigoDetalle)
def adjuntar_copia_firmada(
    id_remito: int,
    fecha_recepcion: date = Form(...),
    recibido_por: str = Form(..., min_length=1, max_length=100),
    pdf_copia_firmada: UploadFile = File(...),
    user: dict = Depends(require_rol("analista_qc", "qa", "admin")),
    conn: pyodbc.Connection = Depends(limss_db),
):
    """Copia del remito firmada por el laboratorio como constancia de
    recepción. Se puede llamar de nuevo sobre el mismo remito para
    reemplazar la copia ya adjunta (sube un archivo nuevo, pisa los datos)."""
    cursor = conn.cursor()
    cursor.execute("SELECT nro_remito, pdf_copia_firmada FROM lims_remito_testigos_cab WHERE id_remito = ?", id_remito)
    row = cursor.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Remito no encontrado")

    tenia_copia = bool(row.pdf_copia_firmada)
    ruta_pdf = storage.guardar_pdf_copia_firmada(pdf_copia_firmada, row.nro_remito)

    cursor.execute(
        """
        UPDATE lims_remito_testigos_cab
        SET pdf_copia_firmada = ?, fecha_recepcion = ?, recibido_por = ?
        WHERE id_remito = ?
        """,
        ruta_pdf, str(fecha_recepcion), recibido_por, id_remito,
    )

    audit.registrar(
        conn, entidad="remito_testigos", accion="reemplazar_copia_firmada" if tenia_copia else "adjuntar_copia_firmada",
        id_usuario=user["id_usuario"], id_entidad=id_remito,
        valor_nuevo={"fecha_recepcion": str(fecha_recepcion), "recibido_por": recibido_por},
    )

    return _obtener_remito_detalle(cursor, id_remito)


@router.get("/remitos/{id_remito}/copia-firmada")
def descargar_copia_firmada(
    id_remito: int,
    user: dict = Depends(require_rol("analista_qc", "qa", "admin")),
    conn: pyodbc.Connection = Depends(limss_db),
):
    cursor = conn.cursor()
    cursor.execute("SELECT nro_remito, pdf_copia_firmada FROM lims_remito_testigos_cab WHERE id_remito = ?", id_remito)
    row = cursor.fetchone()
    if not row or not row.pdf_copia_firmada:
        raise HTTPException(status_code=404, detail="Este remito no tiene copia firmada adjunta")

    ruta = storage.ruta_absoluta(row.pdf_copia_firmada)
    if not os.path.exists(ruta):
        raise HTTPException(status_code=404, detail="El archivo no se encuentra en el servidor")

    return FileResponse(
        ruta, media_type="application/pdf",
        filename=f"LIMSS_{row.nro_remito}_FIRMADO.pdf",
    )


@router.get("/{id_testigo}/historial-envios", response_model=list[HistorialEnvioTestigo])
def historial_envios_testigo(
    id_testigo: int,
    user: dict = Depends(get_current_user),
    conn: pyodbc.Connection = Depends(limss_db),
):
    cursor = conn.cursor()
    cursor.execute("SELECT 1 FROM lims_testigos WHERE id_testigo = ?", id_testigo)
    if not cursor.fetchone():
        raise HTTPException(status_code=404, detail="Testigo no encontrado")

    cursor.execute(
        """
        SELECT c.id_remito, c.nro_remito, c.fecha_envio, lab.nombre AS laboratorio_nombre,
               d.cantidad_enviada, d.unidad
        FROM lims_remito_testigos_det d
        INNER JOIN lims_remito_testigos_cab c ON c.id_remito = d.id_remito
        INNER JOIN lims_laboratorios lab ON lab.id_laboratorio = c.id_laboratorio
        WHERE d.id_testigo = ?
        ORDER BY c.fecha_envio DESC
        """,
        id_testigo,
    )
    return [
        HistorialEnvioTestigo(
            id_remito=r.id_remito, nro_remito=r.nro_remito, fecha_envio=_a_fecha(r.fecha_envio),
            laboratorio_nombre=r.laboratorio_nombre, cantidad_enviada=float(r.cantidad_enviada), unidad=r.unidad,
        )
        for r in cursor.fetchall()
    ]
