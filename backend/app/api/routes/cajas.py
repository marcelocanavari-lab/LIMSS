"""
Archivo de Contramuestras -- cajas físicas donde se archivan las
contramuestras retenidas de cada muestreo, para saber en todo momento
dónde está guardada la contramuestra de un material dado.

lims_caja_muestras nunca hace DELETE al retirar una muestra -- se marca
fecha_retiro (mismo criterio que el resto del proyecto: append-only para
conservar historial, ver lims_solicitudes_muestreo/lims_agente_control).
Un índice único FILTRADO (UQ_caja_muestras_activa, WHERE fecha_retiro IS
NULL, ver migrations_cajas.sql) garantiza a nivel de base que una muestra
esté en como máximo una caja activa a la vez -- el SELECT previo al
INSERT en agregar_muestras_a_caja es solo para dar un mensaje claro en el
caso normal (no concurrente); ese índice es la garantía real ante una
carrera entre dos personas agregando la misma muestra a dos cajas a la vez.
"""
from datetime import date
from typing import Optional

import pyodbc
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response

from app.core.security import require_rol
from app.db.connections import limss_db
from app.schemas.cajas import (
    AgregarMuestrasBody,
    AgregarMuestrasResponse,
    CajaCreate,
    CajaDeProducto,
    CajaDetalleResponse,
    CajaResponse,
    MuestraDisponibleResponse,
    MuestraEnCajaResponse,
    MuestraRechazada,
)
from app.services import audit
from app.services.pdf_caja import generar_pdf_etiquetas_cajas

router = APIRouter(prefix="/api/cajas", tags=["Archivo de Contramuestras"])

_ROLES = ("analista_qc", "qa", "admin")

_SELECT_CAJA = """
    SELECT c.*, ua.nombre + ' ' + ua.apellido AS usuario_apertura_nombre,
           uc.nombre + ' ' + uc.apellido AS usuario_cierre_nombre,
           (SELECT COUNT(*) FROM lims_caja_muestras cm
            WHERE cm.id_caja = c.id_caja AND cm.fecha_retiro IS NULL) AS cantidad_muestras
    FROM lims_cajas c
    INNER JOIN lims_usuarios ua ON ua.id_usuario = c.id_usuario_apertura
    LEFT JOIN lims_usuarios uc ON uc.id_usuario = c.id_usuario_cierre
"""

_SELECT_MUESTRA_EN_CAJA = """
    SELECT cm.*, m.codigo_muestra, m.erp_CODART, m.erp_DESART, m.erp_nro_ir,
           ui.nombre + ' ' + ui.apellido AS usuario_ingreso_nombre,
           ur.nombre + ' ' + ur.apellido AS usuario_retiro_nombre
    FROM lims_caja_muestras cm
    INNER JOIN lims_muestras m ON m.id_muestra = cm.id_muestra
    INNER JOIN lims_usuarios ui ON ui.id_usuario = cm.id_usuario_ingreso
    LEFT JOIN lims_usuarios ur ON ur.id_usuario = cm.id_usuario_retiro
"""


def _fila_a_caja(row) -> CajaResponse:
    return CajaResponse(
        id_caja=row.id_caja, codigo=row.codigo, ubicacion=row.ubicacion, estado=row.estado,
        fecha_apertura=row.fecha_apertura, fecha_cierre=row.fecha_cierre,
        usuario_apertura_nombre=row.usuario_apertura_nombre, usuario_cierre_nombre=row.usuario_cierre_nombre,
        observaciones=row.observaciones, cantidad_muestras=row.cantidad_muestras,
    )


def _fila_a_muestra_en_caja(row) -> MuestraEnCajaResponse:
    return MuestraEnCajaResponse(
        id=row.id, id_caja=row.id_caja, id_muestra=row.id_muestra, codigo_muestra=row.codigo_muestra,
        erp_CODART=row.erp_CODART, erp_DESART=row.erp_DESART, erp_nro_ir=row.erp_nro_ir,
        fecha_ingreso=row.fecha_ingreso, usuario_ingreso_nombre=row.usuario_ingreso_nombre,
        fecha_retiro=row.fecha_retiro, usuario_retiro_nombre=row.usuario_retiro_nombre,
    )


