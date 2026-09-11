import logging
from datetime import datetime

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.datastructures import MutableHeaders
from app.core.config import get_settings
from app.api.routes import auth, maestros, muestras, resultados, dictamenes, materiales, envios, testigos_remitos, erp_config, auditoria, solicitudes_muestreo, erp, dashboard, facturas, integraciones, cajas, novedades_empaque, empaque_ia, reportes, equipos
from app.services import agente_muestreo

settings = get_settings()
logger = logging.getLogger("agente_muestreo")

# BackgroundScheduler corre en un hilo propio (pyodbc es bloqueante, no se
# puede usar AsyncIOScheduler sin bloquear el loop de eventos de FastAPI).
_ID_JOB_AGENTE = "agente_muestreo_polling"
scheduler = BackgroundScheduler()

app = FastAPI(
    title=settings.app_name,
    description="LIMS Simplificado - Gestión de Análisis Externos - Laboratorio Lamar",
    version="0.1.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Remito-Numero", "X-Remito-Fecha"],
)


class PrivateNetworkAccessMiddleware:
    """Agrega Access-Control-Allow-Private-Network: true a la respuesta de
    cualquier preflight OPTIONS -- caso real: Chrome/Edge (Private Network
    Access) exigen este header, además de los headers CORS normales, cuando
    origen y destino están en una red privada (acá los dos en 192.168.10.99,
    puertos distintos). Sin él, el navegador bloquea la request real
    SILENCIOSAMENTE aunque el preflight responda 200 -- bug real que bloqueó
    "agregar ensayo" en producción, confirmado con el preflight real de
    Chrome (manda Access-Control-Request-Private-Network: true) devolviendo
    200 sin este header. CORSMiddleware de Starlette todavía no lo agrega
    nativamente.

    Tiene que registrarse DESPUÉS de CORSMiddleware (ver más abajo) para
    quedar MÁS AFUERA en la pila de middlewares -- add_middleware inserta al
    principio de la lista, así que el último agregado es el que más afuera
    envuelve al resto. CORSMiddleware corta el request ahí mismo para
    OPTIONS (nunca llega al router) y devuelve su propia respuesta; este
    middleware, por estar afuera, ve esa respuesta de vuelta y solo le suma
    el header, sin duplicar ni reemplazar nada de la lógica CORS ya
    existente (allow_origins/allow_headers/etc. siguen resolviéndose igual
    que antes)."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope["method"] != "OPTIONS":
            await self.app(scope, receive, send)
            return

        async def send_con_header(message):
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                headers.append("Access-Control-Allow-Private-Network", "true")
            await send(message)

        await self.app(scope, receive, send_con_header)


app.add_middleware(PrivateNetworkAccessMiddleware)

# Routers
app.include_router(auth.router)
app.include_router(maestros.router)
app.include_router(muestras.router)
app.include_router(resultados.router)
app.include_router(dictamenes.router)
app.include_router(materiales.router)
app.include_router(envios.router)
app.include_router(testigos_remitos.router)
app.include_router(erp_config.router)
app.include_router(auditoria.router)
app.include_router(solicitudes_muestreo.router)
app.include_router(erp.router)
app.include_router(dashboard.router)
app.include_router(facturas.router)
app.include_router(integraciones.router)
app.include_router(cajas.router)
app.include_router(novedades_empaque.router)
app.include_router(empaque_ia.router)
app.include_router(reportes.router)
app.include_router(equipos.router)


@app.get("/api/health")
def health():
    return {"status": "ok", "app": settings.app_name, "env": settings.app_env}


def _ciclo_polling_agente() -> None:
    """Corre un ciclo y reprograma el próximo con el intervalo vigente en
    lims_erp_config -- se relee acá (no se cachea al arrancar el proceso)
    para que un cambio de configuración se aplique sin reiniciar el backend.
    Loguea inicio/fin y cantidad de comprobantes procesados."""
    logger.info("Ciclo de polling del agente de muestreo: inicio")
    try:
        resultado = agente_muestreo.ciclo_polling()
        logger.info("Ciclo de polling del agente de muestreo: fin -- %s", resultado)
    except Exception:
        logger.exception("Ciclo de polling del agente de muestreo: error")

    try:
        minutos = agente_muestreo.obtener_polling_minutos()
    except Exception:
        logger.exception("No se pudo releer agente_muestreo_polling_minutos, se mantiene el intervalo anterior")
        return
    scheduler.reschedule_job(_ID_JOB_AGENTE, trigger=IntervalTrigger(minutes=minutos))


@app.on_event("startup")
def _iniciar_scheduler_agente():
    try:
        minutos = agente_muestreo.obtener_polling_minutos()
    except Exception:
        logger.exception("No se pudo leer agente_muestreo_polling_minutos -- usando 5 minutos por defecto")
        minutos = 5
    # next_run_time=ahora: el primer ciclo corre al levantar el backend, no
    # recién después de esperar el primer intervalo completo.
    scheduler.add_job(
        _ciclo_polling_agente, trigger=IntervalTrigger(minutes=minutos),
        id=_ID_JOB_AGENTE, replace_existing=True, next_run_time=datetime.now(),
    )
    scheduler.start()
    logger.info("Scheduler del agente de muestreo iniciado (cada %s minutos)", minutos)


@app.on_event("shutdown")
def _detener_scheduler_agente():
    scheduler.shutdown(wait=False)
