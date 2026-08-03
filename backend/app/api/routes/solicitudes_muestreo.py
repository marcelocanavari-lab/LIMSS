"""
Solicitud de Muestreo para Materias Primas.

Flujo real (reestructurado):
  Etapa 1 -- QA crea la solicitud y asigna un muestreador (estado 'pendiente').
  Etapa 2 -- El muestreador ve sus solicitudes asignadas (GET /mis-solicitudes)
             y ejecuta el muestreo completando la Orden de Trabajo digital:
             SOLO datos físicos observables (contenedor, identificación de la
             MP, N° de bultos muestreados, observaciones). El muestreador
             NUNCA carga resultados de ensayos -- eso es tarea de QC/QA. Al
             confirmar (POST .../orden-trabajo-digital) se crea la muestra
             automáticamente en estado 'pendiente_envio', se vincula a la
             solicitud, y esta pasa a 'ejecutada'. No existe un paso manual
             separado de "ejecutar" ni de "crear muestra desde la solicitud":
             todo ocurre en esa única confirmación.
  Etapa 3 -- QC/QA ve la muestra en 'pendiente_envio' en el módulo de Envío
             de Muestras (ya existente), genera el/los envío(s) al/los
             laboratorio(s) correspondiente(s) y carga los resultados por
             envío -- sin distinción de "laboratorio interno", todos los
             ensayos de la especificación pasan por ese mismo flujo.
  Etapa 4 -- Dictamen QA agrega los resultados de todos los envíos sobre la
             misma muestra -- ver app/services/recorrido.py y
             app/api/routes/dictamenes.py.

La búsqueda del IR reutiliza app.services.erp_ir (mismo módulo que usa
buscar_material en muestras.py) en vez de repetir la consulta a mano: ya
resuelve el tipo de comprobante 'IR' dinámicamente, filtra por año a partir
del formato "NNN/AA", y contempla la colisión de numeración de la carga
inicial del ERP (2020-04-02) -- repetir esa lógica acá hubiera reintroducido
esos mismos bugs ya resueltos.
"""
from datetime import date, datetime
from typing import Optional

import pyodbc
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response

from app.core.security import get_current_user, require_rol
from app.db.connections import erp_db, limss_db
from app.schemas.solicitudes_muestreo import (
    DatosFisicosMuestreo,
    EnsayoSolicitudMuestreo,
    EnsayosParaOrdenResponse,
    MuestreadorDisponible,
    OrdenTrabajoDigitalBody,
    OrdenTrabajoDigitalResponse,
    ResultadoOrdenTrabajoInput,
    SolicitudMuestreoAnular,
    SolicitudMuestreoCreate,
    SolicitudMuestreoDetalle,
    SolicitudMuestreoResponse,
)
from app.services import audit
from app.services.erp_ir import buscar_lineas_ir, formatear_nro_ir, normalizar_fecha_sentinel
from app.services.pdf_solicitud_muestreo import (
    generar_pdf_etiquetas,
    generar_pdf_etiquetas_v2,
    generar_pdf_formulario,
    generar_pdf_orden_trabajo,
    generar_pdf_planilla_muestreo,
)

router = APIRouter(prefix="/api/solicitudes-muestreo", tags=["Solicitudes de Muestreo"])

_ROLES_MUESTREADOR_O_SUPERIOR = ("muestreador", "analista_qc", "qa", "admin")


def _a_datetime(valor: Optional[date]) -> Optional[datetime]:
    """El driver ODBC "SQL Server" (legacy, configurado en .env) no puede
    bindear objetos date de Python (SQLBindParameter falla) -- se convierte
    a datetime, que sí soporta (mismo problema y mismo fix que en
    auditoria.py)."""
    if valor is None:
        return None
    return datetime.combine(valor, datetime.min.time())


def _a_fecha(valor) -> Optional[date]:
    if valor is None:
        return None
    return valor.date() if hasattr(valor, "date") else valor


def _g(row, atributo: str):
    """Lee un atributo que puede no existir todavía en el esquema real (ver
    migrations_solicitudes_muestreo_datos_fisicos_v2.sql, pendiente de
    ejecutar en algunos entornos) -- getattr con default None en vez de
    romper toda la respuesta por columnas nuevas que todavía no están."""
    return getattr(row, atributo, None)


_SELECT_SOLICITUD = """
    SELECT s.*, lab.nombre AS laboratorio_nombre, u.nombre + ' ' + u.apellido AS usuario_qa,
           um.nombre + ' ' + um.apellido AS muestreador_nombre
    FROM lims_solicitudes_muestreo s
    INNER JOIN lims_laboratorios lab ON lab.id_laboratorio = s.id_laboratorio
    INNER JOIN lims_usuarios u ON u.id_usuario = s.id_usuario_qa
    LEFT JOIN lims_usuarios um ON um.id_usuario = s.id_muestreador
"""


