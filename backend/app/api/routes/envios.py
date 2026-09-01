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
from types import SimpleNamespace

import pyodbc
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse

from app.core.security import get_current_user, require_rol
from app.db.connections import erp_db, limss_db
from app.schemas.envios import RemitoPdfResponse
from app.services import audit, storage
from app.services.erp_ir import obtener_vencimiento_lote as obtener_vencimiento_ir
from app.services.erp_ir import obtener_vencimiento_por_n01id
from app.services.erp_lotes import obtener_vencimiento_lote_produccion
from app.services.pdf_legajo import paginas_de_adjunto
from app.services.pdf_remito import generar_pdf_remito
from app.api.routes.testigos_remitos import _fecha_envio_real_para_pdf

router = APIRouter(prefix="/api/envios", tags=["Envíos"])


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


_SELECT_DATOS_REMITO = """
    SELECT e.id_envio, e.id_laboratorio, e.fecha_despacho, e.temperatura_transporte, e.nro_remito,
           e.transportista, e.analisis_solicitados, e.protocolo_utilizar,
           m.codigo_muestra, m.tipo_referencia, m.nro_referencia, m.erp_n01id,
           m.erp_CODART, m.erp_DESART, m.fecha_muestreo,
           m.cantidad_enviada, m.unidad_enviada,
           u.nombre + ' ' + u.apellido AS usuario_muestreo_nombre,
           lab.nombre AS laboratorio_nombre, lab.direccion AS laboratorio_direccion,
           lab.contacto AS laboratorio_contacto,
           c.nombre AS contacto_nombre, c.cargo AS contacto_cargo,
           -- Vencimiento confirmado a mano durante el muestreo físico (ver
           -- Ejecutar Muestreo/completar-datos), cuando la muestra viene de
           -- una Solicitud de Muestreo -- puede no haber ninguna
           -- (LEFT JOIN, ver el bug real de más abajo: una muestra creada
           -- por "Nueva Muestra" no tiene solicitud asociada).
           s.fecha_vencimiento_real,
           -- N° de lote del proveedor, cargado en la Solicitud de Muestreo
           -- (completar-datos) -- mismo LEFT JOIN de arriba, puede no haber
           -- ninguna solicitud asociada (muestra creada por "Nueva
           -- Muestra"), en cuyo caso queda NULL y el PDF lo muestra como
           -- "S/L" (mismo criterio ya usado para este campo en
           -- reportes.py/Libro de Ingresos).
           s.lote_proveedor,
           -- Protocolo (COAS) del proveedor, cargado en la Solicitud de
           -- Muestreo antes de que exista ningún envío (ver
           -- subir_protocolo_proveedor en solicitudes_muestreo.py) -- se
           -- adjunta a la copia del remito que va al laboratorio cuando
           -- ese laboratorio lo requiere (ver requiere_coas_proveedor,
           -- consultado aparte más abajo por la misma razón de tolerancia
           -- de columna que sin_vencimiento_confirmado).
           s.protocolo_proveedor_path, s.protocolo_proveedor_nombre_original
    FROM lims_envios e
    INNER JOIN lims_muestras m ON m.id_muestra = e.id_muestra
    INNER JOIN lims_usuarios u ON u.id_usuario = m.id_usuario_muestreo
    INNER JOIN lims_laboratorios lab ON lab.id_laboratorio = e.id_laboratorio
    LEFT JOIN lims_laboratorio_contactos c ON c.id_contacto = e.id_contacto
    LEFT JOIN lims_solicitudes_muestreo s ON s.id_muestra = m.id_muestra
"""


def _obtener_testigos_remito(cursor, id_envio: int, id_laboratorio: int, fecha_envio_default: date):
    """Fecha de envío al laboratorio por testigo: prioriza fecha_envio_real
    (cargada a mano en la asignación testigo-laboratorio, ver
    lims_testigo_laboratorios) y solo cae a fecha_envio_default (el
    despacho de ESTE envío) si no está cargada -- reutiliza
    _fecha_envio_real_para_pdf de testigos_remitos.py (mismo criterio ya
    aplicado ahí) en vez de reimplementar la lógica acá."""
    cursor.execute(
        """
        SELECT t.id_testigo, t.codigo, t.nombre, t.nro_ir, t.nro_lote, t.fecha_vencimiento, t.unidad_medida, et.cantidad
        FROM lims_envio_testigos et
        INNER JOIN lims_testigos t ON t.id_testigo = et.id_testigo
        WHERE et.id_envio = ?
        ORDER BY t.codigo
        """,
        id_envio,
    )
    filas = cursor.fetchall()
    return [
        SimpleNamespace(
            codigo=t.codigo, nombre=t.nombre, nro_ir=t.nro_ir, nro_lote=t.nro_lote,
            fecha_vencimiento=t.fecha_vencimiento, unidad_medida=t.unidad_medida, cantidad=t.cantidad,
            fecha_envio_lab=_fecha_envio_real_para_pdf(cursor, id_laboratorio, [t.id_testigo], fecha_envio_default),
        )
        for t in filas
    ]


