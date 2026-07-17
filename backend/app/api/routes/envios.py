"""
Remito de envío en PDF (REQ-ENV-004).

Genera un documento PDF formal del remito, con numeración interna propia
(REM-YYYY-NNNN) -- distinta del número de remito/guía externo del
transportista, que ya se registra en lims_envios.nro_remito (REQ-ENV-005).
Append-only: cada "generar" crea un documento nuevo; nunca se sobrescribe uno
existente. GET siempre devuelve el más reciente.

El GET expone el número y la fecha de generación como headers custom
(X-Remito-Numero / X-Remito-Fecha) para que el frontend pueda mostrar "ya
existe un remito" sin necesitar un tercer endpoint solo de metadata --
son las únicas dos rutas pedidas para este módulo.
"""
import os
from datetime import date

import pyodbc
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse

from app.core.security import get_current_user, require_rol
from app.db.connections import limss_db
from app.schemas.envios import RemitoPdfResponse
from app.services import audit, storage
from app.services.pdf_remito import generar_pdf_remito

router = APIRouter(prefix="/api/envios", tags=["Envíos"])


_SELECT_DATOS_REMITO = """
    SELECT e.id_envio, e.fecha_despacho, e.temperatura_transporte, e.nro_remito,
           e.transportista, e.analisis_solicitados, e.protocolo_utilizar,
           e.cantidad_testigo,
           m.codigo_muestra, m.tipo_referencia, m.nro_referencia,
           m.erp_CODART, m.erp_DESART, m.fecha_muestreo,
           u.nombre + ' ' + u.apellido AS usuario_muestreo_nombre,
           lab.nombre AS laboratorio_nombre, lab.direccion AS laboratorio_direccion,
           lab.contacto AS laboratorio_contacto,
           t.codigo AS testigo_codigo, t.nombre AS testigo_nombre,
           t.nro_lote AS testigo_nro_lote, t.fecha_vencimiento AS testigo_fecha_vencimiento
    FROM lims_envios e
    INNER JOIN lims_muestras m ON m.id_muestra = e.id_muestra
    INNER JOIN lims_usuarios u ON u.id_usuario = m.id_usuario_muestreo
    INNER JOIN lims_laboratorios lab ON lab.id_laboratorio = e.id_laboratorio
    LEFT JOIN lims_testigos t ON t.id_testigo = e.id_testigo
"""


def _fila_a_remito_pdf(fila) -> RemitoPdfResponse:
    return RemitoPdfResponse(
        id_remito=fila.id_remito,
        id_envio=fila.id_envio,
        nro_remito_interno=fila.nro_remito_interno,
        url_descarga=f"/api/envios/{fila.id_envio}/remito",
        id_usuario_genera=fila.id_usuario_genera,
        fecha_generacion=fila.fecha_generacion,
    )


@router.post("/{id_envio}/remito", response_model=RemitoPdfResponse, status_code=201)
def generar_remito(
    id_envio: int,
    user: dict = Depends(require_rol("muestreador", "qa", "admin")),
    conn: pyodbc.Connection = Depends(limss_db),
):
    cursor = conn.cursor()
    cursor.execute(_SELECT_DATOS_REMITO + " WHERE e.id_envio = ?", id_envio)
    datos = cursor.fetchone()
    if not datos:
        raise HTTPException(status_code=404, detail="Envío no encontrado")

    anio = date.today().year
    cursor.execute(
        "SELECT MAX(nro_remito_interno) AS ultimo FROM lims_remitos WHERE nro_remito_interno LIKE ?",
        f"REM-{anio}-%",
    )
    ultimo = cursor.fetchone().ultimo
    correlativo = int(ultimo.split("-")[-1]) + 1 if ultimo else 1
    nro_remito_interno = f"REM-{anio}-{correlativo:04d}"

    pdf_bytes = generar_pdf_remito(datos, nro_remito_interno)
    ruta_pdf = storage.guardar_pdf_remito(pdf_bytes, nro_remito_interno)

    cursor.execute(
        """
        INSERT INTO lims_remitos (id_envio, nro_remito_interno, pdf_path, id_usuario_genera)
        VALUES (?, ?, ?, ?)
        """,
        id_envio, nro_remito_interno, ruta_pdf, user["id_usuario"],
    )
    cursor.execute("SELECT @@IDENTITY AS id")
    id_remito = int(cursor.fetchone().id)

    audit.registrar(
        conn, entidad="remito", accion="generar",
        id_usuario=user["id_usuario"], id_entidad=id_remito,
        valor_nuevo={"id_envio": id_envio, "nro_remito_interno": nro_remito_interno},
    )

    cursor.execute("SELECT * FROM lims_remitos WHERE id_remito = ?", id_remito)
    return _fila_a_remito_pdf(cursor.fetchone())


@router.get("/{id_envio}/remito")
def descargar_remito(
    id_envio: int,
    user: dict = Depends(get_current_user),
    conn: pyodbc.Connection = Depends(limss_db),
):
    cursor = conn.cursor()
    cursor.execute(
        "SELECT TOP 1 * FROM lims_remitos WHERE id_envio = ? ORDER BY id_remito DESC",
        id_envio,
    )
    fila = cursor.fetchone()
    if not fila:
        raise HTTPException(status_code=404, detail="Todavía no se generó un remito para este envío")

    ruta = storage.ruta_absoluta(fila.pdf_path)
    if not os.path.exists(ruta):
        raise HTTPException(status_code=404, detail="El archivo no se encuentra en el servidor")

    return FileResponse(
        ruta, media_type="application/pdf", filename=os.path.basename(ruta),
        headers={
            "X-Remito-Numero": fila.nro_remito_interno,
            "X-Remito-Fecha": fila.fecha_generacion.isoformat(),
        },
    )
