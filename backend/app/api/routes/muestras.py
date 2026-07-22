"""
Módulo I: Muestras y Envíos (REQ-ENV-001 a 005).

Digitaliza el flujo desde la toma de muestra hasta el despacho a un laboratorio
externo. El orden de declaración de rutas importa: FastAPI/Starlette matchea la
primera ruta cuyo patrón calza sintácticamente, y "/{id_muestra}" (un solo
segmento, tipo genérico a nivel de ruteo) calzaría con "/laboratorios" si se
declarara antes -- por eso los literales van primero.
"""
from datetime import date, datetime
from typing import Optional

import pyodbc
from fastapi import APIRouter, Depends, HTTPException, Query

from app.core.security import get_current_user, require_rol
from app.db.connections import erp_db, limss_db
from app.schemas.muestras import (
    EnsayoSolicitado,
    EnvioCreate,
    EnvioResponse,
    EtiquetaResponse,
    LaboratorioCreate,
    LaboratorioResponse,
    LaboratorioUpdate,
    LineaIR,
    MaterialEncontrado,
    MuestraCreate,
    MuestraResponse,
    RemitoResponse,
    TestigoEnviado,
    TestigoRemito,
)
from app.services import audit
from app.services.erp_ir import buscar_lineas_ir, formatear_nro_ir
from app.services.erp_lotes import buscar_lote
from app.services.erp_materiales import CODSAR_POR_TIPO

router = APIRouter(prefix="/api/muestras", tags=["Muestras y Envíos"])


# ── Helpers internos ─────────────────────────────────────────────

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
        cantidad_enviada=float(row.cantidad_enviada) if row.cantidad_enviada is not None else None,
        unidad_enviada=row.unidad_enviada,
        id_especificacion=row.id_especificacion,
        estado=row.estado,
        id_usuario_muestreo=row.id_usuario_muestreo,
        usuario_muestreo_nombre=row.usuario_muestreo_nombre,
        fecha_muestreo=row.fecha_muestreo,
        observaciones=row.observaciones,
    )


def _fila_a_etiqueta(fila, muestra) -> EtiquetaResponse:
    return EtiquetaResponse(
        id_etiqueta=fila.id_etiqueta,
        id_muestra=fila.id_muestra,
        codigo_muestra=muestra.codigo_muestra,
        erp_CODART=muestra.erp_CODART,
        erp_DESART=muestra.erp_DESART,
        tipo_referencia=muestra.tipo_referencia,
        nro_referencia=muestra.nro_referencia,
        fecha_muestreo=muestra.fecha_muestreo,
        usuario_muestreo_nombre=muestra.usuario_muestreo_nombre,
        es_reimpresion=bool(fila.reimpresion),
        id_usuario_impresion=fila.id_usuario,
        fecha_hora=fila.fecha_impresion,
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
    user: dict = Depends(require_rol("analista_qc", "qa", "admin")),
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
    user: dict = Depends(require_rol("analista_qc", "qa", "admin")),
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
    user: dict = Depends(require_rol("analista_qc", "qa", "admin")),
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
    user: dict = Depends(require_rol("muestreador", "analista_qc", "qa", "admin")),
    erp: pyodbc.Connection = Depends(erp_db),
):
    rows = buscar_lineas_ir(erp, nro_ir)
    if not rows:
        raise HTTPException(status_code=404, detail=f"No se encontró el IR '{nro_ir}' en el ERP")
    return [
        LineaIR(
            N01Id=r.N01Id, NUMCOMO=formatear_nro_ir(r.NUMCOMO, r.FECCOM), IdM21=r.IdM21,
            CODART=r.CODART, DESART=r.DESART, CANTID=float(r.CANTID),
            unidad=r.unidad, proveedor=r.proveedor,
            advertencia=(
                f"Este IR corresponde a un artículo de tipo {r.DESSAR.strip()} (no es Materia Prima). "
                "Verificá que el número de IR sea correcto."
                if r.CODSAR is not None and r.CODSAR != "0001" else None
            ),
        )
        for r in rows
    ]