def _fila_a_solicitud(row) -> SolicitudMuestreoResponse:
    return SolicitudMuestreoResponse(
        id_solicitud=row.id_solicitud,
        nro_solicitud=row.nro_solicitud,
        erp_nro_ir=row.erp_nro_ir,
        erp_CODART=row.erp_CODART,
        erp_DESART=row.erp_DESART,
        id_laboratorio=row.id_laboratorio,
        laboratorio_nombre=row.laboratorio_nombre,
        id_muestreador=row.id_muestreador,
        muestreador_nombre=row.muestreador_nombre,
        estado=row.estado,
        fecha_solicitud=row.fecha_solicitud,
        usuario_qa=row.usuario_qa,
        id_muestra=row.id_muestra,
        observaciones=row.observaciones,
        proveedor_codigo=row.proveedor_codigo,
        proveedor_nombre=row.proveedor_nombre,
        fecha_ingreso=row.fecha_ingreso,
        fecha_vencimiento=row.fecha_vencimiento,
        cantidad_ingresada=float(row.cantidad_ingresada) if row.cantidad_ingresada is not None else None,
        unidad_cantidad=row.unidad_cantidad,
        lote_proveedor=row.lote_proveedor,
        fecha_reanalisis=row.fecha_reanalisis,
        pais_origen=row.pais_origen,
        nro_bultos=row.nro_bultos,
        metodologia_analisis=row.metodologia_analisis,
        fabricante=row.fabricante,
        aspecto_externo=row.aspecto_externo,
        cierre=row.cierre,
        aspecto_interno=row.aspecto_interno,
        precintos=row.precintos,
        materias_extranas=row.materias_extranas,
        olor=row.olor,
        color=row.color,
        nro_bultos_muestreados=row.nro_bultos_muestreados,
        observaciones_muestreo=row.observaciones_muestreo,
        identificacion_contenedor=_g(row, "identificacion_contenedor"),
        fecha_vencimiento_real=_a_fecha(_g(row, "fecha_vencimiento_real")),
        fecha_reanalisis_real=_a_fecha(_g(row, "fecha_reanalisis_real")),
        aspecto_mp=_g(row, "aspecto_mp"),
    )


def _obtener_solicitud_o_404(cursor, id_solicitud: int):
    cursor.execute(_SELECT_SOLICITUD + " WHERE s.id_solicitud = ?", id_solicitud)
    row = cursor.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Solicitud no encontrada")
    return row


def _obtener_cantidades(cursor, id_especificacion: Optional[int]) -> dict:
    if id_especificacion is None:
        return {"cantidad_muestra": None, "unidad_muestra": None, "cantidad_contramuestra": None, "unidad_contramuestra": None}
    cursor.execute(
        "SELECT cantidad_muestra, unidad_muestra, cantidad_contramuestra, unidad_contramuestra "
        "FROM lims_especificaciones WHERE id_especificacion = ?",
        id_especificacion,
    )
    espec = cursor.fetchone()
    if not espec:
        return {"cantidad_muestra": None, "unidad_muestra": None, "cantidad_contramuestra": None, "unidad_contramuestra": None}
    return {
        "cantidad_muestra": float(espec.cantidad_muestra) if espec.cantidad_muestra is not None else None,
        "unidad_muestra": espec.unidad_muestra,
        "cantidad_contramuestra": float(espec.cantidad_contramuestra) if espec.cantidad_contramuestra is not None else None,
        "unidad_contramuestra": espec.unidad_contramuestra,
    }