def _obtener_caja_o_404(cursor, id_caja: int):
    cursor.execute(_SELECT_CAJA + " WHERE c.id_caja = ?", id_caja)
    row = cursor.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Caja no encontrada")
    return row


# ── Cajas: alta, listado, cerrar/reabrir ──────────────────────────

@router.get("/proximo-codigo")
def proximo_codigo(
    user: dict = Depends(require_rol(*_ROLES)),
    conn: pyodbc.Connection = Depends(limss_db),
):
    """Sugerencia de correlativo "CAJA-2026-001" -- el campo queda editable
    en el formulario, esto es solo un valor por defecto."""
    cursor = conn.cursor()
    anio = date.today().year
    cursor.execute("SELECT MAX(codigo) AS ultimo FROM lims_cajas WHERE codigo LIKE ?", f"CAJA-{anio}-%")
    ultimo = cursor.fetchone().ultimo
    try:
        correlativo = int(ultimo.split("-")[-1]) + 1 if ultimo else 1
    except ValueError:
        correlativo = 1
    return {"codigo_sugerido": f"CAJA-{anio}-{correlativo:03d}"}


@router.get("/reportes/por-producto", response_model=list[CajaDeProducto])
def buscar_cajas_por_producto(
    buscar: str = Query(..., min_length=1),
    user: dict = Depends(require_rol(*_ROLES)),
    conn: pyodbc.Connection = Depends(limss_db),
):
    """Dado un CODART o nombre de material, en qué caja/s están archivadas
    actualmente sus contramuestras -- incluye cajas ya cerradas (una
    muestra puede seguir en una caja que después se cerró), solo excluye
    las que ya se retiraron (fecha_retiro IS NULL)."""
    cursor = conn.cursor()
    like = f"%{buscar}%"
    cursor.execute(
        """
        SELECT c.id_caja, c.codigo AS codigo_caja, c.estado AS estado_caja,
               m.id_muestra, m.codigo_muestra, m.erp_CODART, m.erp_DESART, cm.fecha_ingreso
        FROM lims_caja_muestras cm
        INNER JOIN lims_cajas c ON c.id_caja = cm.id_caja
        INNER JOIN lims_muestras m ON m.id_muestra = cm.id_muestra
        WHERE cm.fecha_retiro IS NULL AND (m.erp_CODART LIKE ? OR m.erp_DESART LIKE ?)
        ORDER BY c.estado, m.erp_DESART
        """,
        like, like,
    )
    return [
        CajaDeProducto(
            id_caja=r.id_caja, codigo_caja=r.codigo_caja, estado_caja=r.estado_caja,
            id_muestra=r.id_muestra, codigo_muestra=r.codigo_muestra,
            erp_CODART=r.erp_CODART, erp_DESART=r.erp_DESART, fecha_ingreso=r.fecha_ingreso,
        )
        for r in cursor.fetchall()
    ]


