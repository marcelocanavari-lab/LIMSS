"""
Agente de detección automática de Informes de Recepción (IR) nuevos en el
ERP GI_LX y generación automática de la Solicitud de Muestreo correspondiente
en LIMSS -- ver migrations_agente_muestreo.sql.

Decisión de arquitectura clave: si corresponde o no muestreo es 100%
determinístico (evaluar_comprobante, sin LLM). Claude (vía API) se usa
ÚNICAMENTE para redactar la justificación en lenguaje claro que se guarda en
lims_agente_log.justificacion -- nunca decide si se crea la solicitud ni
genera SQL, así que una alucinación del modelo no puede terminar creando (o
no creando) una solicitud real. Si la llamada a Claude falla, se cae a una
justificación genérica basada en el resultado ya decidido -- la
disponibilidad de Claude nunca es un punto de falla para el flujo real.
"""
import json
import time
from datetime import date, datetime
from typing import Optional

import pyodbc

from app.api.routes.solicitudes_muestreo import generar_nro_solicitud
from app.core.config import get_settings
from app.db.connections import get_erp_conn, get_limss_conn
from app.services import audit
from app.services.erp_ir import (
    comprobantes_ir_nuevos,
    formatear_nro_ir,
    lineas_comprobante_por_id,
    max_n01id_nuevo,
    normalizar_fecha_sentinel,
    tipo_comprobante_ir,
)

_CLAUDE_MODEL = "claude-sonnet-5"
_REINTENTOS_BACKOFF_SEGUNDOS = (5, 15, 45)

_JUSTIFICACION_GENERICA = {
    "solicitud_generada": "El subartículo requiere muestreo y el material tiene una especificación vigente en LIMSS: se generó la solicitud de muestreo automáticamente.",
    "no_requiere_muestreo": "El subartículo del material está configurado como que no requiere muestreo: no se generó ninguna solicitud.",
    "subarticulo_no_configurado": "El subartículo de este material todavía no está configurado en LIMSS (no se sabe si requiere muestreo): no se generó ninguna solicitud, hace falta cargarlo en Administración.",
    "error": "El subartículo está configurado como que requiere muestreo, pero no se pudo completar la evaluación (falta especificación vigente, o falló la consulta al ERP/LIMSS): hace falta revisión manual.",
}


def _a_datetime(valor):
    """Mismo problema/fix que en solicitudes_muestreo.py -- el driver ODBC no
    puede bindear objetos date, hay que convertirlos a datetime."""
    if valor is None:
        return None
    return datetime.combine(valor, datetime.min.time())


# ── Evaluación determinística (sin LLM) ────────────────────────────────────

def buscar_subarticulo_config(conn: pyodbc.Connection, erp_codsar: Optional[str]):
    if not erp_codsar:
        return None
    cursor = conn.cursor()
    cursor.execute(
        "SELECT * FROM lims_erp_subarticulo_config WHERE erp_codsar = ? AND activo = 1",
        erp_codsar.strip(),
    )
    return cursor.fetchone()


def buscar_especificacion_vigente(conn: pyodbc.Connection, erp_codart: str):
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id_especificacion FROM lims_especificaciones WHERE erp_CODART = ? AND vigente = 1",
        erp_codart.strip(),
    )
    return cursor.fetchone()


def evaluar_comprobante(conn: pyodbc.Connection, erp_codart: str, erp_codsar: Optional[str]) -> dict:
    """resultado en {'solicitud_generada', 'no_requiere_muestreo',
    'subarticulo_no_configurado', 'error'}. 'error' es tanto para fallas
    técnicas como para la anomalía de negocio "el subartículo dice que sí
    pero no hay especificación vigente" -- ver docstring del módulo."""
    config = buscar_subarticulo_config(conn, erp_codsar)
    if config is None:
        return {"resultado": "subarticulo_no_configurado", "id_especificacion": None}
    if not config.requiere_muestreo:
        return {"resultado": "no_requiere_muestreo", "id_especificacion": None}
    especificacion = buscar_especificacion_vigente(conn, erp_codart)
    if especificacion is None:
        return {"resultado": "error", "id_especificacion": None}
    return {"resultado": "solicitud_generada", "id_especificacion": especificacion.id_especificacion}


