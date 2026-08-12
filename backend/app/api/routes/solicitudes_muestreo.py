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
import os
from datetime import date, datetime
from typing import Optional

import pyodbc
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, Response
from pydantic import ValidationError

from app.core.security import get_current_user, require_rol
from app.db.connections import erp_db, limss_db
from app.schemas.solicitudes_muestreo import (
    DatosFisicosMuestreo,
    EnsayoSolicitudMuestreo,
    EnsayosParaOrdenResponse,
    MuestreadorDisponible,
    OrdenTrabajoDigitalBody,
    OrdenTrabajoDigitalResponse,
    SolicitudMuestreoAnular,
    SolicitudMuestreoCreate,
    SolicitudMuestreoDetalle,
    SolicitudMuestreoResponse,
)
from app.services import audit, storage
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
        protocolo_proveedor_nombre_original=_g(row, "protocolo_proveedor_nombre_original"),
        documentacion_proveedor_nombre_original=_g(row, "documentacion_proveedor_nombre_original"),
    )


def _obtener_solicitud_o_404(cursor, id_solicitud: int):
    cursor.execute(_SELECT_SOLICITUD + " WHERE s.id_solicitud = ?", id_solicitud)
    row = cursor.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Solicitud no encontrada")
    return row


def _iniciales_muestreador(cursor, id_muestreador: Optional[int]) -> Optional[str]:
    """Primera letra de nombre + primera letra de apellido (ej. "Lorena
    Fregenal" -> "LF") para mostrar en la etiqueta impresa -- se calcula al
    generar el PDF, no se guarda ningún campo nuevo en la base. El
    muestreador de la etiqueta es el asignado en la solicitud
    (lims_solicitudes_muestreo.id_muestreador): es la misma persona que
    después queda en lims_muestras.id_usuario_muestreo al confirmar el
    muestreo (ver confirmar_orden_trabajo), pero las etiquetas normalmente
    se descargan ANTES de eso -- al recién crear la solicitud, cuando la
    muestra todavía no existe -- así que hay que resolverlo desde acá."""
    if not id_muestreador:
        return None
    cursor.execute("SELECT nombre, apellido FROM lims_usuarios WHERE id_usuario = ?", id_muestreador)
    row = cursor.fetchone()
    if not row or not row.nombre or not row.apellido:
        return None
    return f"{row.nombre[0]}{row.apellido[0]}".upper()


def _obtener_cantidades(cursor, id_especificacion: Optional[int]) -> dict:
    """cantidad/unidad de la muestra de análisis y de la contramuestra.

    lims_especificaciones.cantidad_muestra/unidad_muestra (y sus pares de
    contramuestra) quedaron deprecados a favor de lims_especificacion_
    muestras (una fila por tipo de muestra -- 'analisis'/'contramuestra'/
    'testigo' -- que soporta varias muestras por especificación) y en la
    práctica siempre vienen NULL: esto hacía que la cantidad enviada nunca
    se guardara en lims_muestras.cantidad_enviada al crear la muestra, y por
    lo tanto tampoco apareciera en el remito ni en el Formulario/Orden de
    Trabajo impresos -- no era que esos documentos no mostraran el dato, es
    que nunca llegaba a existir. Se toma la primera fila de cada tipo por
    orden (lo normal es una sola de cada). Si la especificación es vieja y
    no tiene filas en lims_especificacion_muestras, cae al valor legacy de
    lims_especificaciones como último recurso."""
    resultado = {"cantidad_muestra": None, "unidad_muestra": None, "cantidad_contramuestra": None, "unidad_contramuestra": None}
    if id_especificacion is None:
        return resultado

    cursor.execute("SELECT OBJECT_ID('lims_especificacion_muestras') AS oid")
    if cursor.fetchone().oid is not None:
        cursor.execute(
            "SELECT TOP 1 cantidad, unidad FROM lims_especificacion_muestras "
            "WHERE id_especificacion = ? AND tipo_muestra = 'analisis' ORDER BY orden",
            id_especificacion,
        )
        fila = cursor.fetchone()
        if fila:
            resultado["cantidad_muestra"] = float(fila.cantidad)
            resultado["unidad_muestra"] = fila.unidad

        cursor.execute(
            "SELECT TOP 1 cantidad, unidad FROM lims_especificacion_muestras "
            "WHERE id_especificacion = ? AND tipo_muestra = 'contramuestra' ORDER BY orden",
            id_especificacion,
        )
        fila = cursor.fetchone()
        if fila:
            resultado["cantidad_contramuestra"] = float(fila.cantidad)
            resultado["unidad_contramuestra"] = fila.unidad

    if resultado["cantidad_muestra"] is None and resultado["cantidad_contramuestra"] is None:
        cursor.execute(
            "SELECT cantidad_muestra, unidad_muestra, cantidad_contramuestra, unidad_contramuestra "
            "FROM lims_especificaciones WHERE id_especificacion = ?",
            id_especificacion,
        )
        espec = cursor.fetchone()
        if espec:
            resultado["cantidad_muestra"] = float(espec.cantidad_muestra) if espec.cantidad_muestra is not None else None
            resultado["unidad_muestra"] = espec.unidad_muestra
            resultado["cantidad_contramuestra"] = float(espec.cantidad_contramuestra) if espec.cantidad_contramuestra is not None else None
            resultado["unidad_contramuestra"] = espec.unidad_contramuestra

    return resultado


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