def _obtener_ensayos(cursor, id_solicitud: int, id_especificacion: Optional[int], id_laboratorio: int) -> list[EnsayoSolicitudMuestreo]:
    """Ensayos del laboratorio elegido al crear la solicitud, con su
    resultado ya cargado en la Orden de Trabajo digital si lo hay -- LEFT
    JOIN por id_solicitud, así que antes de confirmar el muestreo todos los
    valores vienen en None (mismo shape para el formulario en blanco, la
    Orden de Trabajo impresa ya completada, y GET .../ensayos-para-orden)."""
    if id_especificacion is None:
        return []
    cursor.execute(
        """
        SELECT ee.id_espec_ensayo, ee.orden, m.nombre_ensayo, ee.metodologia, ee.tipo_dato, ee.limite_inferior,
               ee.limite_superior, ee.unidad_medida, ee.valor_requerido, ee.especificacion_texto, ee.obligatorio,
               r.valor_numerico, r.valor_cualitativo, r.dentro_especificacion
        FROM lims_especificacion_ensayos ee
        INNER JOIN lims_ensayos_maestro m ON m.id_ensayo_maestro = ee.id_ensayo_maestro
        LEFT JOIN lims_orden_trabajo_resultados r ON r.id_espec_ensayo = ee.id_espec_ensayo AND r.id_solicitud = ?
        WHERE ee.id_especificacion = ? AND ee.id_laboratorio = ?
        ORDER BY ee.orden
        """,
        id_solicitud, id_especificacion, id_laboratorio,
    )
    return [
        EnsayoSolicitudMuestreo(
            id_espec_ensayo=e.id_espec_ensayo, orden=e.orden,
            nombre_ensayo=e.nombre_ensayo, metodologia=e.metodologia, tipo_dato=e.tipo_dato,
            limite_inferior=float(e.limite_inferior) if e.limite_inferior is not None else None,
            limite_superior=float(e.limite_superior) if e.limite_superior is not None else None,
            unidad_medida=e.unidad_medida, valor_requerido=e.valor_requerido,
            especificacion_texto=e.especificacion_texto, obligatorio=bool(e.obligatorio),
            valor_numerico=float(e.valor_numerico) if e.valor_numerico is not None else None,
            valor_cualitativo=e.valor_cualitativo,
            dentro_especificacion=bool(e.dentro_especificacion) if e.dentro_especificacion is not None else None,
        )
        for e in cursor.fetchall()
    ]


def _calcular_dentro_especificacion(ensayo: EnsayoSolicitudMuestreo, valor_numerico, valor_cualitativo) -> Optional[bool]:
    """Misma lógica que resultados.py -- se duplica acá (en vez de importarla
    entre routers) porque cada router de este proyecto es autocontenido."""
    if ensayo.tipo_dato == "numerico":
        if valor_numerico is None or ensayo.limite_inferior is None or ensayo.limite_superior is None:
            return None
        return ensayo.limite_inferior <= valor_numerico <= ensayo.limite_superior
    if not valor_cualitativo or not valor_cualitativo.strip():
        return None
    return valor_cualitativo.strip().lower() == "cumple"


def _tiene_valor_ot(r: Optional[ResultadoOrdenTrabajoInput]) -> bool:
    return r is not None and (r.valor_numerico is not None or bool((r.valor_cualitativo or "").strip()))


@router.get("", response_model=list[SolicitudMuestreoResponse])
def listar_solicitudes(
    estado: Optional[str] = Query(None, pattern=r"^(pendiente|ejecutada|anulada)$"),
    id_muestreador: Optional[int] = Query(None),
    user: dict = Depends(get_current_user),
    conn: pyodbc.Connection = Depends(limss_db),
):
    cursor = conn.cursor()
    condiciones = []
    params: list = []
    if estado:
        condiciones.append("s.estado = ?")
        params.append(estado)
    if id_muestreador:
        condiciones.append("s.id_muestreador = ?")
        params.append(id_muestreador)
    where = ("WHERE " + " AND ".join(condiciones)) if condiciones else ""
    cursor.execute(_SELECT_SOLICITUD + f" {where} ORDER BY s.fecha_solicitud DESC", *params)
    return [_fila_a_solicitud(r) for r in cursor.fetchall()]


@router.get("/muestreadores", response_model=list[MuestreadorDisponible])
def listar_muestreadores(
    user: dict = Depends(require_rol("qa", "admin")),
    conn: pyodbc.Connection = Depends(limss_db),
):
    """Usuarios con rol 'muestreador' activos, para el dropdown de "Muestreador
    asignado" al crear la solicitud (Etapa 1). Ruta literal -- debe declararse
    antes de "/{id_solicitud}"."""
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id_usuario, nombre, apellido FROM lims_usuarios WHERE rol = 'muestreador' AND activo = 1 ORDER BY apellido, nombre"
    )
    return [
        MuestreadorDisponible(id_usuario=r.id_usuario, nombre_completo=f"{r.nombre} {r.apellido}")
        for r in cursor.fetchall()
    ]