def _obtener_ensayos_remito(cursor, id_envio: int):
    cursor.execute(
        """
        SELECT m.nombre_ensayo, se.metodologia, se.tipo_dato, se.limite_inferior, se.limite_superior,
               se.unidad_medida, se.valor_requerido, se.especificacion_texto, se.analito
        FROM lims_envio_ensayos ee
        INNER JOIN lims_especificacion_ensayos se ON se.id_espec_ensayo = ee.id_espec_ensayo
        INNER JOIN lims_ensayos_maestro m ON m.id_ensayo_maestro = se.id_ensayo_maestro
        WHERE ee.id_envio = ?
        ORDER BY se.orden
        """,
        id_envio,
    )
    return cursor.fetchall()


def _tiene_sin_vencimiento_confirmado(cursor, id_envio: int) -> bool:
    """True si la Solicitud de Muestreo de este envío tiene confirmado a
    mano (ver Ejecutar Muestreo) que el material NO tiene vencimiento --
    consulta aparte de _SELECT_DATOS_REMITO (que ya trae fecha_vencimiento_
    real por LEFT JOIN) para poder tolerar que la columna sin_vencimiento_
    confirmado (ver migrations_solicitud_vencimiento_confirmado.sql)
    todavía no exista en este entorno sin romper el SELECT principal por un
    nombre de columna inválido."""
    cursor.execute("SELECT COL_LENGTH('lims_solicitudes_muestreo', 'sin_vencimiento_confirmado') AS c")
    if cursor.fetchone().c is None:
        return False
    cursor.execute(
        """
        SELECT s.sin_vencimiento_confirmado
        FROM lims_envios e
        INNER JOIN lims_muestras m ON m.id_muestra = e.id_muestra
        INNER JOIN lims_solicitudes_muestreo s ON s.id_muestra = m.id_muestra
        WHERE e.id_envio = ?
        """,
        id_envio,
    )
    fila = cursor.fetchone()
    return bool(fila.sin_vencimiento_confirmado) if fila else False


def _laboratorio_requiere_coas(cursor, id_laboratorio: int) -> bool:
    """True si el laboratorio destino tiene tildado "Requiere COAS del
    proveedor" -- mismo criterio de tolerancia de columna que
    _tiene_sin_vencimiento_confirmado (ver migrations_laboratorio_requiere_
    coas.sql, columna nueva que puede no existir todavía en este entorno)."""
    cursor.execute("SELECT COL_LENGTH('lims_laboratorios', 'requiere_coas_proveedor') AS c")
    if cursor.fetchone().c is None:
        return False
    cursor.execute(
        "SELECT requiere_coas_proveedor FROM lims_laboratorios WHERE id_laboratorio = ?",
        id_laboratorio,
    )
    fila = cursor.fetchone()
    return bool(fila.requiere_coas_proveedor) if fila else False


def _fila_a_remito_pdf(fila) -> RemitoPdfResponse:
    return RemitoPdfResponse(
        id_remito=fila.id_remito,
        id_envio=fila.id_envio,
        nro_remito_interno=fila.nro_remito_interno,
        # Apunta a ESTE remito puntual (ver descargar_remito_por_id más
        # abajo), no al "más reciente" del envío -- así un documento del
        # historial (ver listar_remitos) siempre baja a sí mismo, nunca a
        # otro que haya sido generado después.
        url_descarga=f"/api/envios/remitos/{fila.id_remito}",
        id_usuario_genera=fila.id_usuario,
        fecha_generacion=fila.fecha_generacion,
        tiene_copia_firmada=bool(fila.pdf_copia_firmada),
        fecha_recepcion=_a_fecha(fila.fecha_recepcion),
        recibido_por=fila.recibido_por,
    )


