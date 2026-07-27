"""
Agregación compartida "muestra + todos sus envíos + resultados + dictamen".
Ver app/schemas/recorrido.py para el detalle de las respuestas.
"""
from typing import Optional

from app.schemas.recorrido import (
    DictamenInfo,
    EnsayoResultado,
    EnvioDetalleInfo,
    ProtocoloEnvioInfo,
    RecorridoResponse,
    TestigoEnvioInfo,
)


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
        "SELECT id_envio, id_laboratorio, fecha_despacho, nro_remito FROM lims_envios WHERE id_muestra = ? ORDER BY id_envio",
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

        envios.append(EnvioDetalleInfo(
            id_envio=e.id_envio,
            laboratorio_nombre=lab.nombre if lab else "—",
            fecha_despacho=e.fecha_despacho,
            nro_remito=e.nro_remito,
            testigos=testigos,
            protocolo=protocolo,
            ensayos=ensayos,
            completo=completo,
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
        tipo_referencia=muestra.tipo_referencia,
        nro_referencia=muestra.nro_referencia,
        fecha_muestreo=muestra.fecha_muestreo,
        usuario_muestreo_nombre=muestra.usuario_muestreo_nombre,
        estado=muestra.estado,
        envios=envios,
        dictamen=dictamen,
        hay_oos=hay_oos,
    )
