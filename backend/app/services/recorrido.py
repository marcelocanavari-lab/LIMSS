"""
Agregación compartida "muestra + todos sus envíos + resultados + dictamen".
Ver app/schemas/recorrido.py para el detalle de las respuestas.
"""
from datetime import date, datetime
from typing import Optional

from app.schemas.recorrido import (
    DictamenInfo,
    EnsayoResultado,
    EnvioDetalleInfo,
    ProtocoloEnvioInfo,
    RecorridoResponse,
    SolicitudRecorridoInfo,
    TestigoEnvioInfo,
)
from app.schemas.solicitudes_muestreo import DatosFisicosMuestreo


def _a_fecha(valor) -> Optional[date]:
    """El driver ODBC no devuelve un tipo consistente para columnas DATE en
    este entorno (a veces date/datetime, a veces str); se normaliza siempre
    a date antes de operar (mismo patrón que solicitudes_muestreo.py)."""
    if valor is None:
        return None
    if isinstance(valor, datetime):
        return valor.date()
    if isinstance(valor, date):
        return valor
    return date.fromisoformat(str(valor))


def _g(row, atributo: str):
    """Lee un atributo que puede no existir todavía en el esquema real (ver
    migrations_solicitudes_muestreo_datos_fisicos_v2.sql, pendiente de
    ejecutar en algunos entornos)."""
    return getattr(row, atributo, None)


