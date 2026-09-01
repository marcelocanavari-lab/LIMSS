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
import logging
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
    BultoGrupoResponse,
    DatosFisicosMuestreo,
    EnsayoSolicitudMuestreo,
    EnsayosParaOrdenResponse,
    MuestreadorDisponible,
    OrdenTrabajoDigitalBody,
    OrdenTrabajoDigitalResponse,
    SolicitudMuestreoAnular,
    SolicitudMuestreoCompletar,
    SolicitudMuestreoCorregirRecepcion,
    SolicitudMuestreoCreate,
    SolicitudMuestreoDetalle,
    SolicitudMuestreoResponse,
    UsuarioDisponible,
)
from app.schemas.muestras import CantidadEtiquetasResponse, ImprimirDirectoBody, ImprimirDirectoResponse
from app.services import audit, storage
from app.services.bultos import expandir_bultos, filtrar_rango_bultos, guardar_grupos_bultos, obtener_grupos_bultos
from app.services.especificaciones import guardar_checklist_muestreo, obtener_checklist_muestreo, tiene_ensayos_analisis
from app.services.erp_ir import (
    buscar_lineas_ir,
    formatear_nro_ir,
    lineas_comprobante_por_id,
    normalizar_fecha_sentinel,
    solicitud_activa_existente,
)
from app.services.erp_materiales import asignar_numero_analisis_si_corresponde, tiene_numero_analisis
from app.services.formato import etiqueta_referencia, formatear_cantidad, normalizar_unidad, titulo_etiqueta_por_tipo
from app.services.impresion_sato import (
    armar_pares_etiquetas_muestra,
    generar_sbpl_etiqueta_estado,
    generar_sbpl_etiqueta_par,
    imprimir_sbpl,
)
from app.services.pdf_solicitud_muestreo import (
    generar_pdf_etiquetas,
    generar_pdf_etiquetas_v2,
    generar_pdf_formulario,
    generar_pdf_orden_trabajo,
    generar_pdf_planilla_muestreo,
)

logger = logging.getLogger("solicitudes_muestreo")

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
    """El driver ODBC no devuelve un tipo consistente para columnas DATE en
    este entorno (a veces date/datetime, a veces str) -- se normaliza
    siempre a date antes de operar (mismo problema y mismo fix que
    testigos_remitos.py/envios.py)."""
    if valor is None:
        return None
    if isinstance(valor, str):
        return date.fromisoformat(valor[:10])
    return valor.date() if hasattr(valor, "date") else valor


def _g(row, atributo: str):
    """Lee un atributo que puede no existir todavía en el esquema real (ver
    migrations_solicitudes_muestreo_datos_fisicos_v2.sql, pendiente de
    ejecutar en algunos entornos) -- getattr con default None en vez de
    romper toda la respuesta por columnas nuevas que todavía no están."""
    return getattr(row, atributo, None)


def _tiene_columna_sin_vencimiento_confirmado(cursor) -> bool:
    """sin_vencimiento_confirmado (ver migrations_solicitud_vencimiento_
    confirmado.sql) puede no haberse corrido todavía en este entorno --
    mientras tanto, no se exige ni se persiste (mismo criterio de
    tolerancia que _tiene_columnas_muestra_adhoc)."""
    cursor.execute("SELECT COL_LENGTH('lims_solicitudes_muestreo', 'sin_vencimiento_confirmado') AS c")
    return cursor.fetchone().c is not None


_SELECT_SOLICITUD = """
    SELECT s.*, lab.nombre AS laboratorio_nombre, u.nombre + ' ' + u.apellido AS usuario_qa,
           um.nombre + ' ' + um.apellido AS muestreador_nombre
    FROM lims_solicitudes_muestreo s
    LEFT JOIN lims_laboratorios lab ON lab.id_laboratorio = s.id_laboratorio
    INNER JOIN lims_usuarios u ON u.id_usuario = s.id_usuario_qa
    LEFT JOIN lims_usuarios um ON um.id_usuario = s.id_muestreador
"""


def _fila_a_solicitud(row, cursor=None) -> SolicitudMuestreoResponse:
    grupos_bultos = (
        [
            BultoGrupoResponse(
                id_bulto_grupo=g.id_bulto_grupo, cantidad_bultos=g.cantidad_bultos,
                cantidad_unidades=float(g.cantidad_unidades), unidad_medida=g.unidad_medida,
            )
            for g in obtener_grupos_bultos(cursor, row.id_solicitud)
        ]
        if cursor is not None else []
    )
    return SolicitudMuestreoResponse(
        grupos_bultos=grupos_bultos,
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
        sin_vencimiento_ingreso_confirmado=bool(_g(row, "sin_vencimiento_ingreso_confirmado")),
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
        origen=_g(row, "origen") or "manual",
        erp_n01id=_g(row, "erp_n01id"),
        fecha_factura_proveedor=_a_fecha(_g(row, "fecha_factura_proveedor")),
        numero_factura_proveedor=_g(row, "numero_factura_proveedor"),
        id_usuario_recibio=_g(row, "id_usuario_recibio"),
        id_usuario_rotulo=_g(row, "id_usuario_rotulo"),
    )


def _obtener_solicitud_o_404(cursor, id_solicitud: int):
    cursor.execute(_SELECT_SOLICITUD + " WHERE s.id_solicitud = ?", id_solicitud)
    row = cursor.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Solicitud no encontrada")
    return row


def _verificar_completa_para_ejecutar(cursor, row) -> None:
    """Antes de generar el envío o confirmar el muestreo, la solicitud tiene
    que tener muestreador asignado -- determina quién muestrea. El
    laboratorio ya NO se exige acá (rediseño de la pantalla de Solicitud de
    Muestreo: dejó de elegirse al crear/completar la solicitud, se resuelve
    más adelante, por ensayo, al generar el envío -- ver EnvioFormPage.jsx,
    que ya elige laboratorio de forma independiente). El lote y el
    protocolo del proveedor son papeleo que QA puede completar en un
    momento distinto, incluso después de ejecutado el muestreo (ver PUT
    .../completar-datos y POST .../protocolo-proveedor) -- no tiene sentido
    hacer esperar al muestreador por eso. El agente puede dejar muestreador
    en blanco cuando no lo puede resolver solo con el ERP (ver
    app/services/agente_muestreo.py)."""
    faltantes = []
    if row.id_muestreador is None:
        faltantes.append("muestreador")
    if faltantes:
        raise HTTPException(
            status_code=400,
            detail=(
                "A la solicitud le falta completar: " + ", ".join(faltantes) +
                " -- ver PUT .../completar-datos"
            ),
        )


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