@router.post("/{id_envio}/remito", response_model=RemitoPdfResponse, status_code=201)
def generar_remito(
    id_envio: int,
    user: dict = Depends(require_rol("analista_qc", "qa", "admin")),
    conn: pyodbc.Connection = Depends(limss_db),
    erp: pyodbc.Connection = Depends(erp_db),
):
    cursor = conn.cursor()
    cursor.execute(_SELECT_DATOS_REMITO + " WHERE e.id_envio = ?", id_envio)
    datos = cursor.fetchone()
    if not datos:
        raise HTTPException(status_code=404, detail="Envío no encontrado")

    ensayos = _obtener_ensayos_remito(cursor, id_envio)
    testigos = _obtener_testigos_remito(cursor, id_envio, datos.id_laboratorio, datos.fecha_despacho)

    # Prioriza fecha_vencimiento_real (cargada a mano en la Solicitud de
    # Muestreo al ejecutar el muestreo físico -- ver completar-datos/
    # orden-trabajo-digital) sobre la consulta en vivo al ERP, mismo
    # criterio que _fecha_envio_real_para_pdf ya aplica para testigos en
    # este mismo módulo. Bug real detectado en producción: el ERP puede no
    # tener vencimiento cargado para un comprobante (VENCOM = sentinel
    # 1899-12-30) mientras que el vencimiento real del lote sí se confirmó
    # a mano durante el muestreo -- antes ese dato cargado quedaba
    # completamente ignorado porque _SELECT_DATOS_REMITO nunca hacía join
    # con lims_solicitudes_muestreo. Solo se cae a la consulta ERP cuando no
    # hay ese dato confirmado (p.ej. una muestra creada por "Nueva Muestra",
    # sin Solicitud de Muestreo asociada).
    #
    # Si la persona confirmó explícitamente en Ejecutar Muestreo que el
    # material NO tiene vencimiento (ver migrations_solicitud_vencimiento_
    # confirmado.sql / sin_vencimiento_confirmado), eso es definitivo -- no
    # se vuelve a consultar el ERP encima de una confirmación humana real.
    sin_vencimiento_confirmado = _tiene_sin_vencimiento_confirmado(cursor, datos.id_envio)
    vencimiento_lote = _a_fecha(datos.fecha_vencimiento_real) if datos.fecha_vencimiento_real else None
    if vencimiento_lote is None and not sin_vencimiento_confirmado:
        try:
            if datos.tipo_referencia == "ir":
                # erp_n01id ya resuelto (ver investigación de colisiones de
                # NUMCOMO+año) -- se usa directo en vez de volver a resolver
                # datos.nro_referencia por texto, así una colisión que aparezca
                # después para el mismo IR no puede traer el comprobante
                # equivocado. Sin erp_n01id (muestras creadas antes de este
                # campo) se cae al camino de siempre.
                if datos.erp_n01id is not None:
                    vencimiento_lote = obtener_vencimiento_por_n01id(erp, datos.erp_n01id)
                else:
                    vencimiento_lote = obtener_vencimiento_ir(erp, datos.nro_referencia)
            else:
                vencimiento_lote = obtener_vencimiento_lote_produccion(erp, datos.nro_referencia)
        except Exception:
            vencimiento_lote = None

    anio = date.today().year
    cursor.execute(
        "SELECT MAX(nro_remito_interno) AS ultimo FROM lims_remitos WHERE nro_remito_interno LIKE ?",
        f"REM-{anio}-%",
    )
    ultimo = cursor.fetchone().ultimo
    correlativo = int(ultimo.split("-")[-1]) + 1 if ultimo else 1
    nro_remito_interno = f"REM-{anio}-{correlativo:04d}"

    # COAS del proveedor: si el laboratorio lo requiere y la solicitud lo
    # tiene cargado, se adjunta a la copia ORIGINAL (para el laboratorio) --
    # ver generar_pdf_remito. Si el laboratorio lo requiere pero no está
    # cargado, no se bloquea acá: el aviso de confirmación es responsabilidad
    # del frontend (mismo patrón que el aviso de vencimiento sin confirmar),
    # así que el remito se genera igual, sin adjunto.
    paginas_protocolo_proveedor = None
    if _laboratorio_requiere_coas(cursor, datos.id_laboratorio) and datos.protocolo_proveedor_path:
        paginas_protocolo_proveedor = paginas_de_adjunto(storage.ruta_absoluta(datos.protocolo_proveedor_path))

    pdf_bytes = generar_pdf_remito(
        datos, nro_remito_interno, ensayos, testigos, vencimiento_lote,
        paginas_protocolo_proveedor=paginas_protocolo_proveedor,
    )
    ruta_pdf = storage.guardar_pdf_remito(pdf_bytes, nro_remito_interno)

    cursor.execute(
        """
        INSERT INTO lims_remitos (id_envio, nro_remito_interno, pdf_path, id_usuario)
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


@router.get("/{id_envio}/remitos", response_model=list[RemitoPdfResponse])
def listar_remitos(
    id_envio: int,
    user: dict = Depends(get_current_user),
    conn: pyodbc.Connection = Depends(limss_db),
):
    """Historial COMPLETO de remitos generados para este envío -- el
    mecanismo sigue siendo append-only (ver el docstring del módulo, arriba
    de todo): "Generar uno nuevo" siempre crea un documento adicional,
    nunca sobrescribe uno existente. Hasta ahora solo se exponía el más
    reciente (ver descargar_remito), lo que podía llevar a que alguien
    corrigiera un dato en la base, mirara/descargara el remito de antes de
    la corrección sin darse cuenta de que no la tiene, y no supiera que
    hacía falta generar uno nuevo para que quedara reflejada en un
    documento. Este endpoint expone la lista entera, más reciente primero
    (el frontend lo destaca como "vigente"), para que quede claro de un
    vistazo cuándo se generó cada versión."""
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM lims_remitos WHERE id_envio = ? ORDER BY id_remito DESC", id_envio)
    return [_fila_a_remito_pdf(f) for f in cursor.fetchall()]


@router.get("/remitos/{id_remito}")
def descargar_remito_por_id(
    id_remito: int,
    user: dict = Depends(get_current_user),
    conn: pyodbc.Connection = Depends(limss_db),
):
    """Descarga un remito PUNTUAL del historial (ver listar_remitos), a
    diferencia de descargar_remito (GET /{id_envio}/remito) que siempre
    sirve el más reciente -- necesario para poder abrir/descargar cualquier
    versión anterior, no solo la vigente."""
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM lims_remitos WHERE id_remito = ?", id_remito)
    fila = cursor.fetchone()
    if not fila:
        raise HTTPException(status_code=404, detail="Remito no encontrado")

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


# ── Constancia de recepción (copia firmada por el laboratorio) ──────
#
# Mismo concepto y mismo patrón que ya existía para remitos de testigos
# (ver testigos_remitos.py: adjuntar_copia_firmada/descargar_copia_firmada),
# replicado acá para el remito de muestra. Como lims_remitos es append-only
# (puede haber varias filas por envío), la recepción se aplica siempre sobre
# la más reciente -- mismo criterio que descargar_remito de arriba.

@router.post("/{id_envio}/remito/copia-firmada", response_model=RemitoPdfResponse)
def adjuntar_copia_firmada(
    id_envio: int,
    fecha_recepcion: date = Form(...),
    recibido_por: str = Form(..., min_length=1, max_length=100),
    pdf_copia_firmada: UploadFile = File(...),
    user: dict = Depends(require_rol("analista_qc", "qa", "admin")),
    conn: pyodbc.Connection = Depends(limss_db),
):
    """Se puede llamar de nuevo sobre el mismo remito para reemplazar la
    copia ya adjunta (sube un archivo nuevo, pisa los datos)."""
    cursor = conn.cursor()
    cursor.execute(
        "SELECT TOP 1 * FROM lims_remitos WHERE id_envio = ? ORDER BY id_remito DESC",
        id_envio,
    )
    fila = cursor.fetchone()
    if not fila:
        raise HTTPException(status_code=404, detail="Todavía no se generó un remito para este envío")

    tenia_copia = bool(fila.pdf_copia_firmada)
    ruta_pdf = storage.guardar_pdf_copia_firmada(pdf_copia_firmada, fila.nro_remito_interno)

    cursor.execute(
        """
        UPDATE lims_remitos
        SET pdf_copia_firmada = ?, fecha_recepcion = ?, recibido_por = ?
        WHERE id_remito = ?
        """,
        ruta_pdf, str(fecha_recepcion), recibido_por, fila.id_remito,
    )

    audit.registrar(
        conn, entidad="remito", accion="reemplazar_copia_firmada" if tenia_copia else "adjuntar_copia_firmada",
        id_usuario=user["id_usuario"], id_entidad=fila.id_remito,
        valor_nuevo={"fecha_recepcion": str(fecha_recepcion), "recibido_por": recibido_por},
    )

    cursor.execute("SELECT * FROM lims_remitos WHERE id_remito = ?", fila.id_remito)
    return _fila_a_remito_pdf(cursor.fetchone())


@router.get("/{id_envio}/remito/copia-firmada")
def descargar_copia_firmada(
    id_envio: int,
    user: dict = Depends(get_current_user),
    conn: pyodbc.Connection = Depends(limss_db),
):
    cursor = conn.cursor()
    cursor.execute(
        "SELECT TOP 1 nro_remito_interno, pdf_copia_firmada FROM lims_remitos WHERE id_envio = ? ORDER BY id_remito DESC",
        id_envio,
    )
    fila = cursor.fetchone()
    if not fila or not fila.pdf_copia_firmada:
        raise HTTPException(status_code=404, detail="Este remito no tiene copia firmada adjunta")

    ruta = storage.ruta_absoluta(fila.pdf_copia_firmada)
    if not os.path.exists(ruta):
        raise HTTPException(status_code=404, detail="El archivo no se encuentra en el servidor")

    return FileResponse(
        ruta, media_type="application/pdf",
        filename=f"LIMSS_{fila.nro_remito_interno}_FIRMADO.pdf",
    )