def _resolver_laboratorio(cursor, id_especificacion: Optional[int]) -> Optional[int]:
    """El laboratorio no viene del ERP -- se resuelve de los ensayos ya
    configurados para la especificación. Si hay exactamente uno, se usa; si
    hay 0 o más de uno, queda NULL para que QA lo complete a mano (ver
    PUT /api/solicitudes-muestreo/{id}/completar-laboratorio)."""
    if id_especificacion is None:
        return None
    cursor.execute(
        "SELECT DISTINCT id_laboratorio FROM lims_especificacion_ensayos WHERE id_especificacion = ?",
        id_especificacion,
    )
    labs = [r.id_laboratorio for r in cursor.fetchall()]
    return labs[0] if len(labs) == 1 else None


# ── Justificación vía Claude (nunca bloqueante) ────────────────────────────

def _justificacion_generica(resultado: str) -> str:
    return _JUSTIFICACION_GENERICA.get(resultado, f"Evaluación automática del agente: resultado = {resultado}.")


def generar_justificacion(resultado: str, datos: dict) -> str:
    """1-2 oraciones en español claro para lims_agente_log.justificacion.
    Cualquier falla (timeout, red, API key inválida, refusal) cae a una
    justificación genérica basada en el resultado ya decidido -- nunca
    bloquea ni retrasa la creación (o no) de la solicitud."""
    settings = get_settings()
    if not settings.anthropic_api_key:
        return _justificacion_generica(resultado)
    try:
        import anthropic

        client = anthropic.Anthropic(api_key=settings.anthropic_api_key, timeout=15.0, max_retries=1)
        prompt = (
            f"Resultado de la evaluación automática de un comprobante de Informe de Recepción (IR) "
            f"del ERP: '{resultado}'.\n"
            f"Datos del comprobante: {json.dumps(datos, default=str, ensure_ascii=False)}\n\n"
            "Redactá una justificación de 1 a 2 oraciones, en español claro y directo, para el "
            "registro de auditoría de un sistema de laboratorio (LIMSS). Explicá en términos del "
            "material y la especificación, no repitas la palabra clave del resultado tal cual. "
            "No agregues nada fuera de esas 1-2 oraciones."
        )
        response = client.messages.create(
            model=_CLAUDE_MODEL,
            max_tokens=300,
            output_config={"effort": "low"},
            messages=[{"role": "user", "content": prompt}],
        )
        if response.stop_reason == "refusal":
            return _justificacion_generica(resultado)
        texto = next((b.text for b in response.content if b.type == "text"), "")
        return texto.strip() or _justificacion_generica(resultado)
    except Exception:
        # Deliberadamente amplio: cualquier falla de Claude (red, auth,
        # timeout, SDK) degrada a la justificación genérica, nunca bloquea.
        return _justificacion_generica(resultado)


# ── Persistencia (lims_agente_control / lims_agente_log) ───────────────────

def _obtener_control(cursor, n01id: int):
    cursor.execute("SELECT * FROM lims_agente_control WHERE id_comprobante_erp = ?", n01id)
    return cursor.fetchone()