@router.get("/muestras-disponibles", response_model=list[MuestraDisponibleResponse])
def listar_muestras_disponibles(
    buscar: str = Query("", description="Filtra por código de muestra, material o N° de IR"),
    user: dict = Depends(require_rol(*_ROLES)),
    conn: pyodbc.Connection = Depends(limss_db),
):
    """Contramuestras que se pueden agregar a una caja: la especificación
    de la muestra contempla tipo_muestra='contramuestra' Y la muestra no
    tiene ninguna fila activa en lims_caja_muestras (fecha_retiro IS NULL,
    o sea que no está ya archivada en otra caja). La pantalla muestra esta
    lista directamente en vez de un buscador -- el filtro de acá es solo
    para acotarla cuando es larga, no el mecanismo de selección."""
    cursor = conn.cursor()
    like = f"%{buscar}%"
    cursor.execute(
        """
        SELECT m.id_muestra, m.codigo_muestra, m.erp_CODART, m.erp_DESART, m.erp_nro_ir, m.fecha_muestreo
        FROM lims_muestras m
        WHERE EXISTS (
                  SELECT 1 FROM lims_especificacion_muestras em
                  WHERE em.id_especificacion = m.id_especificacion AND em.tipo_muestra = 'contramuestra'
              )
          AND NOT EXISTS (
                  SELECT 1 FROM lims_caja_muestras cm
                  WHERE cm.id_muestra = m.id_muestra AND cm.fecha_retiro IS NULL
              )
          AND (m.codigo_muestra LIKE ? OR m.erp_CODART LIKE ? OR m.erp_DESART LIKE ? OR m.erp_nro_ir LIKE ?)
        ORDER BY m.fecha_muestreo DESC
        """,
        like, like, like, like,
    )
    return [
        MuestraDisponibleResponse(
            id_muestra=r.id_muestra, codigo_muestra=r.codigo_muestra, erp_CODART=r.erp_CODART,
            erp_DESART=r.erp_DESART, erp_nro_ir=r.erp_nro_ir, fecha_muestreo=r.fecha_muestreo,
        )
        for r in cursor.fetchall()
    ]


@router.get("/etiquetas")
def descargar_etiquetas_cajas(
    id_cajas: list[int] = Query(..., description="Una o más id_caja -- una página A4 por caja"),
    user: dict = Depends(require_rol(*_ROLES)),
    conn: pyodbc.Connection = Depends(limss_db),
):
    cursor = conn.cursor()
    cajas = [_fila_a_caja(_obtener_caja_o_404(cursor, id_caja)) for id_caja in id_cajas]
    pdf_bytes = generar_pdf_etiquetas_cajas(cajas)
    return Response(
        content=pdf_bytes, media_type="application/pdf",
        headers={"Content-Disposition": 'inline; filename="etiquetas_cajas.pdf"'},
    )


@router.get("", response_model=list[CajaResponse])
def listar_cajas(
    estado: Optional[str] = Query(None, pattern=r"^(activa|cerrada)$"),
    user: dict = Depends(require_rol(*_ROLES)),
    conn: pyodbc.Connection = Depends(limss_db),
):
    cursor = conn.cursor()
    where = " WHERE c.estado = ?" if estado else ""
    params = [estado] if estado else []
    cursor.execute(_SELECT_CAJA + where + " ORDER BY c.fecha_apertura DESC", *params)
    return [_fila_a_caja(r) for r in cursor.fetchall()]