@router.get("/mis-solicitudes", response_model=list[SolicitudMuestreoResponse])
def listar_mis_solicitudes(
    user: dict = Depends(require_rol(*_ROLES_MUESTREADOR_O_SUPERIOR)),
    conn: pyodbc.Connection = Depends(limss_db),
):
    """Bandeja del muestreador (Etapa 2): solo lo que tiene asignado y sigue
    pendiente de ejecutar. Ruta literal -- debe declararse antes de
    "/{id_solicitud}" para que no se intente interpretar "mis-solicitudes"
    como un id."""
    cursor = conn.cursor()
    cursor.execute(
        _SELECT_SOLICITUD + " WHERE s.id_muestreador = ? AND s.estado = 'pendiente' ORDER BY s.fecha_solicitud ASC",
        user["id_usuario"],
    )
    return [_fila_a_solicitud(r) for r in cursor.fetchall()]


def _generar_nro_solicitud(cursor) -> str:
    anio = date.today().year
    cursor.execute(
        "SELECT MAX(nro_solicitud) AS ultimo FROM lims_solicitudes_muestreo WHERE nro_solicitud LIKE ?",
        f"SOL-{anio}-%",
    )
    ultimo = cursor.fetchone().ultimo
    correlativo = int(ultimo.split("-")[-1]) + 1 if ultimo else 1
    return f"SOL-{anio}-{correlativo:03d}"


def _generar_codigo_muestra(cursor) -> str:
    anio = date.today().year
    cursor.execute(
        "SELECT MAX(codigo_muestra) AS ultimo FROM lims_muestras WHERE codigo_muestra LIKE ?",
        f"SAMP-{anio}-%",
    )
    ultimo = cursor.fetchone().ultimo
    correlativo = int(ultimo.split("-")[-1]) + 1 if ultimo else 1
    return f"SAMP-{anio}-{correlativo:04d}"