def _guardar_control(
    cursor, n01id: int, erp_idm21: Optional[int], erp_codart: Optional[str], erp_codsar: Optional[str],
    resultado: str, id_solicitud_generada: Optional[int], incrementar_reintentos: bool,
) -> int:
    """INSERT si es la primera evaluación de este comprobante, UPDATE si ya
    existía -- así tanto el ciclo de polling normal como el reproceso manual
    (POST .../reprocesar/{id}) usan el mismo camino, y la fila de control
    siempre refleja el último estado (el historial completo queda en
    lims_agente_log, que sí acumula una fila por intento)."""
    existente = _obtener_control(cursor, n01id)
    if existente:
        reintentos = existente.reintentos + 1 if incrementar_reintentos else existente.reintentos
        cursor.execute(
            """
            UPDATE lims_agente_control
            SET erp_idm21 = ?, erp_codart = ?, erp_codsar = ?, fecha_evaluacion = GETDATE(),
                resultado = ?, id_solicitud_generada = ?, reintentos = ?
            WHERE id = ?
            """,
            erp_idm21, erp_codart, erp_codsar, resultado, id_solicitud_generada, reintentos, existente.id,
        )
        return existente.id

    cursor.execute(
        """
        INSERT INTO lims_agente_control
            (id_comprobante_erp, erp_idm21, erp_codart, erp_codsar, resultado, id_solicitud_generada, reintentos)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        n01id, erp_idm21, erp_codart, erp_codsar, resultado, id_solicitud_generada, 1 if incrementar_reintentos else 0,
    )
    cursor.execute("SELECT @@IDENTITY AS id")
    return int(cursor.fetchone().id)


def _registrar_log(cursor, id_control: int, datos_consultados: Optional[dict], decision: str,
                    justificacion: Optional[str], error_detalle: Optional[str]) -> None:
    cursor.execute(
        """
        INSERT INTO lims_agente_log (id_control, datos_consultados, decision, justificacion, error_detalle)
        VALUES (?, ?, ?, ?, ?)
        """,
        id_control,
        json.dumps(datos_consultados, default=str, ensure_ascii=False) if datos_consultados else None,
        decision, justificacion, error_detalle,
    )


def _id_usuario_agente(cursor) -> int:
    cursor.execute("SELECT id_usuario FROM lims_usuarios WHERE codigo = 'AGENTE_IA'")
    row = cursor.fetchone()
    if not row:
        raise RuntimeError("El usuario de sistema AGENTE_IA no existe -- correr migrations_agente_muestreo.sql")
    return row.id_usuario


def _crear_solicitud_desde_agente(cursor, linea, id_especificacion: int, nro_ir_normalizado: str,
                                   id_usuario_agente: int) -> tuple[int, str]:
    """Inserta lims_solicitudes_muestreo directamente (sin pasar por el
    endpoint HTTP de "+ Nueva solicitud"), lo que naturalmente bypassea la
    exigencia de protocolo_proveedor -- este flujo automático no lo tiene
    disponible. Reutiliza generar_nro_solicitud (mismo generador SOL-AAAA-NNN
    que el alta manual) para no duplicar esa lógica."""
    id_laboratorio = _resolver_laboratorio(cursor, id_especificacion)
    nro_solicitud = generar_nro_solicitud(cursor)
    fecha_ingreso = normalizar_fecha_sentinel(linea.FECCOM)
    fecha_vencimiento = normalizar_fecha_sentinel(linea.VENCOM)
    cantidad_ingresada = float(linea.cantidad_total) if linea.cantidad_total is not None else None

    cursor.execute(
        """
        INSERT INTO lims_solicitudes_muestreo
            (nro_solicitud, erp_nro_ir, erp_IdM21, erp_CODART, erp_DESART, id_especificacion,
             id_laboratorio, id_muestreador, estado, id_usuario_qa,
             proveedor_codigo, proveedor_nombre, fecha_ingreso, fecha_vencimiento,
             cantidad_ingresada, unidad_cantidad, origen)
        VALUES (?, ?, ?, ?, ?, ?, ?, NULL, 'pendiente', ?, ?, ?, ?, ?, ?, ?, 'agente')
        """,
        nro_solicitud, nro_ir_normalizado, linea.IdM21, linea.CODART.strip(), linea.DESART, id_especificacion,
        id_laboratorio, id_usuario_agente,
        linea.proveedor_codigo, linea.proveedor, _a_datetime(fecha_ingreso), _a_datetime(fecha_vencimiento),
        cantidad_ingresada, linea.unidad,
    )
    cursor.execute("SELECT @@IDENTITY AS id")
    id_solicitud = int(cursor.fetchone().id)
    return id_solicitud, nro_solicitud


def _procesar_comprobante(limss_conn: pyodbc.Connection, n01id: int, linea) -> str:
    """Evalúa un comprobante ya resuelto (línea del ERP en mano) y registra
    control + log + (si corresponde) la solicitud, todo en la misma
    transacción de get_limss_conn -- si algo falla acá adentro (incluido el
    INSERT de la solicitud), get_limss_conn hace rollback de todo y la
    excepción se propaga para que el llamador reintente; nunca queda
    resultado='solicitud_generada' sin que la solicitud exista de verdad."""
    cursor = limss_conn.cursor()
    id_usuario_agente = _id_usuario_agente(cursor)

    erp_codart = linea.CODART.strip()
    erp_codsar = linea.CODSAR.strip() if linea.CODSAR else None

    evaluacion = evaluar_comprobante(limss_conn, erp_codart, erp_codsar)
    resultado = evaluacion["resultado"]
    id_especificacion = evaluacion["id_especificacion"]

    datos_consultados = {
        "erp_IdM21": linea.IdM21,
        "erp_CODART": erp_codart,
        "erp_CODSAR": erp_codsar,
        "erp_DESART": linea.DESART,
        "erp_nro_ir": formatear_nro_ir(linea.NUMCOMO, linea.FECCOR),
        "proveedor": linea.proveedor,
        "cantidad_total": float(linea.cantidad_total) if linea.cantidad_total is not None else None,
        "unidad": linea.unidad,
    }

    id_solicitud = None
    if resultado == "solicitud_generada":
        id_solicitud, nro_solicitud = _crear_solicitud_desde_agente(
            cursor, linea, id_especificacion, datos_consultados["erp_nro_ir"], id_usuario_agente,
        )
        datos_consultados["nro_solicitud"] = nro_solicitud

    id_control = _guardar_control(
        cursor, n01id, linea.IdM21, erp_codart, erp_codsar, resultado, id_solicitud, incrementar_reintentos=False,
    )

    justificacion = generar_justificacion(resultado, datos_consultados)
    _registrar_log(cursor, id_control, datos_consultados, resultado, justificacion, None)

    audit.registrar(
        limss_conn, entidad="agente_muestreo", accion="evaluar_comprobante",
        id_usuario=id_usuario_agente, id_entidad=id_control,
        valor_nuevo={"id_comprobante_erp": n01id, "resultado": resultado, "id_solicitud_generada": id_solicitud},
    )
    return resultado


def _registrar_error(limss_conn: pyodbc.Connection, n01id: int, error_detalle: str,
                      incrementar_reintentos: bool = False) -> None:
    """Registra un fallo técnico (ERP/LIMSS inalcanzable, comprobante sin
    líneas, etc.) que sobrevivió a los reintentos -- resultado='error', sin
    tocar el resto del batch (ver evaluar_y_registrar_comprobante)."""
    cursor = limss_conn.cursor()
    previo = _obtener_control(cursor, n01id)
    erp_idm21 = previo.erp_idm21 if previo else None
    erp_codart = previo.erp_codart if previo else None
    erp_codsar = previo.erp_codsar if previo else None

    id_control = _guardar_control(
        cursor, n01id, erp_idm21, erp_codart, erp_codsar, "error", None, incrementar_reintentos,
    )
    _registrar_log(cursor, id_control, None, "error", _justificacion_generica("error"), error_detalle)


# ── Ciclo de evaluación por comprobante (con reintentos) ───────────────────

def evaluar_y_registrar_comprobante(n01id: int) -> str:
    """Evalúa un comprobante y registra el resultado, con hasta 3 reintentos
    (backoff 5s/15s/45s) ante fallas de conexión al ERP o a LIMSS. Si sigue
    fallando, queda resultado='error' con el detalle en
    lims_agente_log.error_detalle y se incrementa lims_agente_control.reintentos
    -- nunca levanta una excepción hacia el llamador, así un comprobante que
    falla no frena el resto del batch (ver ciclo_polling). También la usa
    directamente el endpoint de reproceso manual (POST .../reprocesar/{id}),
    que reevalúa aunque el comprobante ya tenga fila en lims_agente_control
    (ver _guardar_control, que hace upsert por id_comprobante_erp)."""
    ultimo_error: Optional[Exception] = None
    for espera in (0, *_REINTENTOS_BACKOFF_SEGUNDOS):
        if espera:
            time.sleep(espera)
        try:
            with get_erp_conn() as erp:
                lineas = lineas_comprobante_por_id(erp, n01id)
            if not lineas:
                with get_limss_conn() as limss:
                    _registrar_error(limss, n01id, f"El comprobante N01Id={n01id} no tiene líneas en el ERP")
                return "error"
            linea = lineas[0]
            with get_limss_conn() as limss:
                return _procesar_comprobante(limss, n01id, linea)
        except Exception as e:  # pyodbc.Error (ERP/LIMSS) u otra falla técnica
            ultimo_error = e

    with get_limss_conn() as limss:
        _registrar_error(limss, n01id, str(ultimo_error), incrementar_reintentos=True)
    return "error"


# ── Ciclo de polling ────────────────────────────────────────────────────────

def _obtener_config(cursor, clave: str) -> str:
    cursor.execute("SELECT valor FROM lims_erp_config WHERE clave = ?", clave)
    row = cursor.fetchone()
    if not row:
        raise RuntimeError(f"Falta el parámetro '{clave}' en lims_erp_config -- correr migrations_agente_muestreo.sql")
    return row.valor


def _actualizar_config(cursor, clave: str, valor: str) -> None:
    cursor.execute("UPDATE lims_erp_config SET valor = ? WHERE clave = ?", valor, clave)


def obtener_polling_minutos() -> int:
    """Se relee en cada ciclo (no se cachea al arrancar el proceso) para que
    un cambio de configuración se aplique sin reiniciar el backend."""
    with get_limss_conn() as limss:
        return int(_obtener_config(limss.cursor(), "agente_muestreo_polling_minutos"))


def _obtener_fecha_inicio(cursor) -> datetime:
    """agente_muestreo_fecha_inicio en lims_erp_config (formato 'YYYY-MM-DD')
    -- comprobantes con FECCOR anterior a esta fecha quedan completamente
    ignorados por el agente (ni se evalúan ni generan fila de control/log),
    para no procesar el historial de antes de que este mecanismo existiera.
    Se relee en cada ciclo, igual que agente_muestreo_polling_minutos."""
    valor = _obtener_config(cursor, "agente_muestreo_fecha_inicio").strip()
    return _a_datetime(date.fromisoformat(valor))


def ciclo_polling() -> dict:
    """Un ciclo completo: busca comprobantes IR nuevos desde la marca de agua
    (agente_muestreo_ultimo_n01id) con FECCOR >= agente_muestreo_fecha_inicio,
    evalúa cada uno y actualiza la marca de agua al final. No es async porque
    pyodbc es bloqueante -- se programa vía APScheduler (BackgroundScheduler,
    hilo propio) para no bloquear el loop de eventos de FastAPI, ver
    app/main.py.

    Los comprobantes con N01Id > ultimo_n01id pero FECCOR anterior a la
    fecha de inicio (históricos, de antes de que el agente existiera) no
    entran en `nuevos` -- no se evalúan, no generan fila en
    lims_agente_control. La marca de agua igual avanza más allá de ellos
    (vía max_n01id_nuevo, que ve el rango completo sin el filtro de fecha)
    para no tener que re-escanearlos en cada ciclo futuro."""
    with get_erp_conn() as erp:
        id_tipo_ir = tipo_comprobante_ir(erp)

    with get_limss_conn() as limss:
        cursor = limss.cursor()
        ultimo_n01id = int(_obtener_config(cursor, "agente_muestreo_ultimo_n01id"))
        fecha_inicio = _obtener_fecha_inicio(cursor)

    with get_erp_conn() as erp:
        nuevos = comprobantes_ir_nuevos(erp, id_tipo_ir, ultimo_n01id, fecha_inicio)
        max_disponible = max_n01id_nuevo(erp, id_tipo_ir, ultimo_n01id)

    max_procesado = max(ultimo_n01id, max_disponible) if max_disponible is not None else ultimo_n01id
    procesados = 0
    for n01id in nuevos:
        with get_limss_conn() as limss:
            ya_evaluado = _obtener_control(limss.cursor(), n01id) is not None
        if not ya_evaluado:
            evaluar_y_registrar_comprobante(n01id)
            procesados += 1

    with get_limss_conn() as limss:
        _actualizar_config(limss.cursor(), "agente_muestreo_ultimo_n01id", str(max_procesado))

    return {"comprobantes_nuevos": len(nuevos), "comprobantes_procesados": procesados, "ultimo_n01id": max_procesado}