@router.get("/buscar-material", response_model=list[MaterialEncontrado])
def buscar_material(
    tipo: str = Query(..., pattern=r"^(materia_prima|granel|semi_elaborado|producto_terminado)$"),
    referencia: str = Query(..., min_length=1),
    user: dict = Depends(require_rol("muestreador", "analista_qc", "qa", "admin")),
    erp: pyodbc.Connection = Depends(erp_db),
):
    """Búsqueda unificada por tipo: Materia Prima se busca por IR en el ERP
    (GIN01CPB); el resto (Granel/Semi-Elaborado/Producto Terminado) se busca
    por número de lote, también en el ERP pero como atributo del artículo
    (GIM25ALT/GIT52DSC -- ver erp_lotes.py), no por un documento de recepción."""
    if tipo == "materia_prima":
        rows = buscar_lineas_ir(erp, referencia)
        if not rows:
            raise HTTPException(status_code=404, detail=f"No se encontró el IR '{referencia}' en el ERP")
        return [
            MaterialEncontrado(
                referencia=formatear_nro_ir(r.NUMCOMO, r.FECCOM), IdM21=r.IdM21, CODART=r.CODART, DESART=r.DESART,
                cantidad=float(r.CANTID), unidad=r.unidad, proveedor=r.proveedor,
                advertencia=(
                    f"Este IR corresponde a un artículo de tipo {r.DESSAR.strip()} (no es Materia Prima). "
                    "Verificá que el número de IR sea correcto."
                    if r.CODSAR is not None and r.CODSAR != "0001" else None
                ),
            )
            for r in rows
        ]

    rows = buscar_lote(erp, CODSAR_POR_TIPO[tipo], referencia)
    if not rows:
        raise HTTPException(status_code=404, detail=f"No se encontró el lote '{referencia}' en el ERP para este tipo de material")
    return [
        MaterialEncontrado(
            referencia=referencia.strip(), IdM21=r.IdM21, CODART=r.CODART, DESART=r.DESART, unidad=r.unidad,
        )
        for r in rows
    ]


# ── Muestras (REQ-ENV-001) ────────────────────────────────────────