@router.post("", response_model=CajaResponse, status_code=201)
def crear_caja(
    body: CajaCreate,
    user: dict = Depends(require_rol(*_ROLES)),
    conn: pyodbc.Connection = Depends(limss_db),
):
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            INSERT INTO lims_cajas (codigo, ubicacion, estado, fecha_apertura, id_usuario_apertura, observaciones)
            VALUES (?, ?, 'activa', GETDATE(), ?, ?)
            """,
            body.codigo.strip(), body.ubicacion.strip() if body.ubicacion else None,
            user["id_usuario"], body.observaciones.strip() if body.observaciones else None,
        )
    except pyodbc.IntegrityError:
        raise HTTPException(status_code=400, detail=f"Ya existe una caja con el código '{body.codigo}'")
    cursor.execute("SELECT @@IDENTITY AS id")
    id_caja = int(cursor.fetchone().id)

    audit.registrar(
        conn, entidad="caja", accion="crear", id_usuario=user["id_usuario"], id_entidad=id_caja,
        valor_nuevo={"codigo": body.codigo},
    )

    return _fila_a_caja(_obtener_caja_o_404(cursor, id_caja))


@router.post("/{id_caja}/cerrar", response_model=CajaResponse)
def cerrar_caja(
    id_caja: int,
    user: dict = Depends(require_rol(*_ROLES)),
    conn: pyodbc.Connection = Depends(limss_db),
):
    cursor = conn.cursor()
    row = _obtener_caja_o_404(cursor, id_caja)
    if row.estado != "activa":
        raise HTTPException(status_code=400, detail="La caja ya está cerrada")

    cursor.execute(
        "UPDATE lims_cajas SET estado = 'cerrada', fecha_cierre = GETDATE(), id_usuario_cierre = ? WHERE id_caja = ?",
        user["id_usuario"], id_caja,
    )
    audit.registrar(conn, entidad="caja", accion="cerrar", id_usuario=user["id_usuario"], id_entidad=id_caja)
    return _fila_a_caja(_obtener_caja_o_404(cursor, id_caja))


@router.post("/{id_caja}/reabrir", response_model=CajaResponse)
def reabrir_caja(
    id_caja: int,
    user: dict = Depends(require_rol(*_ROLES)),
    conn: pyodbc.Connection = Depends(limss_db),
):
    """Vuelve la caja a 'activa'. fecha_cierre/id_usuario_cierre de la
    última vez que se cerró quedan como estaban -- es el campo estado el
    que gobierna si la caja acepta movimientos, no la presencia de esos
    campos, así que no hace falta limpiarlos y se conservan como historial
    de cuándo se cerró por última vez."""
    cursor = conn.cursor()
    row = _obtener_caja_o_404(cursor, id_caja)
    if row.estado != "cerrada":
        raise HTTPException(status_code=400, detail="La caja ya está activa")

    cursor.execute("UPDATE lims_cajas SET estado = 'activa' WHERE id_caja = ?", id_caja)
    audit.registrar(conn, entidad="caja", accion="reabrir", id_usuario=user["id_usuario"], id_entidad=id_caja)
    return _fila_a_caja(_obtener_caja_o_404(cursor, id_caja))


# ── Contenido de una caja: alta y retiro de muestras ──────────────

@router.get("/{id_caja}", response_model=CajaDetalleResponse)
def detalle_caja(
    id_caja: int,
    historial: bool = Query(False, description="Si es true, incluye también las muestras ya retiradas"),
    user: dict = Depends(require_rol(*_ROLES)),
    conn: pyodbc.Connection = Depends(limss_db),
):
    cursor = conn.cursor()
    caja = _obtener_caja_o_404(cursor, id_caja)
    where = " WHERE cm.id_caja = ?" if historial else " WHERE cm.id_caja = ? AND cm.fecha_retiro IS NULL"
    cursor.execute(_SELECT_MUESTRA_EN_CAJA + where + " ORDER BY cm.fecha_ingreso DESC", id_caja)
    muestras = [_fila_a_muestra_en_caja(r) for r in cursor.fetchall()]
    return CajaDetalleResponse(**_fila_a_caja(caja).model_dump(), muestras=muestras)


@router.get("/{id_caja}/etiqueta")
def descargar_etiqueta_caja(
    id_caja: int,
    user: dict = Depends(require_rol(*_ROLES)),
    conn: pyodbc.Connection = Depends(limss_db),
):
    cursor = conn.cursor()
    caja = _fila_a_caja(_obtener_caja_o_404(cursor, id_caja))
    pdf_bytes = generar_pdf_etiquetas_cajas([caja])
    return Response(
        content=pdf_bytes, media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="etiqueta_{caja.codigo}.pdf"'},
    )


@router.post("/{id_caja}/muestras", response_model=AgregarMuestrasResponse, status_code=201)
def agregar_muestras_a_caja(
    id_caja: int,
    body: AgregarMuestrasBody,
    user: dict = Depends(require_rol(*_ROLES)),
    conn: pyodbc.Connection = Depends(limss_db),
):
    """Alta múltiple: la pantalla ofrece la lista de contramuestras libres
    (ver listar_muestras_disponibles) con checkboxes, así que lo normal es
    confirmar varias de una sola vez. Se procesan una por una -- si alguna
    falla (no encontrada, o una carrera la archivó en otra caja justo
    antes) no aborta el resto, queda en "rechazadas" con el motivo."""
    cursor = conn.cursor()
    caja = _obtener_caja_o_404(cursor, id_caja)
    if caja.estado != "activa":
        raise HTTPException(status_code=400, detail="La caja está cerrada -- reabrila para poder agregar muestras")

    agregadas: list[MuestraEnCajaResponse] = []
    rechazadas: list[MuestraRechazada] = []

    for id_muestra in body.id_muestras:
        cursor.execute("SELECT codigo_muestra FROM lims_muestras WHERE id_muestra = ?", id_muestra)
        muestra = cursor.fetchone()
        if not muestra:
            rechazadas.append(MuestraRechazada(id_muestra=id_muestra, motivo="Muestra no encontrada"))
            continue

        cursor.execute(
            """
            SELECT c.codigo FROM lims_caja_muestras cm INNER JOIN lims_cajas c ON c.id_caja = cm.id_caja
            WHERE cm.id_muestra = ? AND cm.fecha_retiro IS NULL
            """,
            id_muestra,
        )
        ya_en_caja = cursor.fetchone()
        if ya_en_caja:
            rechazadas.append(MuestraRechazada(
                id_muestra=id_muestra, codigo_muestra=muestra.codigo_muestra,
                motivo=f"Ya está archivada en la caja '{ya_en_caja.codigo}' -- se agregó justo antes de confirmar",
            ))
            continue

        try:
            cursor.execute(
                "INSERT INTO lims_caja_muestras (id_caja, id_muestra, fecha_ingreso, id_usuario_ingreso) "
                "VALUES (?, ?, GETDATE(), ?)",
                id_caja, id_muestra, user["id_usuario"],
            )
        except pyodbc.IntegrityError:
            rechazadas.append(MuestraRechazada(
                id_muestra=id_muestra, codigo_muestra=muestra.codigo_muestra,
                motivo="Se archivó en otra caja en simultáneo -- volvé a intentar",
            ))
            continue

        cursor.execute("SELECT @@IDENTITY AS id")
        id_registro = int(cursor.fetchone().id)
        audit.registrar(
            conn, entidad="caja_muestra", accion="agregar", id_usuario=user["id_usuario"], id_entidad=id_registro,
            valor_nuevo={"id_caja": id_caja, "id_muestra": id_muestra},
        )
        cursor.execute(_SELECT_MUESTRA_EN_CAJA + " WHERE cm.id = ?", id_registro)
        agregadas.append(_fila_a_muestra_en_caja(cursor.fetchone()))

    return AgregarMuestrasResponse(agregadas=agregadas, rechazadas=rechazadas)


@router.post("/{id_caja}/muestras/{id_muestra}/retirar", response_model=MuestraEnCajaResponse)
def retirar_muestra_de_caja(
    id_caja: int,
    id_muestra: int,
    user: dict = Depends(require_rol(*_ROLES)),
    conn: pyodbc.Connection = Depends(limss_db),
):
    cursor = conn.cursor()
    caja = _obtener_caja_o_404(cursor, id_caja)
    if caja.estado != "activa":
        raise HTTPException(status_code=400, detail="La caja está cerrada -- reabrila para poder retirar muestras")

    cursor.execute(
        "SELECT id FROM lims_caja_muestras WHERE id_caja = ? AND id_muestra = ? AND fecha_retiro IS NULL",
        id_caja, id_muestra,
    )
    row = cursor.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Esta muestra no está archivada actualmente en esta caja")

    cursor.execute(
        "UPDATE lims_caja_muestras SET fecha_retiro = GETDATE(), id_usuario_retiro = ? WHERE id = ?",
        user["id_usuario"], row.id,
    )
    audit.registrar(
        conn, entidad="caja_muestra", accion="retirar", id_usuario=user["id_usuario"], id_entidad=row.id,
        valor_nuevo={"id_caja": id_caja, "id_muestra": id_muestra},
    )

    cursor.execute(_SELECT_MUESTRA_EN_CAJA + " WHERE cm.id = ?", row.id)
    return _fila_a_muestra_en_caja(cursor.fetchone())