def _obtener_ensayos(cursor, id_solicitud: int, id_especificacion: Optional[int]) -> list[EnsayoSolicitudMuestreo]:
    """Ensayos de análisis de la especificación, con su resultado ya cargado
    en la Orden de Trabajo digital si lo hay -- LEFT JOIN por id_solicitud,
    así que antes de confirmar el muestreo todos los valores vienen en None
    (mismo shape para el formulario en blanco, la Orden de Trabajo impresa
    ya completada, y GET .../ensayos-para-orden).

    Ya NO se filtra por id_laboratorio (rediseño de esta pantalla: el
    laboratorio no se elige más al crear/completar la solicitud, se resuelve
    después por ensayo al generar el envío) -- trae los ensayos de TODOS los
    laboratorios de la especificación, cada uno con su propio
    laboratorio_nombre (ver EnsayoSolicitudMuestreo) para poder
    identificarlos en la Orden de Trabajo impresa."""
    if id_especificacion is None:
        return []
    cursor.execute(
        """
        SELECT ee.id_espec_ensayo, ee.orden, m.nombre_ensayo, ee.metodologia, ee.tipo_dato, ee.limite_inferior,
               ee.limite_superior, ee.unidad_medida, ee.valor_requerido, ee.especificacion_texto, ee.obligatorio,
               lab.nombre AS laboratorio_nombre,
               r.valor_numerico, r.valor_cualitativo, r.dentro_especificacion
        FROM lims_especificacion_ensayos ee
        INNER JOIN lims_ensayos_maestro m ON m.id_ensayo_maestro = ee.id_ensayo_maestro
        INNER JOIN lims_categorias_ensayo cat ON cat.id_categoria = ee.id_categoria
        LEFT JOIN lims_laboratorios lab ON lab.id_laboratorio = ee.id_laboratorio
        LEFT JOIN lims_orden_trabajo_resultados r ON r.id_espec_ensayo = ee.id_espec_ensayo AND r.id_solicitud = ?
        WHERE ee.id_especificacion = ? AND cat.momento = 'analisis' AND ee.activo = 1
        ORDER BY ee.orden
        """,
        id_solicitud, id_especificacion,
    )
    return [
        EnsayoSolicitudMuestreo(
            id_espec_ensayo=e.id_espec_ensayo, orden=e.orden,
            nombre_ensayo=e.nombre_ensayo, metodologia=e.metodologia, tipo_dato=e.tipo_dato,
            limite_inferior=float(e.limite_inferior) if e.limite_inferior is not None else None,
            limite_superior=float(e.limite_superior) if e.limite_superior is not None else None,
            unidad_medida=e.unidad_medida, valor_requerido=e.valor_requerido,
            especificacion_texto=e.especificacion_texto, obligatorio=bool(e.obligatorio),
            laboratorio_nombre=e.laboratorio_nombre,
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
    return [_fila_a_solicitud(r, cursor) for r in cursor.fetchall()]


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


@router.get("/usuarios-activos", response_model=list[UsuarioDisponible])
def listar_usuarios_activos(
    user: dict = Depends(require_rol(*_ROLES_MUESTREADOR_O_SUPERIOR)),
    conn: pyodbc.Connection = Depends(limss_db),
):
    """Todos los usuarios activos (cualquier rol), para los selectores
    "Recibió"/"Rotuló" de Ejecutar Muestreo (ver OrdenTrabajoDigitalBody) --
    a diferencia de /muestreadores, acá no se filtra por rol porque quien
    recibe o rotula un ingreso no tiene por qué ser un muestreador. Ruta
    literal -- debe declararse antes de "/{id_solicitud}"."""
    cursor = conn.cursor()
    cursor.execute("SELECT id_usuario, nombre, apellido FROM lims_usuarios WHERE activo = 1 ORDER BY apellido, nombre")
    return [
        UsuarioDisponible(id_usuario=r.id_usuario, nombre_completo=f"{r.nombre} {r.apellido}")
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
    return [_fila_a_solicitud(r, cursor) for r in cursor.fetchall()]


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


def _tipo_material_de_especificacion(cursor, id_especificacion: Optional[int]) -> str:
    """El tipo_material de la muestra generada tiene que coincidir con el de
    la especificación que la originó -- antes quedaba hardcodeado a
    'materia_prima' porque, históricamente, era el único tipo que pasaba por
    Solicitudes de Muestreo; con Material de Empaque deja de ser cierto. Si
    la solicitud no tiene especificación vinculada (no debería pasar, la
    creación de la solicitud la exige), se conserva el valor histórico."""
    if id_especificacion is not None:
        cursor.execute("SELECT tipo_material FROM lims_especificaciones WHERE id_especificacion = ?", id_especificacion)
        espec = cursor.fetchone()
        if espec and espec.tipo_material:
            return espec.tipo_material
    return "materia_prima"


def _crear_muestra_desde_solicitud(conn: pyodbc.Connection, cursor, row, datos_muestreo_pendientes: bool) -> tuple[int, str]:
    """Inserta lims_muestras a partir de los datos ya conocidos de la
    solicitud (y del ERP, ya resueltos al crearla) -- compartido por
    confirmar_orden_trabajo (flujo normal: el muestreador ejecuta el
    muestreo primero, datos_muestreo_pendientes=False) y
    generar_envio_anticipado (el envío se genera ANTES del muestreo físico:
    datos_muestreo_pendientes=True y fecha_muestreo queda como placeholder
    -- confirmar_orden_trabajo la reemplaza por la fecha real más
    adelante en vez de crear una segunda muestra, ver ese endpoint).

    Si la especificación no tiene ningún ensayo de etapa 'analisis' (solo
    checklist de muestreo), no hay nada que enviar a un laboratorio -- la
    muestra arranca directo en 'en_análisis' en vez de 'pendiente_envio',
    así nunca aparece en la bandeja de Envío ni pide protocolo; queda apta
    para Dictamen apenas se completa el checklist (ver
    WHERE_MUESTRA_PENDIENTE_DICTAMEN en dictamenes.py)."""
    cantidades = _obtener_cantidades(cursor, row.id_especificacion)
    codigo_muestra = _generar_codigo_muestra(cursor)
    tipo_material = _tipo_material_de_especificacion(cursor, row.id_especificacion)
    estado_inicial = "en_análisis" if not tiene_ensayos_analisis(cursor, row.id_especificacion) else "pendiente_envio"

    # numero_analisis (Libro de Ingresos): correlativo exclusivo de Materia
    # Prima/Material de Empaque, determinado por erp_codsar (ver
    # asignar_numero_analisis_si_corresponde) -- Solicitudes de Muestreo es
    # siempre por IR (materia prima o material de empaque, nunca lote), así
    # que acá puede tocar en cualquiera de los dos casos.
    if tiene_numero_analisis(cursor):
        numero_analisis = asignar_numero_analisis_si_corresponde(conn, row.id_especificacion)
        cursor.execute(
            """
            INSERT INTO lims_muestras
                (codigo_muestra, tipo_referencia, tipo_material, nro_referencia, erp_n01id, erp_IdM21, erp_CODART, erp_DESART,
                 erp_cantidad_lote, erp_proveedor, cantidad_enviada, unidad_enviada, id_especificacion, estado,
                 id_usuario_muestreo, fecha_muestreo, datos_muestreo_pendientes, numero_analisis)
            VALUES (?, 'ir', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, GETDATE(), ?, ?)
            """,
            codigo_muestra, tipo_material, row.erp_nro_ir, getattr(row, "erp_n01id", None), row.erp_IdM21, row.erp_CODART, row.erp_DESART,
            row.cantidad_ingresada, row.proveedor_nombre,
            cantidades["cantidad_muestra"], cantidades["unidad_muestra"],
            row.id_especificacion, estado_inicial, row.id_muestreador, 1 if datos_muestreo_pendientes else 0,
            numero_analisis,
        )
    else:
        cursor.execute(
            """
            INSERT INTO lims_muestras
                (codigo_muestra, tipo_referencia, tipo_material, nro_referencia, erp_n01id, erp_IdM21, erp_CODART, erp_DESART,
                 erp_cantidad_lote, erp_proveedor, cantidad_enviada, unidad_enviada, id_especificacion, estado,
                 id_usuario_muestreo, fecha_muestreo, datos_muestreo_pendientes)
            VALUES (?, 'ir', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, GETDATE(), ?)
            """,
            codigo_muestra, tipo_material, row.erp_nro_ir, getattr(row, "erp_n01id", None), row.erp_IdM21, row.erp_CODART, row.erp_DESART,
            row.cantidad_ingresada, row.proveedor_nombre,
            cantidades["cantidad_muestra"], cantidades["unidad_muestra"],
            row.id_especificacion, estado_inicial, row.id_muestreador, 1 if datos_muestreo_pendientes else 0,
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

    # Si el frontend ya resolvió el N01Id (búsqueda previa, ver
    # GET /api/muestras/buscar-material) se usa directo -- no vuelve a pasar
    # por la resolución ambigua de NUMCOMO+año, así que una colisión que
    # aparezca después para este mismo "NNN/AA" no puede traer el
    # comprobante equivocado. Sin N01Id (clientes viejos, o el caso normal
    # sin colisión donde no hizo falta elegir) se resuelve por texto como
    # siempre -- buscar_lineas_ir ya tiene el desempate mejorado como red de
    # seguridad (preferir VENCOM real), ver erp_ir.py.
    if body.erp_n01id is not None:
        lineas = lineas_comprobante_por_id(erp, body.erp_n01id)
        if not lineas:
            raise HTTPException(
                status_code=404,
                detail=f"El comprobante elegido (N01Id={body.erp_n01id}) ya no se encuentra en el ERP",
            )
    else:
        lineas = buscar_lineas_ir(erp, body.erp_nro_ir)
        if not lineas:
            raise HTTPException(status_code=404, detail=f"No se encontró el IR '{body.erp_nro_ir}' en el ERP")
    linea = lineas[0]

    # Material de Empaque sin codificar (GIT59SAR.CODSAR '0006') es el único
    # caso donde el lote del proveedor no es exigible -- para cualquier otro
    # subartículo (incluido '0005', Material de Empaque codificado) se
    # mantiene el comportamiento de siempre. linea.CODSAR ya viene resuelto
    # por buscar_lineas_ir, no hace falta una consulta nueva al ERP.
    if linea.CODSAR != "0006" and not (body.lote_proveedor and body.lote_proveedor.strip()):
        raise HTTPException(status_code=400, detail="El lote del proveedor es obligatorio para este tipo de material")

    cursor = conn.cursor()

    # Duplicados por IR -- a diferencia del agente (bloqueo duro, nunca
    # genera una segunda solicitud para un IR con una activa, ver
    # solicitud_activa_existente en app/services/erp_ir.py), la creación
    # MANUAL solo avisa: puede ser legítimo necesitar una segunda solicitud
    # para el mismo IR (ej. análisis adicionales pedidos después). Se
    # calcula acá el nro_ir_normalizado (antes se calculaba más abajo,
    # después de subir archivos) para poder fallar rápido, sin dejar un
    # protocolo_proveedor huérfano en storage/ si la persona todavía no
    # confirmó. Sin confirmar_duplicado_ir, se devuelve 409 con los datos de
    # la solicitud existente para que el frontend arme el aviso; con
    # confirmar_duplicado_ir=True (la persona ya vio ese aviso y confirmó),
    # se sigue de largo y se crea igual.
    nro_ir_normalizado = formatear_nro_ir(linea.NUMCOMO, linea.FECCOR)
    existente = solicitud_activa_existente(cursor, nro_ir_normalizado)
    if existente and not body.confirmar_duplicado_ir:
        raise HTTPException(
            status_code=409,
            detail={
                "error": "ir_duplicado",
                "mensaje": f"Ya existe la solicitud {existente.nro_solicitud} para este IR. "
                           "¿Confirmás que necesitás generar una nueva de todas formas?",
                "id_solicitud": existente.id_solicitud,
                "nro_solicitud": existente.nro_solicitud,
                "estado": existente.estado,
                "fecha_solicitud": existente.fecha_solicitud.isoformat(),
            },
        )

    # id_laboratorio: rediseño de esta pantalla, ya no se pide ni se valida
    # -- se resuelve más adelante, por ensayo, al generar el envío. Se deja
    # el chequeo condicional (no se borra) solo por compatibilidad con algún
    # cliente API viejo que todavía lo mande; el formulario actual nunca lo
    # manda.
    if body.id_laboratorio is not None:
        cursor.execute("SELECT 1 FROM lims_laboratorios WHERE id_laboratorio = ? AND activo = 1", body.id_laboratorio)
        if not cursor.fetchone():
            raise HTTPException(status_code=404, detail="El laboratorio indicado no existe o está inactivo")

    cursor.execute("SELECT rol, activo FROM lims_usuarios WHERE id_usuario = ?", body.id_muestreador)
    muestreador = cursor.fetchone()
    if not muestreador or not muestreador.activo:
        raise HTTPException(status_code=404, detail="El muestreador indicado no existe o está inactivo")
    if muestreador.rol not in _ROLES_MUESTREADOR_O_SUPERIOR:
        raise HTTPException(status_code=400, detail="El usuario asignado no tiene un rol habilitado para muestrear")

    # Recepción del proveedor: si vienen usuarios, tienen que existir y
    # estar activos (mismo criterio que completar_datos, unificado en esta
    # misma pantalla).
    for id_usuario, campo in ((body.id_usuario_recibio, "id_usuario_recibio"), (body.id_usuario_rotulo, "id_usuario_rotulo")):
        if id_usuario is not None:
            cursor.execute("SELECT 1 FROM lims_usuarios WHERE id_usuario = ? AND activo = 1", id_usuario)
            if not cursor.fetchone():
                raise HTTPException(status_code=404, detail=f"El usuario indicado en {campo} no existe o está inactivo")

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

    if body.id_laboratorio is not None:
        cursor.execute(
            "SELECT 1 FROM lims_especificacion_ensayos WHERE id_especificacion = ? AND id_laboratorio = ?",
            espec.id_especificacion, body.id_laboratorio,
        )
        if not cursor.fetchone():
            raise HTTPException(
                status_code=400,
                detail="El laboratorio seleccionado no tiene ensayos asignados para la especificación de este artículo",
            )

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
            (nro_solicitud, erp_nro_ir, erp_n01id, erp_IdM21, erp_CODART, erp_DESART, id_especificacion,
             id_laboratorio, id_muestreador, observaciones, estado, id_usuario_qa,
             proveedor_codigo, proveedor_nombre, lote_proveedor, fecha_ingreso, fecha_vencimiento,
             fecha_reanalisis, pais_origen, cantidad_ingresada, unidad_cantidad, nro_bultos,
             metodologia_analisis, fabricante, protocolo_proveedor_path, protocolo_proveedor_nombre_original,
             documentacion_proveedor_path, documentacion_proveedor_nombre_original,
             fecha_factura_proveedor, numero_factura_proveedor, id_usuario_recibio, id_usuario_rotulo)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pendiente', ?,
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        nro_solicitud, nro_ir_normalizado, linea.N01Id, linea.IdM21, linea.CODART, linea.DESART, espec.id_especificacion,
        body.id_laboratorio, body.id_muestreador, body.observaciones, user["id_usuario"],
        body.proveedor_codigo, body.proveedor_nombre, body.lote_proveedor.strip() if body.lote_proveedor else None,
        _a_datetime(fecha_ingreso), _a_datetime(fecha_vencimiento),
        _a_datetime(body.fecha_reanalisis), body.pais_origen, cantidad_ingresada, normalizar_unidad(linea.unidad), body.nro_bultos,
        body.metodologia_analisis, body.fabricante, ruta_protocolo_proveedor, protocolo_proveedor.filename,
        ruta_documentacion_proveedor, nombre_documentacion_proveedor,
        _a_datetime(body.fecha_factura_proveedor), body.numero_factura_proveedor,
        body.id_usuario_recibio, body.id_usuario_rotulo,
    )
    cursor.execute("SELECT @@IDENTITY AS id")
    id_solicitud = int(cursor.fetchone().id)
    try:
        # Columna agregada en migrations_solicitud_sin_vencimiento_ingreso.sql
        # -- si el entorno todavía no la corrió, se omite sin bloquear el
        # resto del alta (mismo criterio de tolerancia usado en todo el
        # módulo, ver _g).
        cursor.execute(
            "UPDATE lims_solicitudes_muestreo SET sin_vencimiento_ingreso_confirmado = ? WHERE id_solicitud = ?",
            1 if body.sin_vencimiento_ingreso_confirmado else 0, id_solicitud,
        )
    except pyodbc.Error:
        pass

    # Grupos de bultos (cantidad de bultos x cantidad de unidades cada uno) --
    # con al menos un grupo, nro_bultos pasa a ser la suma calculada en vez
    # del valor cargado a mano en body.nro_bultos (mismo criterio "no romper
    # lo que ya depende de nro_bultos" pedido para esta feature). Sin
    # grupos, se sigue usando el nro_bultos simple de siempre.
    total_bultos_grupos = guardar_grupos_bultos(cursor, id_solicitud, body.grupos_bultos)
    if total_bultos_grupos is not None:
        cursor.execute(
            "UPDATE lims_solicitudes_muestreo SET nro_bultos = ? WHERE id_solicitud = ?",
            total_bultos_grupos, id_solicitud,
        )

    # La confirmación de "Muestras a tomar" ya no se guarda acá -- se movió
    # a confirmar_orden_trabajo (Ejecutar Muestreo), el único paso común a
    # solicitudes manuales y del agente. Ver OrdenTrabajoDigitalBody.muestras.

    valor_nuevo = {
        "nro_solicitud": nro_solicitud, "erp_nro_ir": nro_ir_normalizado,
        "id_laboratorio": body.id_laboratorio, "id_muestreador": body.id_muestreador,
    }
    if existente:
        # Se llegó hasta acá con una solicitud activa preexistente para este
        # IR solo porque la persona confirmó el aviso (existente and not
        # body.confirmar_duplicado_ir ya habría cortado con 409 más arriba)
        # -- se deja constancia en la auditoría de cuál era la existente y
        # que la creación fue una duplicación deliberada, no un descuido.
        valor_nuevo["duplicado_ir_confirmado"] = True
        valor_nuevo["solicitud_existente"] = existente.nro_solicitud
    audit.registrar(
        conn, entidad="solicitud_muestreo", accion="crear",
        id_usuario=user["id_usuario"], id_entidad=id_solicitud,
        valor_nuevo=valor_nuevo,
    )

    return _fila_a_solicitud(_obtener_solicitud_o_404(cursor, id_solicitud), cursor)


@router.put("/{id_solicitud}/completar-datos", response_model=SolicitudMuestreoResponse)
def completar_datos(
    id_solicitud: int,
    body: SolicitudMuestreoCompletar,
    user: dict = Depends(require_rol("qa", "admin")),
    conn: pyodbc.Connection = Depends(limss_db),
):
    """Completa en una solicitud pendiente los datos que el alta manual pide
    en el momento (obligatorios u opcionales) pero que el agente no puede
    resolver solo con el ERP -- muestreador, lote del proveedor, país de
    origen, fecha de reanálisis, bultos, metodología, fabricante (ver
    app/services/agente_muestreo.py; el protocolo y la documentación del
    proveedor se completan aparte, por archivo, ver POST .../protocolo-
    proveedor y POST .../documentacion-proveedor). Solo toca los campos que
    vengan con valor -- si un campo no se manda, se conserva el que ya
    tenía la solicitud.

    Sin laboratorio (rediseño de esta pantalla): ya no se completa acá para
    ningún origen, ver el docstring de SolicitudMuestreoCompletar."""
    cursor = conn.cursor()
    row = _obtener_solicitud_o_404(cursor, id_solicitud)
    if row.estado != "pendiente":
        raise HTTPException(status_code=400, detail=f"La solicitud está '{row.estado}', no se puede modificar")

    id_muestreador = body.id_muestreador if body.id_muestreador is not None else row.id_muestreador
    lote_proveedor = body.lote_proveedor if body.lote_proveedor is not None else row.lote_proveedor
    # _a_fecha normaliza el fallback -- el driver ODBC no devuelve un tipo
    # consistente para columnas DATE (a veces date/datetime, a veces str,
    # ver _a_fecha más arriba); sin esto, _a_datetime (más abajo, antes del
    # UPDATE) rompe con TypeError si row.fecha_vencimiento/fecha_reanalisis
    # vino como str -- bug real detectado al probar este endpoint, no
    # introducido acá pero corregido de paso porque es la misma función.
    fecha_vencimiento = body.fecha_vencimiento if body.fecha_vencimiento is not None else _a_fecha(row.fecha_vencimiento)
    sin_vencimiento_ingreso_confirmado = (
        body.sin_vencimiento_ingreso_confirmado if body.sin_vencimiento_ingreso_confirmado is not None
        else bool(_g(row, "sin_vencimiento_ingreso_confirmado"))
    )
    fecha_reanalisis = body.fecha_reanalisis if body.fecha_reanalisis is not None else _a_fecha(row.fecha_reanalisis)
    pais_origen = body.pais_origen if body.pais_origen is not None else row.pais_origen
    nro_bultos = body.nro_bultos if body.nro_bultos is not None else row.nro_bultos
    metodologia_analisis = body.metodologia_analisis if body.metodologia_analisis is not None else row.metodologia_analisis
    fabricante = body.fabricante if body.fabricante is not None else row.fabricante
    # Datos de recepción del proveedor (Libro de Ingresos) -- movidos acá
    # desde Ejecutar Muestreo (ver OrdenTrabajoDigitalBody): es QA quien
    # maneja la factura del proveedor y sabe quién recibió/rotuló, no el
    # muestreador. _g porque las columnas son de una migración que puede no
    # estar corrida todavía en este entorno (ver el UPDATE tolerante más
    # abajo).
    fecha_factura_proveedor = body.fecha_factura_proveedor if body.fecha_factura_proveedor is not None else _a_fecha(_g(row, "fecha_factura_proveedor"))
    numero_factura_proveedor = body.numero_factura_proveedor if body.numero_factura_proveedor is not None else _g(row, "numero_factura_proveedor")
    id_usuario_recibio = body.id_usuario_recibio if body.id_usuario_recibio is not None else _g(row, "id_usuario_recibio")
    id_usuario_rotulo = body.id_usuario_rotulo if body.id_usuario_rotulo is not None else _g(row, "id_usuario_rotulo")

    if body.id_muestreador is not None:
        cursor.execute("SELECT rol, activo FROM lims_usuarios WHERE id_usuario = ?", id_muestreador)
        muestreador = cursor.fetchone()
        if not muestreador or not muestreador.activo:
            raise HTTPException(status_code=404, detail="El muestreador indicado no existe o está inactivo")
        if muestreador.rol not in _ROLES_MUESTREADOR_O_SUPERIOR:
            raise HTTPException(status_code=400, detail="El usuario asignado no tiene un rol habilitado para muestrear")

    # Recepción del proveedor: si vienen usuarios, tienen que existir y
    # estar activos (mismo criterio que id_muestreador arriba), para no
    # guardar una referencia a un usuario borrado/desactivado que después
    # el reporte del Libro de Ingresos no pueda resolver.
    for id_usuario, campo in ((body.id_usuario_recibio, "id_usuario_recibio"), (body.id_usuario_rotulo, "id_usuario_rotulo")):
        if id_usuario is not None:
            cursor.execute("SELECT 1 FROM lims_usuarios WHERE id_usuario = ? AND activo = 1", id_usuario)
            if not cursor.fetchone():
                raise HTTPException(status_code=404, detail=f"El usuario indicado en {campo} no existe o está inactivo")

    # Grupos de bultos: con al menos un grupo, reemplaza los grupos ya
    # cargados (completar-datos se puede llamar más de una vez sobre la
    # misma solicitud pendiente) y nro_bultos pasa a ser la suma calculada
    # en vez de lo que haya venido en body.nro_bultos/lo que ya tenía la
    # solicitud -- mismo criterio "no romper lo que ya depende de
    # nro_bultos" pedido para esta feature.
    total_bultos_grupos = guardar_grupos_bultos(cursor, id_solicitud, body.grupos_bultos)
    if total_bultos_grupos is not None:
        nro_bultos = total_bultos_grupos

    cursor.execute(
        """
        UPDATE lims_solicitudes_muestreo
        SET id_muestreador = ?, lote_proveedor = ?, fecha_vencimiento = ?, fecha_reanalisis = ?,
            pais_origen = ?, nro_bultos = ?, metodologia_analisis = ?, fabricante = ?
        WHERE id_solicitud = ?
        """,
        id_muestreador, lote_proveedor, _a_datetime(fecha_vencimiento), _a_datetime(fecha_reanalisis),
        pais_origen, nro_bultos, metodologia_analisis, fabricante, id_solicitud,
    )
    try:
        # Columnas agregadas en la migración del Libro de Ingresos -- si el
        # entorno todavía no la corrió, se omiten sin bloquear el resto de
        # completar-datos (mismo criterio de tolerancia que el resto del
        # módulo, ver _g).
        cursor.execute(
            """
            UPDATE lims_solicitudes_muestreo
            SET fecha_factura_proveedor = ?, numero_factura_proveedor = ?,
                id_usuario_recibio = ?, id_usuario_rotulo = ?
            WHERE id_solicitud = ?
            """,
            _a_datetime(fecha_factura_proveedor), numero_factura_proveedor,
            id_usuario_recibio, id_usuario_rotulo, id_solicitud,
        )
    except pyodbc.Error:
        pass
    try:
        # Columna agregada en migrations_solicitud_sin_vencimiento_ingreso.sql
        cursor.execute(
            "UPDATE lims_solicitudes_muestreo SET sin_vencimiento_ingreso_confirmado = ? WHERE id_solicitud = ?",
            1 if sin_vencimiento_ingreso_confirmado else 0, id_solicitud,
        )
    except pyodbc.Error:
        pass

    audit.registrar(
        conn, entidad="solicitud_muestreo", accion="completar_datos",
        id_usuario=user["id_usuario"], id_entidad=id_solicitud,
        valor_anterior={
            "id_muestreador": row.id_muestreador, "lote_proveedor": row.lote_proveedor,
        },
        valor_nuevo={
            "id_muestreador": id_muestreador, "lote_proveedor": lote_proveedor,
        },
    )

    return _fila_a_solicitud(_obtener_solicitud_o_404(cursor, id_solicitud), cursor)


@router.put("/{id_solicitud}/corregir-recepcion", response_model=SolicitudMuestreoResponse)
def corregir_recepcion(
    id_solicitud: int,
    body: SolicitudMuestreoCorregirRecepcion,
    user: dict = Depends(require_rol("qa", "admin")),
    conn: pyodbc.Connection = Depends(limss_db),
):
    """Excepción CONTROLADA a la regla de "solicitud ejecutada = bloqueada
    para edición" (ver el `if row.estado != "pendiente"` de completar_datos)
    -- únicamente para corregir bultos y datos de recepción del proveedor
    que quedaron mal cargados o incompletos en su momento (caso real: un
    error de carga de bultos hizo que nunca se generaran las etiquetas de
    Cuarentena/Aprobado de los bultos faltantes). No reabre la edición
    general de la solicitud/muestra -- nada más que estos campos puntuales
    se puede tocar por acá, y solo QA/Admin (nunca Muestreador ni Analista
    QC). Motivo obligatorio, se audita junto con el valor anterior/nuevo de
    cada campo efectivamente cambiado (mismo criterio que editar_muestra +
    motivo obligatorio de anular_solicitud).

    Solo aplica a solicitudes YA EJECUTADAS -- una 'pendiente' se sigue
    corrigiendo por completar_datos (edición normal, sin necesitar motivo,
    no es una excepción a ninguna regla) y una 'anulada' no tiene sentido
    corregirla.

    Corregidos los grupos de bultos, la impresión de etiquetas CUARENTENA/
    APROBADO/RECHAZADO ya calcula el total en vivo a partir de
    lims_solicitud_bultos (ver expandir_bultos) -- no hace falta ningún
    otro paso para que el nuevo total se refleje ahí."""
    cursor = conn.cursor()
    row = _obtener_solicitud_o_404(cursor, id_solicitud)
    if row.estado != "ejecutada":
        raise HTTPException(
            status_code=400,
            detail=f"Esta corrección aplica solo a solicitudes ya ejecutadas (estado actual: '{row.estado}')",
        )

    valor_anterior: dict = {}
    valor_nuevo: dict = {}

    if body.grupos_bultos:
        grupos_antes = [
            {"cantidad_bultos": g.cantidad_bultos, "cantidad_unidades": float(g.cantidad_unidades), "unidad_medida": g.unidad_medida}
            for g in obtener_grupos_bultos(cursor, id_solicitud)
        ]
        total_bultos_grupos = guardar_grupos_bultos(cursor, id_solicitud, body.grupos_bultos)
        cursor.execute("UPDATE lims_solicitudes_muestreo SET nro_bultos = ? WHERE id_solicitud = ?", total_bultos_grupos, id_solicitud)
        valor_anterior["grupos_bultos"] = grupos_antes
        valor_anterior["nro_bultos"] = row.nro_bultos
        valor_nuevo["grupos_bultos"] = [g.model_dump() for g in body.grupos_bultos]
        valor_nuevo["nro_bultos"] = total_bultos_grupos

    fecha_factura_actual = _a_fecha(_g(row, "fecha_factura_proveedor"))
    if body.fecha_factura_proveedor is not None and body.fecha_factura_proveedor != fecha_factura_actual:
        try:
            cursor.execute(
                "UPDATE lims_solicitudes_muestreo SET fecha_factura_proveedor = ? WHERE id_solicitud = ?",
                _a_datetime(body.fecha_factura_proveedor), id_solicitud,
            )
            valor_anterior["fecha_factura_proveedor"] = fecha_factura_actual
            valor_nuevo["fecha_factura_proveedor"] = body.fecha_factura_proveedor
        except pyodbc.Error:
            pass

    numero_factura_actual = _g(row, "numero_factura_proveedor")
    if body.numero_factura_proveedor is not None and body.numero_factura_proveedor != numero_factura_actual:
        try:
            cursor.execute(
                "UPDATE lims_solicitudes_muestreo SET numero_factura_proveedor = ? WHERE id_solicitud = ?",
                body.numero_factura_proveedor, id_solicitud,
            )
            valor_anterior["numero_factura_proveedor"] = numero_factura_actual
            valor_nuevo["numero_factura_proveedor"] = body.numero_factura_proveedor
        except pyodbc.Error:
            pass

    if not valor_nuevo:
        raise HTTPException(status_code=400, detail="No se indicó ningún cambio para corregir")

    audit.registrar(
        conn, entidad="solicitud_muestreo", accion="corregir_recepcion",
        id_usuario=user["id_usuario"], id_entidad=id_solicitud,
        valor_anterior=valor_anterior, valor_nuevo=valor_nuevo, motivo=body.motivo,
    )

    return _fila_a_solicitud(_obtener_solicitud_o_404(cursor, id_solicitud), cursor)


@router.get("/{id_solicitud}", response_model=SolicitudMuestreoDetalle)
def detalle_solicitud(
    id_solicitud: int,
    user: dict = Depends(get_current_user),
    conn: pyodbc.Connection = Depends(limss_db),
):
    cursor = conn.cursor()
    row = _obtener_solicitud_o_404(cursor, id_solicitud)
    cantidades = _obtener_cantidades(cursor, row.id_especificacion)
    ensayos = _obtener_ensayos(cursor, id_solicitud, row.id_especificacion)

    base = _fila_a_solicitud(row, cursor)
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
    ensayos = _obtener_ensayos(cursor, id_solicitud, row.id_especificacion)

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
    ensayos = _obtener_ensayos(cursor, id_solicitud, row.id_especificacion)

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
    checklist_materia_prima = [
        it for it in obtener_checklist_muestreo(cursor, row.id_muestra, row.id_especificacion)
        if it.categoria_codigo == "materia_prima"
    ]

    pdf_bytes = generar_pdf_planilla_muestreo(row, checklist_materia_prima)
    return Response(
        content=pdf_bytes, media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{row.nro_solicitud}_planilla_muestreo.pdf"'},
    )


def _tiene_columnas_muestra_adhoc(cursor) -> bool:
    """tipo_muestra/unidad/ad_hoc en lims_solicitud_muestras (y
    id_espec_muestra vuelto nullable) son de la migración que soporta
    muestras ad-hoc -- puede no haberse corrido todavía en este entorno."""
    cursor.execute("SELECT COL_LENGTH('lims_solicitud_muestras', 'ad_hoc') AS c")
    return cursor.fetchone().c is not None


def _guardar_muestras_confirmadas(cursor, id_solicitud: int, id_especificacion: int, muestras) -> None:
    """Reemplaza (DELETE + INSERT) la confirmación de "Muestras a tomar" de
    una solicitud -- estándar (id_espec_muestra de la especificación) o
    ad-hoc (sin id_espec_muestra, con tipo_muestra/unidad propios -- no
    modifica lims_especificacion_muestras, queda asociada solo a esta
    solicitud). Sin la tabla en este entorno, no hace nada (etiquetas caen
    al modelo legacy)."""
    cursor.execute("SELECT OBJECT_ID('lims_solicitud_muestras') AS oid")
    if cursor.fetchone().oid is None:
        return
    tiene_adhoc = _tiene_columnas_muestra_adhoc(cursor)

    # Toda fila estándar (id_espec_muestra no nulo) tiene que pertenecer a
    # la especificación de ESTA solicitud -- si no, un cliente podría mandar
    # el id_espec_muestra de otro producto y terminaría con tipo_muestra/
    # unidad/laboratorio de una especificación ajena (ver el COALESCE del
    # JOIN en _obtener_muestras_confirmadas). Mismo chequeo que ya hacía el
    # código anterior a la refactorización de este flujo (antes en
    # crear_solicitud), ahora acá porque la confirmación se hace en este
    # endpoint (ver docstring de SolicitudMuestreoCreate).
    ids_espec_muestra = {m.id_espec_muestra for m in muestras if m.id_espec_muestra is not None}
    if ids_espec_muestra:
        placeholders = ",".join("?" * len(ids_espec_muestra))
        cursor.execute(
            f"SELECT id FROM lims_especificacion_muestras WHERE id_especificacion = ? AND id IN ({placeholders})",
            id_especificacion, *ids_espec_muestra,
        )
        ids_validos = {r.id for r in cursor.fetchall()}
        ids_invalidos = ids_espec_muestra - ids_validos
        if ids_invalidos:
            raise HTTPException(
                status_code=400,
                detail=f"id_espec_muestra inválido para esta solicitud: {sorted(ids_invalidos)}",
            )

    cursor.execute("DELETE FROM lims_solicitud_muestras WHERE id_solicitud = ?", id_solicitud)
    for m in muestras:
        if m.id_espec_muestra is None and not tiene_adhoc:
            raise HTTPException(
                status_code=503,
                detail="Las muestras ad-hoc todavía no están disponibles en este entorno -- "
                       "falta correr la migración de lims_solicitud_muestras.",
            )
        if tiene_adhoc:
            cursor.execute(
                """
                INSERT INTO lims_solicitud_muestras
                    (id_solicitud, id_espec_muestra, cantidad_real, confirmada, tipo_muestra, unidad, ad_hoc)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                id_solicitud, m.id_espec_muestra, m.cantidad_real, 1 if m.confirmada else 0,
                m.tipo_muestra, normalizar_unidad(m.unidad), 0 if m.id_espec_muestra is not None else 1,
            )
        else:
            cursor.execute(
                "INSERT INTO lims_solicitud_muestras (id_solicitud, id_espec_muestra, cantidad_real, confirmada) VALUES (?, ?, ?, ?)",
                id_solicitud, m.id_espec_muestra, m.cantidad_real, 1 if m.confirmada else 0,
            )


def _obtener_muestras_confirmadas(cursor, id_solicitud: int):
    """Filas de lims_solicitud_muestras confirmadas para esta solicitud, con
    los datos de la muestra (tipo/unidad/laboratorio) -- una etiqueta por
    fila. LEFT JOIN (no INNER) a lims_especificacion_muestras: una fila
    ad-hoc no tiene id_espec_muestra, así que toma tipo_muestra/unidad de
    sus propias columnas en vez de la especificación (COALESCE). Lista
    vacía si la tabla todavía no existe en este entorno (ver
    migrations_solicitud_muestras.sql, pendiente de ejecutar) o si la
    solicitud no tiene ninguna fila (solicitudes creadas antes de esta
    funcionalidad): en ambos casos, descargar_etiquetas cae al modelo legacy
    de 2 etiquetas fijas."""
    cursor.execute("SELECT OBJECT_ID('lims_solicitud_muestras') AS oid")
    if cursor.fetchone().oid is None:
        return []
    if _tiene_columnas_muestra_adhoc(cursor):
        cursor.execute(
            """
            SELECT sm.cantidad_real, COALESCE(sm.tipo_muestra, em.tipo_muestra) AS tipo_muestra,
                   COALESCE(sm.unidad, em.unidad) AS unidad, lab.nombre AS laboratorio_nombre
            FROM lims_solicitud_muestras sm
            LEFT JOIN lims_especificacion_muestras em ON em.id = sm.id_espec_muestra
            LEFT JOIN lims_laboratorios lab ON lab.id_laboratorio = em.id_laboratorio
            WHERE sm.id_solicitud = ? AND sm.confirmada = 1
            ORDER BY CASE WHEN em.orden IS NULL THEN 1 ELSE 0 END, em.orden
            """,
            id_solicitud,
        )
    else:
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


def _obtener_tipos_de_especificacion(cursor, id_especificacion: int):
    """Fallback para una muestra SIN Solicitud de Muestreo asociada (creada
    por "Nueva Muestra"): no existe fila en lims_solicitud_muestras sin una
    solicitud, así que hasta ahora se generaba una sola etiqueta genérica
    aunque la especificación definiera varios tipos de muestra (análisis,
    contramuestra, testigo, ad-hoc) -- bug real detectado con PT019 (4 tipos
    definidos, solo salía 1 etiqueta). Se lee directo de
    lims_especificacion_muestras (la definición, no la confirmación) y se
    genera una etiqueta por tipo -- mismos nombres de columna que
    _obtener_muestras_confirmadas (tipo_muestra, cantidad_real, unidad,
    laboratorio_nombre) para que el llamador no tenga que distinguir el
    origen. cantidad_real acá es la cantidad PLANEADA de la especificación
    (no hay una "real" propia de esta muestra puntual sin confirmación)."""
    cursor.execute(
        """
        SELECT em.tipo_muestra, em.cantidad AS cantidad_real, em.unidad, lab.nombre AS laboratorio_nombre
        FROM lims_especificacion_muestras em
        LEFT JOIN lims_laboratorios lab ON lab.id_laboratorio = em.id_laboratorio
        WHERE em.id_especificacion = ?
        ORDER BY em.orden
        """,
        id_especificacion,
    )
    return cursor.fetchall()


def _generar_pdf_etiquetas_de_solicitud(cursor, row) -> bytes:
    """Arma el PDF de etiquetas para una solicitud ya cargada (fila de
    lims_solicitudes_muestreo) -- función compartida para que "Descargar
    etiquetas" (Solicitudes) y la reimpresión desde Consulta de Muestras
    (ver descargar_etiquetas_de_muestra en muestras.py) generen exactamente
    el mismo PDF en vez de mantener dos caminos que puedan divergir.

    Antes esto podía fallar en silencio (sin traceback en consola) para una
    muestra de Material de Empaque sin codificar, sin lote de proveedor ni
    fecha de vencimiento -- se loguea la excepción real acá, en el único
    lugar donde arman el PDF ambos endpoints, en vez de dejar que se pierda."""
    try:
        iniciales = _iniciales_muestreador(cursor, row.id_muestreador)
        muestras_confirmadas = _obtener_muestras_confirmadas(cursor, row.id_solicitud)
        if muestras_confirmadas:
            return generar_pdf_etiquetas_v2(row, muestras_confirmadas, iniciales)
        # Sin confirmación todavía (solicitud pendiente, o ejecutada antes de
        # que existiera "Muestras a tomar") -- se lee la especificación EN
        # VIVO con _obtener_tipos_de_especificacion (bug real corregido: antes
        # caía acá en _obtener_cantidades, truncado a como máximo 2 tipos
        # fijos -- análisis + contramuestra -- ignorando testigo y cualquier
        # tipo adicional que la especificación definiera). Mismo generador
        # (generar_pdf_etiquetas_v2) que ya usa la rama de arriba: acepta
        # cualquier N de filas con esta misma forma de columnas.
        tipos = _obtener_tipos_de_especificacion(cursor, row.id_especificacion) if row.id_especificacion else []
        if tipos:
            return generar_pdf_etiquetas_v2(row, tipos, iniciales)
        # Última instancia -- especificación sin ninguna fila en
        # lims_especificacion_muestras (dato viejo, de antes de que existiera
        # esa tabla): cae al valor legacy de lims_especificaciones.cantidad_
        # muestra/cantidad_contramuestra (ver _obtener_cantidades).
        cantidades = _obtener_cantidades(cursor, row.id_especificacion)
        return generar_pdf_etiquetas(row, cantidades, iniciales)
    except Exception:
        logger.error(
            "Error generando el PDF de etiquetas (id_solicitud=%s, nro_solicitud=%s)",
            row.id_solicitud, row.nro_solicitud, exc_info=True,
        )
        raise HTTPException(status_code=500, detail="No se pudo generar el PDF de etiquetas -- ver el log del servidor")


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


def _armar_etiquetas_logicas_de_solicitud(cursor, row) -> list[dict]:
    """Misma resolución que _generar_pdf_etiquetas_de_solicitud (PDF) de
    arriba, pero devolviendo etiquetas lógicas en el formato que espera
    generar_sbpl_etiqueta_par -- para que "Etiquetas (SATO)" funcione en una
    solicitud TODAVÍA PENDIENTE (sin id_muestra real, ver imprimir_etiquetas_
    directo_de_solicitud más abajo) exactamente igual que ya funciona
    "Etiquetas (PDF)" para ese mismo caso, en vez de un camino nuevo con
    otra fuente de datos.

    Usa row (la solicitud) en vez de una fila real de lims_muestras -- no
    tiene tipo_referencia propio (esa columna es de lims_muestras, no de
    lims_solicitudes_muestreo), así que la referencia es siempre "IR" para
    este caso, igual que ya asume _dibujar_etiqueta en pdf_solicitud_
    muestreo.py (getattr(solicitud, "tipo_referencia", "ir"))."""
    iniciales = _iniciales_muestreador(cursor, row.id_muestreador)
    datos_base = {
        "identificador": row.nro_solicitud,
        "erp_codart": row.erp_CODART.strip() if row.erp_CODART else None,
        "erp_desart": row.erp_DESART.strip() if row.erp_DESART else None,
        "nro_ir": row.erp_nro_ir,
        "etiqueta_referencia": etiqueta_referencia(getattr(row, "tipo_referencia", "ir")),
        "fecha": row.fecha_solicitud,
        "iniciales_muestreador": iniciales,
    }

    # Igual que el PDF: si ya hay tipos confirmados (lims_solicitud_muestras
    # -- puede pasar incluso antes de ejecutar el muestreo, ver el
    # comentario de "Muestras a tomar" en CargaResultadosOrdenTrabajoPage.jsx),
    # una etiqueta lógica por tipo.
    tipos_confirmados = _obtener_muestras_confirmadas(cursor, row.id_solicitud)

    def _etiquetas_desde_tipos(tipos):
        etiquetas = []
        for t in tipos:
            d = dict(datos_base)
            d["titulo"] = titulo_etiqueta_por_tipo(t.tipo_muestra)
            d["cantidad_muestra_texto"] = (
                f"{formatear_cantidad(t.cantidad_real)} {t.unidad or ''}".strip() if t.cantidad_real is not None else None
            )
            d["laboratorio_nombre"] = t.laboratorio_nombre
            etiquetas.append(d)
        return etiquetas

    if tipos_confirmados:
        return _etiquetas_desde_tipos(tipos_confirmados)

    # Sin confirmación todavía -- se lee la especificación EN VIVO (bug real
    # corregido: antes caía acá en el modelo legacy de 2 etiquetas fijas --
    # análisis + contramuestra -- leídas de _obtener_cantidades, ignorando
    # testigo y cualquier tipo adicional que la especificación definiera).
    # Mismo generador (_etiquetas_desde_tipos) que la rama de arriba, mismas
    # columnas que devuelve _obtener_tipos_de_especificacion.
    tipos_espec = _obtener_tipos_de_especificacion(cursor, row.id_especificacion) if row.id_especificacion else []
    if tipos_espec:
        return _etiquetas_desde_tipos(tipos_espec)

    # Última instancia -- especificación sin ninguna fila en
    # lims_especificacion_muestras (dato viejo): cae al valor legacy de
    # lims_especificaciones.cantidad_muestra/cantidad_contramuestra (ver
    # _obtener_cantidades), como máximo 2 etiquetas fijas.
    cantidades = _obtener_cantidades(cursor, row.id_especificacion)

    def _cantidad_o_none(cantidad, unidad):
        return f"{formatear_cantidad(cantidad)} {unidad or ''}".strip() if cantidad is not None else None

    d_analisis = dict(datos_base)
    d_analisis["titulo"] = "MUESTRA PARA ANÁLISIS"
    d_analisis["cantidad_muestra_texto"] = _cantidad_o_none(cantidades.get("cantidad_muestra"), cantidades.get("unidad_muestra"))
    d_analisis["laboratorio_nombre"] = row.laboratorio_nombre

    d_contra = dict(datos_base)
    d_contra["titulo"] = "CONTRAMUESTRA"
    d_contra["cantidad_muestra_texto"] = _cantidad_o_none(cantidades.get("cantidad_contramuestra"), cantidades.get("unidad_contramuestra"))
    d_contra["laboratorio_nombre"] = None

    return [d_analisis, d_contra]


@router.get("/{id_solicitud}/etiquetas-cantidad", response_model=CantidadEtiquetasResponse)
def contar_etiquetas_a_imprimir_de_solicitud(
    id_solicitud: int,
    user: dict = Depends(get_current_user),
    conn: pyodbc.Connection = Depends(limss_db),
):
    """Preview de cantidad para "Etiquetas (SATO)" en una solicitud
    PENDIENTE -- misma idea que GET /api/muestras/{id_muestra}/etiquetas-
    cantidad, pero a partir de la solicitud directamente (sin id_muestra
    real todavía)."""
    cursor = conn.cursor()
    row = _obtener_solicitud_o_404(cursor, id_solicitud)
    etiquetas = _armar_etiquetas_logicas_de_solicitud(cursor, row)
    return CantidadEtiquetasResponse(
        cantidad_muestras=len(etiquetas),
        cantidad_etiquetas_fisicas=len(armar_pares_etiquetas_muestra(etiquetas)),
    )


@router.post("/{id_solicitud}/imprimir-directo", response_model=ImprimirDirectoResponse)
def imprimir_etiquetas_directo_de_solicitud(
    id_solicitud: int,
    body: ImprimirDirectoBody,
    user: dict = Depends(require_rol("muestreador", "analista_qc", "qa", "admin")),
    conn: pyodbc.Connection = Depends(limss_db),
):
    """Alternativa SATO a "Descargar etiquetas" (PDF) para una solicitud
    TODAVÍA PENDIENTE (sin id_muestra real) -- antes el botón "Etiquetas
    (SATO)" quedaba oculto en ese caso porque el único camino de impresión
    directa (POST /api/muestras/{id_muestra}/imprimir-directo) necesitaba
    una fila real de lims_muestras. Este endpoint usa la misma fuente de
    datos que ya usa el PDF para una solicitud pendiente (ver
    _armar_etiquetas_logicas_de_solicitud), agrupadas de a 2 por etiqueta
    física igual que el resto de las etiquetas de muestra.

    Para una solicitud YA EJECUTADA (con id_muestra), el frontend sigue
    usando el endpoint de muestras.py sin cambios -- éste es específicamente
    para el caso sin muestra todavía."""
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM lims_impresoras_etiquetas WHERE id_impresora = ? AND activa = 1", body.id_impresora)
    impresora = cursor.fetchone()
    if not impresora:
        raise HTTPException(status_code=404, detail="La impresora indicada no existe o está inactiva")

    row = _obtener_solicitud_o_404(cursor, id_solicitud)
    etiquetas = _armar_etiquetas_logicas_de_solicitud(cursor, row)

    pares = armar_pares_etiquetas_muestra(etiquetas)
    enviadas = 0
    for arriba, abajo in pares:
        sbpl_bytes = generar_sbpl_etiqueta_par(
            arriba, abajo, impresora.ancho_mm, impresora.alto_mm, impresora.resolucion_dpi, cantidad_copias=body.cantidad,
        )
        nombre_trabajo = f"Etiqueta {arriba['identificador']}"
        if abajo:
            nombre_trabajo += f" + {abajo['identificador']}"
        try:
            imprimir_sbpl(impresora, sbpl_bytes, nombre_trabajo=nombre_trabajo)
        except RuntimeError as e:
            detalle = str(e)
            if enviadas:
                detalle += f" (se enviaron {enviadas} de {len(pares)} etiquetas antes de este error)"
            raise HTTPException(status_code=502, detail=detalle)
        enviadas += 1

    audit.registrar(
        conn, entidad="etiqueta", accion="imprimir_directo",
        id_usuario=user["id_usuario"], id_entidad=id_solicitud,
        valor_nuevo={"id_impresora": body.id_impresora, "ruta_red": impresora.ruta_red, "cantidad_etiquetas": enviadas},
    )

    plural = "s" if enviadas != 1 else ""
    return ImprimirDirectoResponse(ok=True, mensaje=f"{enviadas} etiqueta{plural} enviada{plural} a {impresora.nombre}")


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


@router.post("/{id_solicitud}/protocolo-proveedor", response_model=SolicitudMuestreoResponse)
def subir_protocolo_proveedor(
    id_solicitud: int,
    protocolo_proveedor: UploadFile = File(
        ..., description="Protocolo que entrega el proveedor junto con el lote (foto o PDF)",
    ),
    motivo: Optional[str] = Form(None, description="Motivo, si este reemplazo es parte de una corrección post-ejecución (ver PUT .../corregir-recepcion)"),
    user: dict = Depends(require_rol("qa", "admin")),
    conn: pyodbc.Connection = Depends(limss_db),
):
    """Adjunta (o reemplaza, si ya había uno) el protocolo del proveedor de
    una solicitud ya creada -- en el alta manual es obligatorio en el
    momento (ver POST ""), pero las solicitudes que genera el agente no lo
    tienen disponible en ese flujo automático (ver
    app/services/agente_muestreo.py), así que hace falta este endpoint
    aparte para que QA lo cargue después. Sigue siendo obligatorio antes de
    poder ejecutar el muestreo -- ver los checks en
    confirmar_orden_trabajo/generar_envio_anticipado.

    No chequea el estado de la solicitud -- también se usa para reemplazar
    el protocolo de una solicitud YA EJECUTADA como parte de "Corregir
    datos de recepción" (ver corregir_recepcion), de ahí el `motivo`
    opcional: si viene, queda en el mismo audit trail que el resto de esa
    corrección puntual."""
    if not protocolo_proveedor.filename:
        raise HTTPException(status_code=422, detail="No se recibió ningún archivo")

    cursor = conn.cursor()
    row = _obtener_solicitud_o_404(cursor, id_solicitud)
    nombre_anterior = _g(row, "protocolo_proveedor_nombre_original")

    ruta = storage.guardar_protocolo_proveedor(protocolo_proveedor, row.nro_solicitud)
    cursor.execute(
        "UPDATE lims_solicitudes_muestreo SET protocolo_proveedor_path = ?, protocolo_proveedor_nombre_original = ? "
        "WHERE id_solicitud = ?",
        ruta, protocolo_proveedor.filename, id_solicitud,
    )

    audit.registrar(
        conn, entidad="solicitud_muestreo", accion="adjuntar_protocolo_proveedor",
        id_usuario=user["id_usuario"], id_entidad=id_solicitud,
        valor_anterior={"protocolo_proveedor_nombre_original": nombre_anterior} if nombre_anterior else None,
        valor_nuevo={"protocolo_proveedor_nombre_original": protocolo_proveedor.filename},
        motivo=motivo,
    )

    return _fila_a_solicitud(_obtener_solicitud_o_404(cursor, id_solicitud), cursor)


@router.post("/{id_solicitud}/documentacion-proveedor", response_model=SolicitudMuestreoResponse)
def subir_documentacion_proveedor(
    id_solicitud: int,
    documentacion_proveedor: UploadFile = File(
        ..., description="Documentación del proveedor (remito y/o factura en un solo archivo, foto o PDF)",
    ),
    motivo: Optional[str] = Form(None, description="Motivo, si este reemplazo es parte de una corrección post-ejecución (ver PUT .../corregir-recepcion)"),
    user: dict = Depends(require_rol("qa", "admin")),
    conn: pyodbc.Connection = Depends(limss_db),
):
    """Adjunta (o reemplaza, si ya había una) la documentación del proveedor
    de una solicitud ya creada -- a diferencia del protocolo, este adjunto
    no se exige en el momento de crear la solicitud, así que hace falta este
    endpoint aparte para poder cargarlo después.

    No chequea el estado de la solicitud -- también se usa para reemplazar
    la documentación de una solicitud YA EJECUTADA como parte de "Corregir
    datos de recepción" (ver corregir_recepcion), de ahí el `motivo`
    opcional: si viene, queda en el mismo audit trail que el resto de esa
    corrección puntual."""
    if not documentacion_proveedor.filename:
        raise HTTPException(status_code=422, detail="No se recibió ningún archivo")

    cursor = conn.cursor()
    row = _obtener_solicitud_o_404(cursor, id_solicitud)
    nombre_anterior = _g(row, "documentacion_proveedor_nombre_original")

    ruta = storage.guardar_documentacion_proveedor(documentacion_proveedor, row.nro_solicitud)
    cursor.execute(
        "UPDATE lims_solicitudes_muestreo SET documentacion_proveedor_path = ?, documentacion_proveedor_nombre_original = ? "
        "WHERE id_solicitud = ?",
        ruta, documentacion_proveedor.filename, id_solicitud,
    )

    audit.registrar(
        conn, entidad="solicitud_muestreo", accion="adjuntar_documentacion_proveedor",
        id_usuario=user["id_usuario"], id_entidad=id_solicitud,
        valor_anterior={"documentacion_proveedor_nombre_original": nombre_anterior} if nombre_anterior else None,
        valor_nuevo={"documentacion_proveedor_nombre_original": documentacion_proveedor.filename},
        motivo=motivo,
    )

    return _fila_a_solicitud(_obtener_solicitud_o_404(cursor, id_solicitud), cursor)


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
        id_especificacion=row.id_especificacion,
        fecha_vencimiento_sugerida=_a_fecha(row.fecha_vencimiento),
        datos_fisicos=DatosFisicosMuestreo(
            aspecto_externo=row.aspecto_externo, cierre=row.cierre,
            aspecto_interno=row.aspecto_interno, precintos=row.precintos,
            identificacion_contenedor=_g(row, "identificacion_contenedor"),
            fecha_vencimiento_real=_a_fecha(_g(row, "fecha_vencimiento_real")),
            sin_vencimiento_confirmado=bool(_g(row, "sin_vencimiento_confirmado")),
            fecha_reanalisis_real=_a_fecha(_g(row, "fecha_reanalisis_real")),
            aspecto_mp=_g(row, "aspecto_mp"),
            materias_extranas=row.materias_extranas, olor=row.olor, color=row.color,
            observaciones_muestreo=row.observaciones_muestreo,
            nro_bultos_muestreados=row.nro_bultos_muestreados,
        ),
        checklist_muestreo=obtener_checklist_muestreo(cursor, row.id_muestra, row.id_especificacion),
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
    _verificar_completa_para_ejecutar(cursor, row)

    id_muestra, codigo_muestra = _crear_muestra_desde_solicitud(conn, cursor, row, datos_muestreo_pendientes=True)
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
    _verificar_completa_para_ejecutar(cursor, row)

    df = body.datos_fisicos
    # "Datos físicos del muestreo" se sacó de Ejecutar Muestreo -- ningún
    # campo del bloque (incluida esta confirmación de vencimiento) tiene
    # reemplazo real en otro lado, pero se eliminó igual. df llega siempre
    # con sus valores por default (ver OrdenTrabajoDigitalBody), así que ya
    # no tiene sentido exigir fecha_vencimiento_real/sin_vencimiento_
    # confirmado -- el frontend nunca los va a mandar.
    tiene_columna_sin_vencimiento = _tiene_columna_sin_vencimiento_confirmado(cursor)

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

    if tiene_columna_sin_vencimiento:
        cursor.execute(
            "UPDATE lims_solicitudes_muestreo SET sin_vencimiento_confirmado = ? WHERE id_solicitud = ?",
            1 if df.sin_vencimiento_confirmado else 0, id_solicitud,
        )

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
        id_muestra, codigo_muestra = _crear_muestra_desde_solicitud(conn, cursor, row, datos_muestreo_pendientes=False)
        cursor.execute(
            "UPDATE lims_solicitudes_muestreo SET id_muestra = ? WHERE id_solicitud = ?",
            id_muestra, id_solicitud,
        )
        accion_auditoria = "crear_desde_orden_trabajo"

    cursor.execute(
        "UPDATE lims_solicitudes_muestreo SET estado = 'ejecutada' WHERE id_solicitud = ?",
        id_solicitud,
    )

    # Checklist configurable de etapa 'muestreo' -- misma función que usa el
    # checklist de Nueva Muestra (creación directa), ver
    # app/services/especificaciones.py.
    guardar_checklist_muestreo(cursor, id_muestra, row.id_especificacion, body.checklist_muestreo, user["id_usuario"])

    # Confirmación de "Muestras a tomar" -- estándar (de la especificación) o
    # ad-hoc (agregada a mano para esta solicitud puntual, ver
    # MuestraConfirmadaInput). Mismo momento para solicitudes manuales y del
    # agente (antes solo se pedía al crear, y el agente nunca pasa por ese
    # formulario -- ver docstring de SolicitudMuestreoCreate).
    _guardar_muestras_confirmadas(cursor, id_solicitud, row.id_especificacion, body.muestras)

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

    return _fila_a_solicitud(_obtener_solicitud_o_404(cursor, id_solicitud), cursor)


@router.post("/{id_solicitud}/imprimir-cuarentena", response_model=ImprimirDirectoResponse)
def imprimir_etiquetas_cuarentena(
    id_solicitud: int,
    body: ImprimirDirectoBody,
    user: dict = Depends(require_rol("analista_qc", "qa", "admin")),
    conn: pyodbc.Connection = Depends(limss_db),
):
    """Una etiqueta CUARENTENA por cada bulto de la solicitud -- no es
    automático, lo dispara la persona desde la pantalla de Solicitudes de
    Muestreo. Si la solicitud tiene grupos de bultos cargados (cantidad de
    bultos x cantidad de unidades cada uno, ver lims_solicitud_bultos /
    app/services/bultos.py), cada etiqueta muestra la cantidad de SU grupo
    en vez de la cantidad general del ingreso (ej. "4 x 50kg" + "1 x 30kg"
    -- 4 etiquetas con "50kg" y una con "30kg", contador 1/5 a 5/5 continuo
    a través de ambos grupos). Sin grupos cargados, se comporta igual que
    antes de esta feature (nro_bultos etiquetas idénticas). Solicitudes de
    Muestreo es siempre por IR (materia prima), nunca por lote, así que la
    etiqueta de referencia es fija ("IR"), a diferencia de la etiqueta de
    muestra que sí puede ser IR o LOTE."""
    cursor = conn.cursor()
    row = _obtener_solicitud_o_404(cursor, id_solicitud)

    if not row.nro_bultos or row.nro_bultos < 1:
        raise HTTPException(
            status_code=400,
            detail="La solicitud no tiene cargada la cantidad de bultos -- completala antes de imprimir CUARENTENA",
        )

    cursor.execute("SELECT * FROM lims_impresoras_etiquetas WHERE id_impresora = ? AND activa = 1", body.id_impresora)
    impresora = cursor.fetchone()
    if not impresora:
        raise HTTPException(status_code=404, detail="La impresora indicada no existe o está inactiva")

    cantidad_texto = f"{formatear_cantidad(row.cantidad_ingresada)} {row.unidad_cantidad or ''}".strip()
    datos_base = {
        "erp_desart": row.erp_DESART,
        "erp_codart": row.erp_CODART,
        "nro_ir": row.erp_nro_ir,
        "etiqueta_referencia": "IR",
        "fecha_ingreso": _a_fecha(row.fecha_ingreso),
        "fecha_vencimiento": _a_fecha(row.fecha_vencimiento),
    }

    # Grupos de bultos (cantidad de bultos x cantidad de unidades cada uno) --
    # sin grupos cargados (solicitud vieja, de antes de esta feature), se
    # arma un único grupo implícito de nro_bultos etiquetas con la cantidad
    # general del ingreso, igual que el comportamiento de siempre.
    grupos = obtener_grupos_bultos(cursor, id_solicitud)
    bultos = expandir_bultos(grupos, row.nro_bultos, cantidad_texto, cantidad_valor_fallback=row.cantidad_ingresada)
    total_bultos = bultos[0].bulto_total

    try:
        bultos_a_imprimir = filtrar_rango_bultos(bultos, body.desde_bulto, body.hasta_bulto)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    enviadas = 0
    for b in bultos_a_imprimir:
        datos = dict(
            datos_base, bulto_actual=b.bulto_actual, bulto_total=b.bulto_total,
            cantidad_texto=b.cantidad_texto, cantidad_valor=b.cantidad_valor,
        )
        sbpl_bytes = generar_sbpl_etiqueta_estado(
            datos, "CUARENTENA", impresora.ancho_mm, impresora.alto_mm, impresora.resolucion_dpi,
            cantidad_copias=body.cantidad,
        )
        try:
            imprimir_sbpl(impresora, sbpl_bytes, nombre_trabajo=f"Cuarentena {row.nro_solicitud} {b.bulto_actual}/{b.bulto_total}")
        except RuntimeError as e:
            detalle = str(e)
            if enviadas:
                detalle += f" (se enviaron {enviadas} de {len(bultos_a_imprimir)} etiquetas antes de este error)"
            raise HTTPException(status_code=502, detail=detalle)
        enviadas += 1

    audit.registrar(
        conn, entidad="etiqueta_cuarentena", accion="imprimir",
        id_usuario=user["id_usuario"], id_entidad=id_solicitud,
        valor_nuevo={
            "id_impresora": body.id_impresora, "ruta_red": impresora.ruta_red, "cantidad_etiquetas": enviadas,
            "desde_bulto": body.desde_bulto, "hasta_bulto": body.hasta_bulto,
        },
    )

    plural = "s" if enviadas != 1 else ""
    mensaje = f"{enviadas} etiqueta{plural} CUARENTENA enviada{plural} a {impresora.nombre}"
    if len(bultos_a_imprimir) != total_bultos:
        mensaje += f" (bultos {bultos_a_imprimir[0].bulto_actual} a {bultos_a_imprimir[-1].bulto_actual} de {total_bultos})"
    return ImprimirDirectoResponse(ok=True, mensaje=mensaje)


# Reexport para app/api/routes/integraciones.py: la creación de muestra desde
# la integración con el eBR usa el mismo generador de código SAMP-AAAA-NNNN
# que el flujo normal de confirmación de muestreo, en vez de duplicarlo.
generar_codigo_muestra = _generar_codigo_muestra

# Reexport para app/services/agente_muestreo.py: la solicitud que genera el
# agente al detectar un IR nuevo usa el mismo generador de nro_solicitud
# SOL-AAAA-NNN que "+ Nueva solicitud", en vez de duplicarlo.
generar_nro_solicitud = _generar_nro_solicitud

# Reexport para app/api/routes/muestras.py: la reimpresión de etiquetas desde
# Consulta de Muestras usa el mismo armado de PDF que "Descargar etiquetas"
# en Solicitudes, en vez de un template paralelo. iniciales_muestreador
# también se reusa ahí para la etiqueta simplificada de una muestra sin
# Solicitud de Muestreo asociada (ver generar_pdf_etiqueta_muestra).
# obtener_muestras_confirmadas se reusa para que la impresión directa
# (SBPL) imprima una etiqueta por cada tipo de muestra confirmado, igual
# que ya hace generar_pdf_etiquetas_v2 -- misma fuente de datos para los
# dos caminos, no una lógica de iteración paralela.
obtener_solicitud_o_404 = _obtener_solicitud_o_404
generar_pdf_etiquetas_de_solicitud = _generar_pdf_etiquetas_de_solicitud
iniciales_muestreador = _iniciales_muestreador
obtener_muestras_confirmadas = _obtener_muestras_confirmadas
obtener_tipos_de_especificacion = _obtener_tipos_de_especificacion