@router.post("/", response_model=MuestraResponse, status_code=201)
def crear_muestra(
    body: MuestraCreate,
    user: dict = Depends(require_rol("muestreador", "analista_qc", "qa", "admin")),
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
        "SELECT id_especificacion, cantidad_muestra, unidad_muestra FROM lims_especificaciones WHERE erp_IdM21 = ? AND vigente = 1",
        body.erp_IdM21,
    )
    espec = cursor.fetchone()
    id_especificacion = espec.id_especificacion if espec else None

    cantidad_enviada = body.cantidad_enviada
    unidad_enviada = body.unidad_enviada
    if cantidad_enviada is None and espec is not None:
        cantidad_enviada = float(espec.cantidad_muestra) if espec.cantidad_muestra is not None else None
        unidad_enviada = espec.unidad_muestra

    cursor.execute(
        """
        INSERT INTO lims_muestras
            (codigo_muestra, tipo_referencia, nro_referencia, erp_IdM21, erp_CODART, erp_DESART,
             erp_cantidad_lote, erp_proveedor, cantidad_enviada, unidad_enviada, id_especificacion, estado,
             id_usuario_muestreo, observaciones)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pendiente_envio', ?, ?)
        """,
        codigo_muestra, body.tipo_referencia, body.nro_referencia, body.erp_IdM21, body.erp_CODART, body.erp_DESART,
        body.erp_cantidad_lote, body.erp_proveedor, cantidad_enviada, unidad_enviada, id_especificacion,
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

@router.get("/{id_muestra}/ensayos-para-envio", response_model=list[EnsayoSolicitado])
def ensayos_para_envio(
    id_muestra: int,
    id_laboratorio: int = Query(...),
    user: dict = Depends(get_current_user),
    conn: pyodbc.Connection = Depends(limss_db),
):
    """Ensayos de la especificación de la muestra que tienen asignado
    justamente el laboratorio elegido para este envío -- el formulario de
    envío recalcula esta lista cada vez que cambia el laboratorio."""
    cursor = conn.cursor()
    cursor.execute("SELECT id_especificacion FROM lims_muestras WHERE id_muestra = ?", id_muestra)
    muestra = cursor.fetchone()
    if not muestra:
        raise HTTPException(status_code=404, detail="Muestra no encontrada")
    if not muestra.id_especificacion:
        return []

    cursor.execute(
        """
        SELECT se.id_espec_ensayo, m.nombre_ensayo, se.requerido_por_defecto, se.id_laboratorio, lab.nombre AS laboratorio_nombre
        FROM lims_especificacion_ensayos se
        INNER JOIN lims_ensayos_maestro m ON m.id_ensayo_maestro = se.id_ensayo_maestro
        INNER JOIN lims_laboratorios lab ON lab.id_laboratorio = se.id_laboratorio
        WHERE se.id_especificacion = ? AND se.id_laboratorio = ?
        ORDER BY se.orden
        """,
        muestra.id_especificacion, id_laboratorio,
    )
    return [
        EnsayoSolicitado(
            id_espec_ensayo=e.id_espec_ensayo, nombre_ensayo=e.nombre_ensayo,
            requerido_por_defecto=bool(e.requerido_por_defecto),
            id_laboratorio=e.id_laboratorio, laboratorio_nombre=e.laboratorio_nombre,
        )
        for e in cursor.fetchall()
    ]


@router.post("/{id_muestra}/envio", response_model=EnvioResponse, status_code=201)
def confirmar_envio(
    id_muestra: int,
    body: EnvioCreate,
    user: dict = Depends(require_rol("analista_qc", "qa", "admin")),
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

    ids_espec_ensayo = body.id_espec_ensayo or []
    if ids_espec_ensayo:
        placeholders = ",".join("?" * len(ids_espec_ensayo))
        cursor.execute(
            f"""
            SELECT se.id_espec_ensayo, m.nombre_ensayo, se.requerido_por_defecto, se.id_laboratorio, lab.nombre AS laboratorio_nombre
            FROM lims_especificacion_ensayos se
            INNER JOIN lims_ensayos_maestro m ON m.id_ensayo_maestro = se.id_ensayo_maestro
            LEFT JOIN lims_laboratorios lab ON lab.id_laboratorio = se.id_laboratorio
            WHERE se.id_especificacion = ? AND se.id_espec_ensayo IN ({placeholders})
            """,
            muestra.id_especificacion, *ids_espec_ensayo,
        )
        ensayos_elegidos = cursor.fetchall()
        if len(ensayos_elegidos) != len(set(ids_espec_ensayo)):
            raise HTTPException(
                status_code=400,
                detail="Alguno de los ensayos indicados no pertenece a la especificación de la muestra",
            )
    else:
        # Sin lista explícita: se solicitan los ensayos que tienen laboratorio
        # asignado (son los que efectivamente se pueden derivar a un lab externo).
        cursor.execute(
            """
            SELECT se.id_espec_ensayo, m.nombre_ensayo, se.requerido_por_defecto, se.id_laboratorio, lab.nombre AS laboratorio_nombre
            FROM lims_especificacion_ensayos se
            INNER JOIN lims_ensayos_maestro m ON m.id_ensayo_maestro = se.id_ensayo_maestro
            LEFT JOIN lims_laboratorios lab ON lab.id_laboratorio = se.id_laboratorio
            WHERE se.id_especificacion = ? AND se.id_laboratorio IS NOT NULL
            """,
            muestra.id_especificacion,
        )
        ensayos_elegidos = cursor.fetchall()

    ids_testigo_permitidos = set()
    if muestra.id_especificacion:
        cursor.execute(
            "SELECT id_testigo FROM lims_especificacion_testigos WHERE id_especificacion = ?",
            muestra.id_especificacion,
        )
        ids_testigo_permitidos = {r.id_testigo for r in cursor.fetchall()}

    hoy = date.today()
    alerta_testigo_por_vencer = False
    testigos_confirmados = []  # testigo_row

    for item in body.testigos:
        if item.id_testigo not in ids_testigo_permitidos:
            raise HTTPException(
                status_code=400,
                detail=f"El testigo {item.id_testigo} no está asociado a la especificación de la muestra",
            )

        cursor.execute("SELECT * FROM lims_testigos WHERE id_testigo = ?", item.id_testigo)
        testigo = cursor.fetchone()
        if not testigo:
            raise HTTPException(status_code=404, detail="Testigo no encontrado")
        if not testigo.activo:
            raise HTTPException(status_code=400, detail=f"El testigo '{testigo.codigo}' está inactivo")

        # Sin fecha de vencimiento cargada, no se puede considerar vencido ni
        # próximo a vencer.
        fecha_vencimiento = _a_fecha(testigo.fecha_vencimiento)
        if fecha_vencimiento is not None:
            if fecha_vencimiento < hoy:
                # REQ-ENV-004-A: bloqueo absoluto, testigo vencido no puede enviarse.
                raise HTTPException(
                    status_code=400,
                    detail=f"El testigo '{testigo.codigo}' está VENCIDO ({fecha_vencimiento}). No se puede confirmar el envío.",
                )
            if (fecha_vencimiento - hoy).days < 30:
                alerta_testigo_por_vencer = True

        testigos_confirmados.append(testigo)

    cursor.execute(
        """
        INSERT INTO lims_envios
            (id_muestra, id_laboratorio,
             temperatura_transporte, nro_remito, transportista,
             analisis_solicitados, protocolo_utilizar, id_usuario_envio)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        id_muestra, body.id_laboratorio,
        body.temperatura_transporte, body.nro_remito, body.transportista,
        body.analisis_solicitados, body.protocolo_utilizar, user["id_usuario"],
    )
    cursor.execute("SELECT @@IDENTITY AS id")
    id_envio = int(cursor.fetchone().id)

    for e in ensayos_elegidos:
        cursor.execute(
            "INSERT INTO lims_envio_ensayos (id_envio, id_espec_ensayo) VALUES (?, ?)",
            id_envio, e.id_espec_ensayo,
        )

    testigos_enviados = []
    for testigo in testigos_confirmados:
        # Solo confirmación de que se incluye en el envío -- el stock se
        # descuenta en el flujo aparte de remitos de testigos, no acá.
        cursor.execute(
            "INSERT INTO lims_envio_testigos (id_envio, id_testigo, cantidad) VALUES (?, ?, 0)",
            id_envio, testigo.id_testigo,
        )

        testigos_enviados.append(TestigoEnviado(
            id_testigo=testigo.id_testigo, codigo=testigo.codigo, nombre=testigo.nombre, nro_ir=testigo.nro_ir,
        ))

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
        testigos=testigos_enviados,
        fecha_despacho=row.fecha_despacho,
        temperatura_transporte=row.temperatura_transporte,
        nro_remito=row.nro_remito,
        transportista=row.transportista,
        analisis_solicitados=row.analisis_solicitados,
        protocolo_utilizar=row.protocolo_utilizar,
        id_usuario_envio=row.id_usuario_envio,
        alerta_testigo_por_vencer=alerta_testigo_por_vencer,
        alerta_reorden=False,
        ensayos_solicitados=[
            EnsayoSolicitado(
                id_espec_ensayo=e.id_espec_ensayo, nombre_ensayo=e.nombre_ensayo,
                requerido_por_defecto=bool(e.requerido_por_defecto),
                id_laboratorio=e.id_laboratorio, laboratorio_nombre=e.laboratorio_nombre,
            )
            for e in ensayos_elegidos
        ],
    )


def _obtener_ensayos_solicitados(cursor, id_envio: int) -> list[EnsayoSolicitado]:
    cursor.execute(
        """
        SELECT se.id_espec_ensayo, m.nombre_ensayo, se.requerido_por_defecto, se.id_laboratorio, lab.nombre AS laboratorio_nombre
        FROM lims_envio_ensayos ee
        INNER JOIN lims_especificacion_ensayos se ON se.id_espec_ensayo = ee.id_espec_ensayo
        INNER JOIN lims_ensayos_maestro m ON m.id_ensayo_maestro = se.id_ensayo_maestro
        LEFT JOIN lims_laboratorios lab ON lab.id_laboratorio = se.id_laboratorio
        WHERE ee.id_envio = ?
        ORDER BY se.orden
        """,
        id_envio,
    )
    return [
        EnsayoSolicitado(
            id_espec_ensayo=e.id_espec_ensayo, nombre_ensayo=e.nombre_ensayo,
            requerido_por_defecto=bool(e.requerido_por_defecto),
            id_laboratorio=e.id_laboratorio, laboratorio_nombre=e.laboratorio_nombre,
        )
        for e in cursor.fetchall()
    ]


def _obtener_testigos_enviados(cursor, id_envio: int) -> list[TestigoEnviado]:
    cursor.execute(
        """
        SELECT t.id_testigo, t.codigo, t.nombre, et.cantidad
        FROM lims_envio_testigos et
        INNER JOIN lims_testigos t ON t.id_testigo = et.id_testigo
        WHERE et.id_envio = ?
        ORDER BY t.codigo
        """,
        id_envio,
    )
    return [
        TestigoEnviado(
            id_testigo=t.id_testigo, codigo=t.codigo, nombre=t.nombre, cantidad=float(t.cantidad),
        )
        for t in cursor.fetchall()
    ]


@router.get("/{id_muestra}/envio", response_model=EnvioResponse)
def obtener_envio(
    id_muestra: int,
    user: dict = Depends(get_current_user),
    conn: pyodbc.Connection = Depends(limss_db),
):
    cursor = conn.cursor()
    cursor.execute(
        "SELECT TOP 1 * FROM lims_envios WHERE id_muestra = ? ORDER BY id_envio DESC",
        id_muestra,
    )
    row = cursor.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="La muestra no tiene un envío confirmado todavía")

    return EnvioResponse(
        id_envio=row.id_envio,
        id_muestra=row.id_muestra,
        id_laboratorio=row.id_laboratorio,
        testigos=_obtener_testigos_enviados(cursor, row.id_envio),
        fecha_despacho=row.fecha_despacho,
        temperatura_transporte=row.temperatura_transporte,
        nro_remito=row.nro_remito,
        transportista=row.transportista,
        analisis_solicitados=row.analisis_solicitados,
        protocolo_utilizar=row.protocolo_utilizar,
        id_usuario_envio=row.id_usuario_envio,
        ensayos_solicitados=_obtener_ensayos_solicitados(cursor, row.id_envio),
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
        SELECT e.id_envio,
               m.codigo_muestra, m.tipo_referencia, m.nro_referencia, m.erp_CODART, m.erp_DESART, m.fecha_muestreo,
               m.cantidad_enviada, m.unidad_enviada,
               u.nombre + ' ' + u.apellido AS usuario_muestreo_nombre,
               e.fecha_despacho, e.temperatura_transporte, e.nro_remito, e.transportista,
               e.analisis_solicitados, e.protocolo_utilizar,
               lab.nombre AS laboratorio_nombre, lab.direccion AS laboratorio_direccion,
               lab.contacto AS laboratorio_contacto
        FROM lims_muestras m
        INNER JOIN lims_envios e ON e.id_muestra = m.id_muestra
        INNER JOIN lims_usuarios u ON u.id_usuario = m.id_usuario_muestreo
        INNER JOIN lims_laboratorios lab ON lab.id_laboratorio = e.id_laboratorio
        WHERE m.id_muestra = ?
        """,
        id_muestra,
    )
    row = cursor.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="La muestra no tiene un envío confirmado todavía")

    cursor.execute(
        """
        SELECT t.id_testigo, t.codigo, t.nombre, t.nro_ir, t.nro_lote, t.fecha_vencimiento
        FROM lims_envio_testigos et
        INNER JOIN lims_testigos t ON t.id_testigo = et.id_testigo
        WHERE et.id_envio = ?
        ORDER BY t.codigo
        """,
        row.id_envio,
    )
    testigos = [
        TestigoRemito(
            id_testigo=t.id_testigo, codigo=t.codigo, nombre=t.nombre, nro_ir=t.nro_ir,
            nro_lote=t.nro_lote, fecha_vencimiento=t.fecha_vencimiento,
        )
        for t in cursor.fetchall()
    ]

    return RemitoResponse(
        id_envio=row.id_envio,
        codigo_muestra=row.codigo_muestra,
        tipo_referencia=row.tipo_referencia,
        nro_referencia=row.nro_referencia,
        erp_CODART=row.erp_CODART,
        erp_DESART=row.erp_DESART,
        fecha_muestreo=row.fecha_muestreo,
        usuario_muestreo_nombre=row.usuario_muestreo_nombre,
        cantidad_enviada=float(row.cantidad_enviada) if row.cantidad_enviada is not None else None,
        unidad_enviada=row.unidad_enviada,
        laboratorio_nombre=row.laboratorio_nombre,
        laboratorio_direccion=row.laboratorio_direccion,
        laboratorio_contacto=row.laboratorio_contacto,
        fecha_despacho=row.fecha_despacho,
        temperatura_transporte=row.temperatura_transporte,
        nro_remito=row.nro_remito,
        transportista=row.transportista,
        analisis_solicitados=row.analisis_solicitados,
        protocolo_utilizar=row.protocolo_utilizar,
        ensayos_solicitados=_obtener_ensayos_solicitados(cursor, row.id_envio),
        testigos=testigos,
    )


# ── Etiquetas (REQ-ENV-003) ────────────────────────────────────────

@router.post("/{id_muestra}/etiqueta", response_model=EtiquetaResponse, status_code=201)
def generar_etiqueta(
    id_muestra: int,
    user: dict = Depends(require_rol("muestreador", "analista_qc", "qa", "admin")),
    conn: pyodbc.Connection = Depends(limss_db),
):
    """Genera (e imprime) una etiqueta para la muestra. Cada llamada registra
    una fila nueva en lims_etiquetas -- la primera es la impresión original,
    las siguientes quedan marcadas como reimpresión."""
    cursor = conn.cursor()
    cursor.execute(_SELECT_MUESTRA + " WHERE m.id_muestra = ?", id_muestra)
    muestra = cursor.fetchone()
    if not muestra:
        raise HTTPException(status_code=404, detail="Muestra no encontrada")

    cursor.execute("SELECT COUNT(*) AS n FROM lims_etiquetas WHERE id_muestra = ?", id_muestra)
    es_reimpresion = cursor.fetchone().n > 0

    cursor.execute(
        "INSERT INTO lims_etiquetas (id_muestra, id_usuario, reimpresion) VALUES (?, ?, ?)",
        id_muestra, user["id_usuario"], es_reimpresion,
    )
    cursor.execute("SELECT @@IDENTITY AS id")
    id_etiqueta = int(cursor.fetchone().id)

    audit.registrar(
        conn, entidad="etiqueta", accion="reimprimir" if es_reimpresion else "imprimir",
        id_usuario=user["id_usuario"], id_entidad=id_etiqueta,
        valor_nuevo={"id_muestra": id_muestra, "reimpresion": es_reimpresion},
    )

    cursor.execute("SELECT * FROM lims_etiquetas WHERE id_etiqueta = ?", id_etiqueta)
    return _fila_a_etiqueta(cursor.fetchone(), muestra)


@router.get("/{id_muestra}/etiqueta", response_model=EtiquetaResponse)
def obtener_ultima_etiqueta(
    id_muestra: int,
    user: dict = Depends(get_current_user),
    conn: pyodbc.Connection = Depends(limss_db),
):
    cursor = conn.cursor()
    cursor.execute(_SELECT_MUESTRA + " WHERE m.id_muestra = ?", id_muestra)
    muestra = cursor.fetchone()
    if not muestra:
        raise HTTPException(status_code=404, detail="Muestra no encontrada")

    cursor.execute(
        "SELECT TOP 1 * FROM lims_etiquetas WHERE id_muestra = ? ORDER BY id_etiqueta DESC",
        id_muestra,
    )
    fila = cursor.fetchone()
    if not fila:
        raise HTTPException(status_code=404, detail="Todavía no se generó ninguna etiqueta para esta muestra")
    return _fila_a_etiqueta(fila, muestra)