def _crear_muestra_desde_solicitud(cursor, row, datos_muestreo_pendientes: bool) -> tuple[int, str]:
    """Inserta lims_muestras a partir de los datos ya conocidos de la
    solicitud (y del ERP, ya resueltos al crearla) -- compartido por
    confirmar_orden_trabajo (flujo normal: el muestreador ejecuta el
    muestreo primero, datos_muestreo_pendientes=False) y
    generar_envio_anticipado (el envío se genera ANTES del muestreo físico:
    datos_muestreo_pendientes=True y fecha_muestreo queda como placeholder
    -- confirmar_orden_trabajo la reemplaza por la fecha real más
    adelante en vez de crear una segunda muestra, ver ese endpoint)."""
    cantidades = _obtener_cantidades(cursor, row.id_especificacion)
    codigo_muestra = _generar_codigo_muestra(cursor)
    cursor.execute(
        """
        INSERT INTO lims_muestras
            (codigo_muestra, tipo_referencia, tipo_material, nro_referencia, erp_IdM21, erp_CODART, erp_DESART,
             erp_cantidad_lote, erp_proveedor, cantidad_enviada, unidad_enviada, id_especificacion, estado,
             id_usuario_muestreo, fecha_muestreo, datos_muestreo_pendientes)
        VALUES (?, 'ir', 'materia_prima', ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pendiente_envio', ?, GETDATE(), ?)
        """,
        codigo_muestra, row.erp_nro_ir, row.erp_IdM21, row.erp_CODART, row.erp_DESART,
        row.cantidad_ingresada, row.proveedor_nombre,
        cantidades["cantidad_muestra"], cantidades["unidad_muestra"],
        row.id_especificacion, row.id_muestreador, 1 if datos_muestreo_pendientes else 0,
    )
    cursor.execute("SELECT @@IDENTITY AS id")
    id_muestra = int(cursor.fetchone().id)
    return id_muestra, codigo_muestra