def construir_recorrido(cursor, id_muestra: int) -> Optional[RecorridoResponse]:
    cursor.execute(
        """
        SELECT m.*, u.nombre + ' ' + u.apellido AS usuario_muestreo_nombre
        FROM lims_muestras m
        INNER JOIN lims_usuarios u ON u.id_usuario = m.id_usuario_muestreo
        WHERE m.id_muestra = ?
        """,
        id_muestra,
    )
    muestra = cursor.fetchone()
    if not muestra:
        return None

    cursor.execute(
        "SELECT id_envio, id_laboratorio, fecha_despacho FROM lims_envios WHERE id_muestra = ? ORDER BY id_envio",
        id_muestra,
    )
    envios_rows = cursor.fetchall()

    envios: list[EnvioDetalleInfo] = []
    hay_oos = False
    for e in envios_rows:
        cursor.execute("SELECT nombre FROM lims_laboratorios WHERE id_laboratorio = ?", e.id_laboratorio)
        lab = cursor.fetchone()

        cursor.execute(
            """
            SELECT se.id_espec_ensayo, se.orden, em.nombre_ensayo, se.metodologia, se.tipo_dato,
                   se.limite_inferior, se.limite_superior, se.unidad_medida, se.valor_requerido, se.obligatorio,
                   r.valor_numerico, r.valor_cualitativo, r.dentro_especificacion
            FROM lims_envio_ensayos ee
            INNER JOIN lims_especificacion_ensayos se ON se.id_espec_ensayo = ee.id_espec_ensayo
            INNER JOIN lims_ensayos_maestro em ON em.id_ensayo_maestro = se.id_ensayo_maestro
            LEFT JOIN lims_resultados r ON r.id_espec_ensayo = ee.id_espec_ensayo AND r.id_envio = ee.id_envio
            WHERE ee.id_envio = ?
            ORDER BY se.orden
            """,
            e.id_envio,
        )
        ensayos: list[EnsayoResultado] = []
        completo = True
        for r in cursor.fetchall():
            dentro = bool(r.dentro_especificacion) if r.dentro_especificacion is not None else None
            if dentro is False:
                hay_oos = True
            tiene_valor = r.valor_numerico is not None or bool((r.valor_cualitativo or "").strip())
            if bool(r.obligatorio) and not tiene_valor:
                completo = False
            ensayos.append(EnsayoResultado(
                id_espec_ensayo=r.id_espec_ensayo,
                orden=r.orden,
                nombre_ensayo=r.nombre_ensayo,
                metodologia=r.metodologia,
                tipo_dato=r.tipo_dato,
                limite_inferior=float(r.limite_inferior) if r.limite_inferior is not None else None,
                limite_superior=float(r.limite_superior) if r.limite_superior is not None else None,
                unidad_medida=r.unidad_medida,
                valor_requerido=r.valor_requerido,
                obligatorio=bool(r.obligatorio),
                valor_numerico=float(r.valor_numerico) if r.valor_numerico is not None else None,
                valor_cualitativo=r.valor_cualitativo,
                dentro_especificacion=dentro,
            ))

        cursor.execute(
            """
            SELECT t.id_testigo, t.codigo, t.nombre
            FROM lims_envio_testigos et
            INNER JOIN lims_testigos t ON t.id_testigo = et.id_testigo
            WHERE et.id_envio = ?
            ORDER BY t.codigo
            """,
            e.id_envio,
        )
        testigos = [
            TestigoEnvioInfo(id_testigo=t.id_testigo, codigo=t.codigo, nombre=t.nombre)
            for t in cursor.fetchall()
        ]

        cursor.execute(
            """
            SELECT TOP 1 nro_protocolo_ext, fecha_emision, pdf_nombre_original
            FROM lims_protocolos WHERE id_envio = ? ORDER BY fecha_carga DESC
            """,
            e.id_envio,
        )
        p = cursor.fetchone()
        protocolo = (
            ProtocoloEnvioInfo(
                nro_protocolo_ext=p.nro_protocolo_ext,
                fecha_emision=p.fecha_emision,
                pdf_nombre_original=p.pdf_nombre_original,
            )
            if p
            else None
        )

        # El número real de remito lo genera el sistema (lims_remitos,
        # nro_remito_interno) -- ebr_envios.nro_remito es un campo manual
        # que casi siempre queda vacío (mismo bug ya visto en Facturación).
        # Un envío puede tener más de una fila en lims_remitos (sin UNIQUE
        # sobre id_envio); se toma la más reciente, igual que el protocolo.
        cursor.execute(
            "SELECT TOP 1 nro_remito_interno FROM lims_remitos WHERE id_envio = ? ORDER BY fecha_generacion DESC",
            e.id_envio,
        )
        rem = cursor.fetchone()

        envios.append(EnvioDetalleInfo(
            id_envio=e.id_envio,
            laboratorio_nombre=lab.nombre if lab else "—",
            fecha_despacho=e.fecha_despacho,
            nro_remito=rem.nro_remito_interno if rem else None,
            testigos=testigos,
            protocolo=protocolo,
            ensayos=ensayos,
            completo=completo,
        ))

    # Resultados de la Orden de Trabajo (Solicitud de Muestreo) -- no tiene
    # dictamen propio, se integra acá igual que los ensayos de cada envío.
    # Filtrados por el laboratorio elegido al crear la solicitud (mismo
    # criterio que ensayos-para-orden). Una muestra normalmente tiene a lo
    # sumo una solicitud vinculada, pero se recorre por si hubiera más de una.
    # SELECT s.* (no una lista a mano) porque _g() más abajo necesita poder
    # leer las columnas de la migración v2 (identificacion_contenedor,
    # fecha_vencimiento_real, fecha_reanalisis_real, aspecto_mp) cuando
    # existen -- con una lista explícita que no las incluyera, _g() las iba a
    # ver siempre ausentes (columna nunca seleccionada) y no "ausente en este
    # entorno", que es la única razón por la que debería devolver None.
    cursor.execute(
        """
        SELECT s.*, u.nombre + ' ' + u.apellido AS usuario_qa_nombre
        FROM lims_solicitudes_muestreo s
        INNER JOIN lims_usuarios u ON u.id_usuario = s.id_usuario_qa
        WHERE s.id_muestra = ? AND s.id_especificacion IS NOT NULL
        """,
        id_muestra,
    )
    solicitudes_ot = cursor.fetchall()

    # Una muestra tiene a lo sumo una Solicitud de Muestreo vinculada en la
    # práctica; se toma la primera para los datos de cabecera de la Sección 2
    # del reporte (los ensayos de TODAS las solicitudes igual se agregan más
    # abajo, por si hubiera más de una).
    solicitud_info: Optional[SolicitudRecorridoInfo] = None
    if solicitudes_ot:
        s0 = solicitudes_ot[0]
        solicitud_info = SolicitudRecorridoInfo(
            nro_solicitud=s0.nro_solicitud,
            usuario_qa_nombre=s0.usuario_qa_nombre,
            fecha_solicitud=s0.fecha_solicitud,
            proveedor_codigo=s0.proveedor_codigo,
            proveedor_nombre=s0.proveedor_nombre,
            lote_proveedor=s0.lote_proveedor,
            fecha_vencimiento=_a_fecha(s0.fecha_vencimiento),
            fecha_reanalisis=_a_fecha(s0.fecha_reanalisis),
            datos_fisicos=DatosFisicosMuestreo(
                aspecto_externo=s0.aspecto_externo,
                cierre=s0.cierre,
                aspecto_interno=s0.aspecto_interno,
                precintos=s0.precintos,
                identificacion_contenedor=_g(s0, "identificacion_contenedor"),
                fecha_vencimiento_real=_a_fecha(_g(s0, "fecha_vencimiento_real")),
                fecha_reanalisis_real=_a_fecha(_g(s0, "fecha_reanalisis_real")),
                aspecto_mp=_g(s0, "aspecto_mp"),
                materias_extranas=s0.materias_extranas,
                olor=s0.olor,
                color=s0.color,
                observaciones_muestreo=s0.observaciones_muestreo,
                nro_bultos_muestreados=s0.nro_bultos_muestreados,
            ),
        )

    resultados_orden_trabajo: list[EnsayoResultado] = []
    for s in solicitudes_ot:
        cursor.execute(
            """
            SELECT se.id_espec_ensayo, se.orden, em.nombre_ensayo, se.metodologia, se.tipo_dato,
                   se.limite_inferior, se.limite_superior, se.unidad_medida, se.valor_requerido, se.obligatorio,
                   r.valor_numerico, r.valor_cualitativo, r.dentro_especificacion
            FROM lims_especificacion_ensayos se
            INNER JOIN lims_ensayos_maestro em ON em.id_ensayo_maestro = se.id_ensayo_maestro
            LEFT JOIN lims_orden_trabajo_resultados r ON r.id_espec_ensayo = se.id_espec_ensayo AND r.id_solicitud = ?
            WHERE se.id_especificacion = ? AND se.id_laboratorio = ?
            ORDER BY se.orden
            """,
            s.id_solicitud, s.id_especificacion, s.id_laboratorio,
        )
        for r in cursor.fetchall():
            dentro = bool(r.dentro_especificacion) if r.dentro_especificacion is not None else None
            if dentro is False:
                hay_oos = True
            resultados_orden_trabajo.append(EnsayoResultado(
                id_espec_ensayo=r.id_espec_ensayo,
                orden=r.orden,
                nombre_ensayo=r.nombre_ensayo,
                metodologia=r.metodologia,
                tipo_dato=r.tipo_dato,
                limite_inferior=float(r.limite_inferior) if r.limite_inferior is not None else None,
                limite_superior=float(r.limite_superior) if r.limite_superior is not None else None,
                unidad_medida=r.unidad_medida,
                valor_requerido=r.valor_requerido,
                obligatorio=bool(r.obligatorio),
                valor_numerico=float(r.valor_numerico) if r.valor_numerico is not None else None,
                valor_cualitativo=r.valor_cualitativo,
                dentro_especificacion=dentro,
            ))

    cursor.execute(
        """
        SELECT d.estado_dictamen, d.fecha_dictamen, d.justificacion_oos, d.observaciones,
               u.nombre + ' ' + u.apellido AS usuario_qa_nombre
        FROM lims_dictamenes d
        INNER JOIN lims_usuarios u ON u.id_usuario = d.id_usuario_qa
        WHERE d.id_muestra = ?
        """,
        id_muestra,
    )
    d = cursor.fetchone()
    dictamen = (
        DictamenInfo(
            estado_dictamen=d.estado_dictamen,
            usuario_qa_nombre=d.usuario_qa_nombre,
            fecha_dictamen=d.fecha_dictamen,
            justificacion_oos=d.justificacion_oos,
            observaciones=d.observaciones,
        )
        if d
        else None
    )

    return RecorridoResponse(
        id_muestra=muestra.id_muestra,
        codigo_muestra=muestra.codigo_muestra,
        erp_CODART=muestra.erp_CODART,
        erp_DESART=muestra.erp_DESART,
        tipo_material=muestra.tipo_material,
        erp_proveedor=muestra.erp_proveedor,
        tipo_referencia=muestra.tipo_referencia,
        nro_referencia=muestra.nro_referencia,
        fecha_muestreo=muestra.fecha_muestreo,
        usuario_muestreo_nombre=muestra.usuario_muestreo_nombre,
        estado=muestra.estado,
        solicitud=solicitud_info,
        resultados_orden_trabajo=resultados_orden_trabajo,
        envios=envios,
        dictamen=dictamen,
        hay_oos=hay_oos,
        datos_muestreo_pendientes=bool(muestra.datos_muestreo_pendientes),
    )
