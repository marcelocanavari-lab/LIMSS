from typing import Optional

from pydantic import BaseModel


class SolicitudSinEjecutarItem(BaseModel):
    id_solicitud: int
    nro_solicitud: str
    erp_DESART: str
    muestreador_nombre: Optional[str] = None
    dias_pendiente: int


class MuestreadorActivoItem(BaseModel):
    id_usuario: int
    nombre_completo: str


class DashboardResumenResponse(BaseModel):
    solicitudes_pendientes: int
    muestras_en_proceso: int
    resultados_pendientes: int
    dictamenes_pendientes: int
    # Los testigos por vencer pasaron a GET /api/dashboard/testigos, y las
    # solicitudes sin ejecutar a GET /api/dashboard/solicitudes-pendientes
    # (ambos con filtros interactivos) -- ya no viajan acá.