@router.post("", response_model=SolicitudMuestreoResponse, status_code=201)
def crear_solicitud(
    datos: str = Form(..., description="JSON de SolicitudMuestreoCreate"),
    protocolo_proveedor: UploadFile = File(
        ...,
        description="Protocolo que entrega el proveedor junto con el lote (foto o PDF) -- obligatorio",
    ),
    documentacion_proveedor: Optional[UploadFile] = File(
        None,
        description="Documentación del proveedor (remito y/o factura en un solo archivo, foto o PDF) "
                     "-- opcional, se puede adjuntar acá o después (ver POST .../documentacion-proveedor)",
    ),
    user: dict = Depends(require_rol("qa", "admin")),
    erp: pyodbc.Connection = Depends(erp_db),
    conn: pyodbc.Connection = Depends(limss_db),
):
    try:
        body = SolicitudMuestreoCreate.model_validate_json(datos)
    except ValidationError as e:
        raise HTTPException(status_code=422, detail=f"Datos de la solicitud inválidos: {e}")
    if not protocolo_proveedor.filename:
        raise HTTPException(
            status_code=422,
            detail="El protocolo del proveedor (foto o PDF) es obligatorio para generar la solicitud",
        )

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

    nro_ir_normalizado = formatear_nro_ir(linea.NUMCOMO, linea.FECCOR)
    nro_solicitud = _generar_nro_solicitud(cursor)

    fecha_ingreso = normalizar_fecha_sentinel(linea.FECCOM)
    # El frontend precarga este campo con el VENCOM del ERP y deja que el
    # usuario lo corrija -- si no mandó nada (ej. un cliente API viejo) se
    # cae al valor del ERP como antes.
    fecha_vencimiento = body.fecha_vencimiento or normalizar_fecha_sentinel(linea.VENCOM)
    cantidad_ingresada = float(linea.cantidad_total) if linea.cantidad_total is not None else None

    # Validado y guardado recién acá (todas las reglas de negocio ya pasaron) --
    # si el tipo de archivo es inválido, falla antes de escribir nada en la BD.
    ruta_protocolo_proveedor = storage.guardar_protocolo_proveedor(protocolo_proveedor, nro_solicitud)

    # A diferencia del protocolo, este adjunto es opcional: si no se mandó
    # nada (o se mandó un campo de archivo vacío, mismo criterio que arriba
    # con protocolo_proveedor.filename), la solicitud se crea igual, sin
    # error -- se puede adjuntar después con POST .../documentacion-proveedor.
    ruta_documentacion_proveedor = None
    nombre_documentacion_proveedor = None
    if documentacion_proveedor is not None and documentacion_proveedor.filename:
        ruta_documentacion_proveedor = storage.guardar_documentacion_proveedor(documentacion_proveedor, nro_solicitud)
        nombre_documentacion_proveedor = documentacion_proveedor.filename

    cursor.execute(
        """
        INSERT INTO lims_solicitudes_muestreo
            (nro_solicitud, erp_nro_ir, erp_IdM21, erp_CODART, erp_DESART, id_especificacion,
             id_laboratorio, id_muestreador, observaciones, estado, id_usuario_qa,
             proveedor_codigo, proveedor_nombre, lote_proveedor, fecha_ingreso, fecha_vencimiento,
             fecha_reanalisis, pais_origen, cantidad_ingresada, unidad_cantidad, nro_bultos,
             metodologia_analisis, fabricante, protocolo_proveedor_path, protocolo_proveedor_nombre_original,
             documentacion_proveedor_path, documentacion_proveedor_nombre_original)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'pendiente', ?,
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        nro_solicitud, nro_ir_normalizado, linea.IdM21, linea.CODART, linea.DESART, espec.id_especificacion,
        body.id_laboratorio, body.id_muestreador, body.observaciones, user["id_usuario"],
        body.proveedor_codigo, body.proveedor_nombre, body.lote_proveedor, _a_datetime(fecha_ingreso), _a_datetime(fecha_vencimiento),
        _a_datetime(body.fecha_reanalisis), body.pais_origen, cantidad_ingresada, linea.unidad, body.nro_bultos,
        body.metodologia_analisis, body.fabricante, ruta_protocolo_proveedor, protocolo_proveedor.filename,
        ruta_documentacion_proveedor, nombre_documentacion_proveedor,
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


def _generar_pdf_etiquetas_de_solicitud(cursor, row) -> bytes:
    """Arma el PDF de etiquetas para una solicitud ya cargada (fila de
    lims_solicitudes_muestreo) -- función compartida para que "Descargar
    etiquetas" (Solicitudes) y la reimpresión desde Consulta de Muestras
    (ver descargar_etiquetas_de_muestra en muestras.py) generen exactamente
    el mismo PDF en vez de mantener dos caminos que puedan divergir."""
    iniciales = _iniciales_muestreador(cursor, row.id_muestreador)
    muestras_confirmadas = _obtener_muestras_confirmadas(cursor, row.id_solicitud)
    if muestras_confirmadas:
        return generar_pdf_etiquetas_v2(row, muestras_confirmadas, iniciales)
    cantidades = _obtener_cantidades(cursor, row.id_especificacion)
    return generar_pdf_etiquetas(row, cantidades, iniciales)


@router.get("/{id_solicitud}/etiquetas")
def descargar_etiquetas(
    id_solicitud: int,
    user: dict = Depends(get_current_user),
    conn: pyodbc.Connection = Depends(limss_db),
):
    cursor = conn.cursor()
    row = _obtener_solicitud_o_404(cursor, id_solicitud)
    pdf_bytes = _generar_pdf_etiquetas_de_solicitud(cursor, row)

    return Response(
        content=pdf_bytes, media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{row.nro_solicitud}_etiquetas.pdf"'},
    )


_MEDIA_TYPES_PROTOCOLO_PROVEEDOR = {
    ".pdf": "application/pdf", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png",
}


@router.get("/{id_solicitud}/protocolo-proveedor")
def descargar_protocolo_proveedor(
    id_solicitud: int,
    user: dict = Depends(get_current_user),
    conn: pyodbc.Connection = Depends(limss_db),
):
    """Protocolo que entregó el proveedor junto con el lote (foto o PDF),
    adjuntado por QA al crear la solicitud -- distinto del protocolo del
    laboratorio de análisis (ver /api/envios/{id_envio}/protocolo)."""
    cursor = conn.cursor()
    cursor.execute(
        "SELECT protocolo_proveedor_path, protocolo_proveedor_nombre_original "
        "FROM lims_solicitudes_muestreo WHERE id_solicitud = ?",
        id_solicitud,
    )
    row = cursor.fetchone()
    if not row or not row.protocolo_proveedor_path:
        raise HTTPException(status_code=404, detail="Esta solicitud no tiene protocolo del proveedor cargado")

    ruta = storage.ruta_absoluta(row.protocolo_proveedor_path)
    if not os.path.exists(ruta):
        raise HTTPException(status_code=404, detail="El archivo no se encuentra en el servidor")

    extension = os.path.splitext(ruta)[1].lower()
    media_type = _MEDIA_TYPES_PROTOCOLO_PROVEEDOR.get(extension, "application/octet-stream")
    return FileResponse(
        ruta, media_type=media_type,
        filename=row.protocolo_proveedor_nombre_original or os.path.basename(ruta),
    )


@router.post("/{id_solicitud}/documentacion-proveedor", response_model=SolicitudMuestreoResponse)
def subir_documentacion_proveedor(
    id_solicitud: int,
    documentacion_proveedor: UploadFile = File(
        ..., description="Documentación del proveedor (remito y/o factura en un solo archivo, foto o PDF)",
    ),
    user: dict = Depends(require_rol("qa", "admin")),
    conn: pyodbc.Connection = Depends(limss_db),
):
    """Adjunta (o reemplaza, si ya había una) la documentación del proveedor
    de una solicitud ya creada -- a diferencia del protocolo, este adjunto
    no se exige en el momento de crear la solicitud, así que hace falta este
    endpoint aparte para poder cargarlo después."""
    if not documentacion_proveedor.filename:
        raise HTTPException(status_code=422, detail="No se recibió ningún archivo")

    cursor = conn.cursor()
    row = _obtener_solicitud_o_404(cursor, id_solicitud)

    ruta = storage.guardar_documentacion_proveedor(documentacion_proveedor, row.nro_solicitud)
    cursor.execute(
        "UPDATE lims_solicitudes_muestreo SET documentacion_proveedor_path = ?, documentacion_proveedor_nombre_original = ? "
        "WHERE id_solicitud = ?",
        ruta, documentacion_proveedor.filename, id_solicitud,
    )

    audit.registrar(
        conn, entidad="solicitud_muestreo", accion="adjuntar_documentacion_proveedor",
        id_usuario=user["id_usuario"], id_entidad=id_solicitud,
        valor_nuevo={"documentacion_proveedor_nombre_original": documentacion_proveedor.filename},
    )

    return _fila_a_solicitud(_obtener_solicitud_o_404(cursor, id_solicitud))


@router.get("/{id_solicitud}/documentacion-proveedor")
def descargar_documentacion_proveedor(
    id_solicitud: int,
    user: dict = Depends(get_current_user),
    conn: pyodbc.Connection = Depends(limss_db),
):
    """Documentación del proveedor (remito y/o factura) adjuntada por QA --
    opcional, distinta del protocolo (ver descargar_protocolo_proveedor)."""
    cursor = conn.cursor()
    cursor.execute(
        "SELECT documentacion_proveedor_path, documentacion_proveedor_nombre_original "
        "FROM lims_solicitudes_muestreo WHERE id_solicitud = ?",
        id_solicitud,
    )
    row = cursor.fetchone()
    if not row or not row.documentacion_proveedor_path:
        raise HTTPException(status_code=404, detail="Esta solicitud no tiene documentación del proveedor cargada")

    ruta = storage.ruta_absoluta(row.documentacion_proveedor_path)
    if not os.path.exists(ruta):
        raise HTTPException(status_code=404, detail="El archivo no se encuentra en el servidor")

    extension = os.path.splitext(ruta)[1].lower()
    media_type = _MEDIA_TYPES_PROTOCOLO_PROVEEDOR.get(extension, "application/octet-stream")
    return FileResponse(
        ruta, media_type=media_type,
        filename=row.documentacion_proveedor_nombre_original or os.path.basename(ruta),
    )


@router.get("/{id_solicitud}/ensayos-para-orden", response_model=EnsayosParaOrdenResponse)
def ensayos_para_orden(
    id_solicitud: int,
    user: dict = Depends(get_current_user),
    conn: pyodbc.Connection = Depends(limss_db),
):
    """Datos físicos del muestreo ya cargados (si el muestreo ya fue
    confirmado) para precargar el formulario de Orden de Trabajo digital que
    completa el muestreador -- solo datos físicos observables, nunca
    resultados de ensayos (eso lo carga QC/QA después, por envío)."""
    cursor = conn.cursor()
    row = _obtener_solicitud_o_404(cursor, id_solicitud)

    return EnsayosParaOrdenResponse(
        id_solicitud=row.id_solicitud, nro_solicitud=row.nro_solicitud,
        erp_CODART=row.erp_CODART, erp_DESART=row.erp_DESART, estado=row.estado,
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


@router.post("/{id_solicitud}/generar-envio-anticipado", response_model=OrdenTrabajoDigitalResponse, status_code=201)
def generar_envio_anticipado(
    id_solicitud: int,
    user: dict = Depends(require_rol("analista_qc", "qa", "admin")),
    conn: pyodbc.Connection = Depends(limss_db),
):
    """Genera el envío ANTES de que el muestreador ejecute el muestreo
    físico: crea la muestra ahora mismo con los datos ya conocidos de la
    solicitud/ERP (datos_muestreo_pendientes=True, fecha_muestreo como
    placeholder) para que QC/QA pueda seguir con el flujo normal de Envío de
    Muestras (POST /api/muestras/{id_muestra}/envios, sin cambios) en vez de
    esperar a que se complete el registro físico del muestreo. Cuando el
    muestreador después confirme la Orden de Trabajo digital de esta misma
    solicitud, completa los datos reales sobre esta muestra en vez de crear
    una segunda (ver confirmar_orden_trabajo)."""
    cursor = conn.cursor()
    row = _obtener_solicitud_o_404(cursor, id_solicitud)
    if row.id_muestra is not None:
        raise HTTPException(status_code=409, detail="Esta solicitud ya tiene una muestra asociada")
    if row.estado != "pendiente":
        raise HTTPException(
            status_code=409,
            detail=f"La solicitud está '{row.estado}', no se puede generar un envío anticipado",
        )
    if row.id_muestreador is None:
        raise HTTPException(status_code=400, detail="La solicitud no tiene un muestreador asignado")

    id_muestra, codigo_muestra = _crear_muestra_desde_solicitud(cursor, row, datos_muestreo_pendientes=True)
    cursor.execute(
        "UPDATE lims_solicitudes_muestreo SET id_muestra = ? WHERE id_solicitud = ?",
        id_muestra, id_solicitud,
    )

    audit.registrar(
        conn, entidad="muestra", accion="crear_desde_envio_anticipado",
        id_usuario=user["id_usuario"], id_entidad=id_muestra,
        valor_nuevo={"codigo_muestra": codigo_muestra, "id_solicitud": id_solicitud, "datos_muestreo_pendientes": True},
    )

    return OrdenTrabajoDigitalResponse(
        id_solicitud=id_solicitud, id_muestra=id_muestra, codigo_muestra=codigo_muestra,
    )


@router.post("/{id_solicitud}/orden-trabajo-digital", response_model=OrdenTrabajoDigitalResponse)
def confirmar_orden_trabajo(
    id_solicitud: int,
    body: OrdenTrabajoDigitalBody,
    user: dict = Depends(require_rol(*_ROLES_MUESTREADOR_O_SUPERIOR)),
    conn: pyodbc.Connection = Depends(limss_db),
):
    """Etapa 2 completa en una sola confirmación: guarda los datos físicos
    del muestreo (Sección A). El muestreador NUNCA carga resultados de
    ensayos -- eso lo hace QC/QA más adelante, por envío, en Carga de
    Resultados (ver app/api/routes/resultados.py).

    Si la solicitud todavía no tiene muestra asociada (flujo normal: se
    ejecuta el muestreo antes de generar el envío), la crea acá, igual que
    siempre. Si ya tiene una -- porque QC/QA generó el envío por adelantado
    con generar_envio_anticipado -- no crea una segunda: completa
    fecha_muestreo con la fecha real de esta confirmación y baja
    datos_muestreo_pendientes a 0 sobre la que ya existe."""
    cursor = conn.cursor()
    row = _obtener_solicitud_o_404(cursor, id_solicitud)
    if row.estado != "pendiente":
        raise HTTPException(
            status_code=409,
            detail=f"La solicitud está '{row.estado}', no se puede ejecutar el muestreo",
        )
    if row.id_muestreador is None:
        raise HTTPException(status_code=400, detail="La solicitud no tiene un muestreador asignado")

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

    if row.id_muestra is not None:
        cursor.execute(
            "UPDATE lims_muestras SET fecha_muestreo = GETDATE(), datos_muestreo_pendientes = 0 WHERE id_muestra = ?",
            row.id_muestra,
        )
        cursor.execute("SELECT codigo_muestra FROM lims_muestras WHERE id_muestra = ?", row.id_muestra)
        id_muestra = row.id_muestra
        codigo_muestra = cursor.fetchone().codigo_muestra
        accion_auditoria = "completar_datos_muestreo"
    else:
        id_muestra, codigo_muestra = _crear_muestra_desde_solicitud(cursor, row, datos_muestreo_pendientes=False)
        cursor.execute(
            "UPDATE lims_solicitudes_muestreo SET id_muestra = ? WHERE id_solicitud = ?",
            id_muestra, id_solicitud,
        )
        accion_auditoria = "crear_desde_orden_trabajo"

    cursor.execute(
        "UPDATE lims_solicitudes_muestreo SET estado = 'ejecutada' WHERE id_solicitud = ?",
        id_solicitud,
    )

    audit.registrar(
        conn, entidad="muestra", accion=accion_auditoria,
        id_usuario=user["id_usuario"], id_entidad=id_muestra,
        valor_nuevo={"codigo_muestra": codigo_muestra, "id_solicitud": id_solicitud},
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


# Reexport para app/api/routes/integraciones.py: la creación de muestra desde
# la integración con el eBR usa el mismo generador de código SAMP-AAAA-NNNN
# que el flujo normal de confirmación de muestreo, en vez de duplicarlo.
generar_codigo_muestra = _generar_codigo_muestra

# Reexport para app/api/routes/muestras.py: la reimpresión de etiquetas desde
# Consulta de Muestras usa el mismo armado de PDF que "Descargar etiquetas"
# en Solicitudes, en vez de un template paralelo.
obtener_solicitud_o_404 = _obtener_solicitud_o_404
generar_pdf_etiquetas_de_solicitud = _generar_pdf_etiquetas_de_solicitud
