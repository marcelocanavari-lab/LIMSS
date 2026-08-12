from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import get_settings
from app.api.routes import auth, maestros, muestras, resultados, dictamenes, materiales, envios, testigos_remitos, erp_config, auditoria, solicitudes_muestreo, erp, dashboard, facturas, integraciones

settings = get_settings()

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


@app.get("/api/health")
def health():
    return {"status": "ok", "app": settings.app_name, "env": settings.app_env}