@router.post("", response_model=SolicitudMuestreoResponse, status_code=201)
def crear_solicitud(
    body: SolicitudMuestreoCreate,
    user: dict = Depends(require_rol("qa", "admin")),
    erp: pyodbc.Connection = Depends(erp_db),
    conn: pyodbc.Connection = Depends(limss_db),
):
    lineas = buscar_lineas_ir(erp, body.erp_nro_ir)
    if not lineas:
        raise HTTPException(status_code=404, detail=f"No se encontró el IR '{body.erp_nro_ir}' en el ERP")
    linea = lineas[0]

    cursor = conn.cursor()

    cursor.execute("SELECT 1 FROM lims_laboratorios WHERE id_laboratorio = ? AND activo = 1", body.id_laboratorio)
    if not cursor.fetchone():
        raise HTTPException(status_code=404, detail="El laboratorio indicado no existe o está inactivo")

    cursor.execute("SELECT rol, activo FROM lims_usuarios WHERE id_usuario = ?", body.id_muestreador)
    muestreador = cursor.fetchone()
    if not muestreador or not muestreador.activo:
        raise HTTPException(status_code=404, detail="El muestreador indicado no existe o está inactivo")
    if muestreador.rol not in _ROLES_MUESTREADOR_O_SUPERIOR:
        raise HTTPException(status_code=400, detail="El usuario asignado no tiene un rol habilitado para muestrear")

    cursor.execute(
        "SELECT id_especificacion, cantidad_muestra, cantidad_contramuestra "
        "FROM lims_especificaciones WHERE erp_IdM21 = ? AND vigente = 1",
        linea.IdM21,
    )
    espec = cursor.fetchone()
    if not espec:
        raise HTTPException(
            status_code=400,
            detail=f"El artículo '{linea.CODART}' no tiene una especificación vigente cargada en Datos Maestros",
        )
    # cantidad_muestra/cantidad_contramuestra quedaron deprecados a favor de
    # lims_especificacion_muestras (varias muestras posibles, no solo
    # análisis/contramuestra) -- ya no se exigen acá; si la especificación
    # no tiene muestras definidas, el frontend solo muestra una advertencia,
    # no bloquea la creación de la solicitud.

    cursor.execute(
        "SELECT 1 FROM lims_especificacion_ensayos WHERE id_especificacion = ? AND id_laboratorio = ?",
        espec.id_especificacion, body.id_laboratorio,
    )
    if not cursor.fetchone():
        raise HTTPException(
            status_code=400,
            detail="El laboratorio seleccionado no tiene ensayos asignados para la especificación de este artículo",
        )

    if body.muestras:
        ids_muestra_espec = {m.id_espec_muestra for m in body.muestras}
        placeholders = ",".join("?" * len(ids_muestra_espec))
        cursor.execute(
            f"SELECT id FROM lims_especificacion_muestras WHERE id_especificacion = ? AND id IN ({placeholders})",
            espec.id_especificacion, *ids_muestra_espec,
        )
        ids_validos = {r.id for r in cursor.fetchall()}
        if ids_validos != ids_muestra_espec:
            raise HTTPException(
                status_code=400,
                detail="Alguna de las muestras indicadas no pertenece a la especificación de este artículo",
            )

    nro_ir_normalizado = formatear_nro_ir(linea.NUMCOMO, linea.FECCOM)
    nro_solicitud = _generar_nro_solicitud(cursor)

    fecha_ingreso = normalizar_fecha_sentinel(linea.FECCOM)
    fecha_vencimiento = normalizar_fecha_sentinel(linea.VENCOM)
    cantidad_ingresada = float(linea.cantidad_total) if linea.cantidad_total is not None else None

    cursor.execute(
        """
        INSERT INTO lims_solicitudes_muestreo
            (nro_solicitud, erp_nro_ir, erp_IdM21, erp_CODART, erp_DESART, id_especificacion,
             id_laboratorio, id_muestreador, observaciones, estado, id_usuario_qa,
             proveedor_codigo, proveedor_nombre, lote_proveedor, fecha_ingreso, fecha_vencimiento,
             fecha_reanalisis, pais_origen, cantidad_ingresada, unidad_cantidad, nro_bultos,
             metodologia_analisis, fabricante)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'pendiente', ?,
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        nro_solicitud, nro_ir_normalizado, linea.IdM21, linea.CODART, linea.DESART, espec.id_especificacion,
        body.id_laboratorio, body.id_muestreador, body.observaciones, user["id_usuario"],
        body.proveedor_codigo, body.proveedor_nombre, body.lote_proveedor, _a_datetime(fecha_ingreso), _a_datetime(fecha_vencimiento),
        _a_datetime(body.fecha_reanalisis), body.pais_origen, cantidad_ingresada, linea.unidad, body.nro_bultos,
        body.metodologia_analisis, body.fabricante,
    )
    cursor.execute("SELECT @@IDENTITY AS id")
    id_solicitud = int(cursor.fetchone().id)

    if body.muestras:
        cursor.execute("SELECT OBJECT_ID('lims_solicitud_muestras') AS oid")
        if cursor.fetchone().oid is not None:
            for m in body.muestras:
                cursor.execute(
                    """
                    INSERT INTO lims_solicitud_muestras (id_solicitud, id_espec_muestra, cantidad_real, confirmada)
                    VALUES (?, ?, ?, ?)
                    """,
                    id_solicitud, m.id_espec_muestra, m.cantidad_real, 1 if m.confirmada else 0,
                )
        # Si la tabla todavía no existe en este entorno (ver migrations_
        # solicitud_muestras.sql, pendiente de ejecutar), se omite sin
        # romper la creación de la solicitud -- las etiquetas caen al
        # modelo legacy de 2 fijas (ver descargar_etiquetas).

    audit.registrar(
        conn, entidad="solicitud_muestreo", accion="crear",
        id_usuario=user["id_usuario"], id_entidad=id_solicitud,
        valor_nuevo={
            "nro_solicitud": nro_solicitud, "erp_nro_ir": nro_ir_normalizado,
            "id_laboratorio": body.id_laboratorio, "id_muestreador": body.id_muestreador,
        },
    )

    return _fila_a_solicitud(_obtener_solicitud_o_404(cursor, id_solicitud))


@router.get("/{id_solicitud}", response_model=SolicitudMuestreoDetalle)
def detalle_solicitud(
    id_solicitud: int,
    user: dict = Depends(get_current_user),
    conn: pyodbc.Connection = Depends(limss_db),
):
    cursor = conn.cursor()
    row = _obtener_solicitud_o_404(cursor, id_solicitud)
    cantidades = _obtener_cantidades(cursor, row.id_especificacion)
    ensayos = _obtener_ensayos(cursor, id_solicitud, row.id_especificacion, row.id_laboratorio)

    base = _fila_a_solicitud(row)
    return SolicitudMuestreoDetalle(
        **base.model_dump(),
        erp_IdM21=row.erp_IdM21,
        id_especificacion=row.id_especificacion,
        cantidad_muestra=cantidades["cantidad_muestra"],
        unidad_muestra=cantidades["unidad_muestra"],
        cantidad_contramuestra=cantidades["cantidad_contramuestra"],
        unidad_contramuestra=cantidades["unidad_contramuestra"],
        ensayos=ensayos,
    )


@router.get("/{id_solicitud}/formulario")
def descargar_formulario(
    id_solicitud: int,
    user: dict = Depends(get_current_user),
    conn: pyodbc.Connection = Depends(limss_db),
):
    cursor = conn.cursor()
    row = _obtener_solicitud_o_404(cursor, id_solicitud)
    cantidades = _obtener_cantidades(cursor, row.id_especificacion)
    ensayos = _obtener_ensayos(cursor, id_solicitud, row.id_especificacion, row.id_laboratorio)

    pdf_bytes = generar_pdf_formulario(row, cantidades, ensayos)
    return Response(
        content=pdf_bytes, media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{row.nro_solicitud}_formulario.pdf"'},
    )


@router.get("/{id_solicitud}/orden-trabajo")
def descargar_orden_trabajo(
    id_solicitud: int,
    user: dict = Depends(get_current_user),
    conn: pyodbc.Connection = Depends(limss_db),
):
    """Réplica impresa de P_CC002-1 (Orden de Trabajo de Control de Calidad) --
    distinta de la Orden de Trabajo DIGITAL (ensayos-para-orden/orden-trabajo-digital)."""
    cursor = conn.cursor()
    row = _obtener_solicitud_o_404(cursor, id_solicitud)
    cantidades = _obtener_cantidades(cursor, row.id_especificacion)
    ensayos = _obtener_ensayos(cursor, id_solicitud, row.id_especificacion, row.id_laboratorio)

    pdf_bytes = generar_pdf_orden_trabajo(row, cantidades, ensayos)
    return Response(
        content=pdf_bytes, media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{row.nro_solicitud}_orden_trabajo.pdf"'},
    )


@router.get("/{id_solicitud}/planilla-muestreo")
def descargar_planilla_muestreo(
    id_solicitud: int,
    user: dict = Depends(get_current_user),
    conn: pyodbc.Connection = Depends(limss_db),
):
    """Réplica de P_CC002-2 (Planilla de Muestreo de Materias Primas)."""
    cursor = conn.cursor()
    row = _obtener_solicitud_o_404(cursor, id_solicitud)

    pdf_bytes = generar_pdf_planilla_muestreo(row)
    return Response(
        content=pdf_bytes, media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{row.nro_solicitud}_planilla_muestreo.pdf"'},
    )


def _obtener_muestras_confirmadas(cursor, id_solicitud: int):
    """Filas de lims_solicitud_muestras confirmadas para esta solicitud, con
    los datos de la muestra definida (tipo/unidad/laboratorio) -- una
    etiqueta por fila. Lista vacía si la tabla todavía no existe en este
    entorno (ver migrations_solicitud_muestras.sql, pendiente de ejecutar) o
    si la solicitud no tiene ninguna fila (solicitudes creadas antes de esta
    funcionalidad): en ambos casos, descargar_etiquetas cae al modelo legacy
    de 2 etiquetas fijas."""
    cursor.execute("SELECT OBJECT_ID('lims_solicitud_muestras') AS oid")
    if cursor.fetchone().oid is None:
        return []
    cursor.execute(
        """
        SELECT sm.cantidad_real, em.tipo_muestra, em.unidad, lab.nombre AS laboratorio_nombre
        FROM lims_solicitud_muestras sm
        INNER JOIN lims_especificacion_muestras em ON em.id = sm.id_espec_muestra
        LEFT JOIN lims_laboratorios lab ON lab.id_laboratorio = em.id_laboratorio
        WHERE sm.id_solicitud = ? AND sm.confirmada = 1
        ORDER BY em.orden
        """,
        id_solicitud,
    )
    return cursor.fetchall()


@router.get("/{id_solicitud}/etiquetas")
def descargar_etiquetas(
    id_solicitud: int,
    user: dict = Depends(get_current_user),
    conn: pyodbc.Connection = Depends(limss_db),
):
    cursor = conn.cursor()
    row = _obtener_solicitud_o_404(cursor, id_solicitud)

    muestras_confirmadas = _obtener_muestras_confirmadas(cursor, id_solicitud)
    if muestras_confirmadas:
        pdf_bytes = generar_pdf_etiquetas_v2(row, muestras_confirmadas)
    else:
        cantidades = _obtener_cantidades(cursor, row.id_especificacion)
        pdf_bytes = generar_pdf_etiquetas(row, cantidades)

    return Response(
        content=pdf_bytes, media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{row.nro_solicitud}_etiquetas.pdf"'},
    )


@router.get("/{id_solicitud}/ensayos-para-orden", response_model=EnsayosParaOrdenResponse)
def ensayos_para_orden(
    id_solicitud: int,
    user: dict = Depends(get_current_user),
    conn: pyodbc.Connection = Depends(limss_db),
):
    """Sección B de la Orden de Trabajo digital: ensayos de la especificación
    filtrados por el laboratorio elegido al crear la solicitud (mismo
    criterio que la Orden de Trabajo impresa), con su resultado ya cargado
    si el muestreo ya fue confirmado."""
    cursor = conn.cursor()
    row = _obtener_solicitud_o_404(cursor, id_solicitud)
    ensayos = _obtener_ensayos(cursor, id_solicitud, row.id_especificacion, row.id_laboratorio)

    resultados_completos = bool(ensayos) and all(
        e.valor_numerico is not None or bool((e.valor_cualitativo or "").strip())
        for e in ensayos
    )

    return EnsayosParaOrdenResponse(
        id_solicitud=row.id_solicitud, nro_solicitud=row.nro_solicitud,
        erp_CODART=row.erp_CODART, erp_DESART=row.erp_DESART, estado=row.estado,
        ensayos=ensayos, resultados_completos=resultados_completos,
        datos_fisicos=DatosFisicosMuestreo(
            aspecto_externo=row.aspecto_externo, cierre=row.cierre,
            aspecto_interno=row.aspecto_interno, precintos=row.precintos,
            identificacion_contenedor=_g(row, "identificacion_contenedor"),
            fecha_vencimiento_real=_a_fecha(_g(row, "fecha_vencimiento_real")),
            fecha_reanalisis_real=_a_fecha(_g(row, "fecha_reanalisis_real")),
            aspecto_mp=_g(row, "aspecto_mp"),
            materias_extranas=row.materias_extranas, olor=row.olor, color=row.color,
            observaciones_muestreo=row.observaciones_muestreo,
            nro_bultos_muestreados=row.nro_bultos_muestreados,
        ),
    )


@router.post("/{id_solicitud}/orden-trabajo-digital", response_model=OrdenTrabajoDigitalResponse)
def confirmar_orden_trabajo(
    id_solicitud: int,
    body: OrdenTrabajoDigitalBody,
    user: dict = Depends(require_rol(*_ROLES_MUESTREADOR_O_SUPERIOR)),
    conn: pyodbc.Connection = Depends(limss_db),
):
    """Etapa 2 completa en una sola confirmación: guarda los datos físicos
    del muestreo (Sección A) + los resultados de los ensayos de la
    especificación filtrados por el laboratorio de la solicitud (Sección B),
    y crea la muestra automáticamente en 'pendiente_envio'. Ya no hay un paso
    manual separado de "ejecutar" ni de "crear muestra desde la solicitud"."""
    cursor = conn.cursor()
    row = _obtener_solicitud_o_404(cursor, id_solicitud)
    if row.estado != "pendiente":
        raise HTTPException(
            status_code=409,
            detail=f"La solicitud está '{row.estado}', no se puede ejecutar el muestreo",
        )
    if row.id_muestreador is None:
        raise HTTPException(status_code=400, detail="La solicitud no tiene un muestreador asignado")

    ensayos = _obtener_ensayos(cursor, id_solicitud, row.id_especificacion, row.id_laboratorio)
    resultados_por_ensayo = {r.id_espec_ensayo: r for r in body.resultados}
    faltantes = [
        e.nombre_ensayo for e in ensayos
        if not _tiene_valor_ot(resultados_por_ensayo.get(e.id_espec_ensayo))
    ]
    if faltantes:
        raise HTTPException(status_code=400, detail=f"Faltan resultados de ensayos: {', '.join(faltantes)}")

    df = body.datos_fisicos
    cursor.execute(
        """
        UPDATE lims_solicitudes_muestreo
        SET aspecto_externo = ?, cierre = ?, aspecto_interno = ?, precintos = ?,
            materias_extranas = ?, olor = ?, color = ?, nro_bultos_muestreados = ?,
            observaciones_muestreo = ?
        WHERE id_solicitud = ?
        """,
        df.aspecto_externo, df.cierre, df.aspecto_interno, df.precintos,
        df.materias_extranas, df.olor, df.color, df.nro_bultos_muestreados,
        df.observaciones_muestreo, id_solicitud,
    )
    try:
        # Columnas agregadas en migrations_solicitudes_muestreo_datos_
        # fisicos_v2.sql -- si todavía no se corrió en este entorno, se
        # omiten sin bloquear el resto de la confirmación (ver _g más arriba).
        cursor.execute(
            """
            UPDATE lims_solicitudes_muestreo
            SET identificacion_contenedor = ?, fecha_vencimiento_real = ?,
                fecha_reanalisis_real = ?, aspecto_mp = ?
            WHERE id_solicitud = ?
            """,
            df.identificacion_contenedor, _a_datetime(df.fecha_vencimiento_real),
            _a_datetime(df.fecha_reanalisis_real), df.aspecto_mp, id_solicitud,
        )
    except pyodbc.Error:
        pass

    hay_oos = False
    for ensayo in ensayos:
        r = resultados_por_ensayo[ensayo.id_espec_ensayo]
        dentro = _calcular_dentro_especificacion(ensayo, r.valor_numerico, r.valor_cualitativo)
        if dentro is False:
            hay_oos = True

        cursor.execute(
            "SELECT 1 FROM lims_orden_trabajo_resultados WHERE id_solicitud = ? AND id_espec_ensayo = ?",
            id_solicitud, ensayo.id_espec_ensayo,
        )
        if cursor.fetchone():
            cursor.execute(
                """
                UPDATE lims_orden_trabajo_resultados
                SET valor_numerico = ?, valor_cualitativo = ?, dentro_especificacion = ?,
                    id_usuario_carga = ?, fecha_carga = GETDATE()
                WHERE id_solicitud = ? AND id_espec_ensayo = ?
                """,
                r.valor_numerico, r.valor_cualitativo, dentro, user["id_usuario"], id_solicitud, ensayo.id_espec_ensayo,
            )
        else:
            cursor.execute(
                """
                INSERT INTO lims_orden_trabajo_resultados
                    (id_solicitud, id_espec_ensayo, valor_numerico, valor_cualitativo, dentro_especificacion, id_usuario_carga)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                id_solicitud, ensayo.id_espec_ensayo, r.valor_numerico, r.valor_cualitativo, dentro, user["id_usuario"],
            )

    cantidades = _obtener_cantidades(cursor, row.id_especificacion)
    codigo_muestra = _generar_codigo_muestra(cursor)

    cursor.execute(
        """
        INSERT INTO lims_muestras
            (codigo_muestra, tipo_referencia, tipo_material, nro_referencia, erp_IdM21, erp_CODART, erp_DESART,
             erp_cantidad_lote, erp_proveedor, cantidad_enviada, unidad_enviada, id_especificacion, estado,
             id_usuario_muestreo, fecha_muestreo)
        VALUES (?, 'ir', 'materia_prima', ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pendiente_envio', ?, GETDATE())
        """,
        codigo_muestra, row.erp_nro_ir, row.erp_IdM21, row.erp_CODART, row.erp_DESART,
        row.cantidad_ingresada, row.proveedor_nombre,
        cantidades["cantidad_muestra"], cantidades["unidad_muestra"],
        row.id_especificacion, row.id_muestreador,
    )
    cursor.execute("SELECT @@IDENTITY AS id")
    id_muestra = int(cursor.fetchone().id)

    cursor.execute(
        "UPDATE lims_solicitudes_muestreo SET id_muestra = ?, estado = 'ejecutada' WHERE id_solicitud = ?",
        id_muestra, id_solicitud,
    )

    audit.registrar(
        conn, entidad="muestra", accion="crear_desde_orden_trabajo",
        id_usuario=user["id_usuario"], id_entidad=id_muestra,
        valor_nuevo={"codigo_muestra": codigo_muestra, "id_solicitud": id_solicitud, "estado": "pendiente_envio"},
    )
    audit.registrar(
        conn, entidad="orden_trabajo_resultados", accion="confirmar",
        id_usuario=user["id_usuario"], id_entidad=id_solicitud,
        valor_nuevo={"hay_oos": hay_oos, "id_muestra": id_muestra},
    )

    return OrdenTrabajoDigitalResponse(
        id_solicitud=id_solicitud, id_muestra=id_muestra, codigo_muestra=codigo_muestra,
    )


@router.put("/{id_solicitud}/anular", response_model=SolicitudMuestreoResponse)
def anular_solicitud(
    id_solicitud: int,
    body: SolicitudMuestreoAnular,
    user: dict = Depends(require_rol("qa", "admin")),
    conn: pyodbc.Connection = Depends(limss_db),
):
    cursor = conn.cursor()
    row = _obtener_solicitud_o_404(cursor, id_solicitud)
    if row.estado != "pendiente":
        raise HTTPException(status_code=400, detail=f"La solicitud ya está '{row.estado}', no se puede anular")

    cursor.execute("UPDATE lims_solicitudes_muestreo SET estado = 'anulada' WHERE id_solicitud = ?", id_solicitud)

    audit.registrar(
        conn, entidad="solicitud_muestreo", accion="anular",
        id_usuario=user["id_usuario"], id_entidad=id_solicitud,
        valor_anterior={"estado": row.estado},
        valor_nuevo={"estado": "anulada"}, motivo=body.motivo,
    )

    return _fila_a_solicitud(_obtener_solicitud_o_404(cursor, id_solicitud))
