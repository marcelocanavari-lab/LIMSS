"""
Esquemas para las evaluaciones del agente de detección automática de IR
(ver app/services/agente_muestreo.py y app/api/routes/integraciones.py --
los endpoints quedan bajo /api/integraciones/agente porque son de uso
interno del equipo, no de terceros, pero conceptualmente son un módulo
aparte de la integración server-to-server con el eBR).
"""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class AgenteLogEntry(BaseModel):
    id: int
    fecha_hora: datetime
    datos_consultados: Optional[dict] = None
    decision: Optional[str] = None
    justificacion: Optional[str] = None
    error_detalle: Optional[str] = None


class AgenteEvaluacion(BaseModel):
    id: int
    id_comprobante_erp: int
    erp_idm21: Optional[int] = None
    erp_codart: Optional[str] = None
    erp_codsar: Optional[str] = None
    fecha_evaluacion: datetime
    resultado: str
    id_solicitud_generada: Optional[int] = None
    nro_solicitud_generada: Optional[str] = None
    reintentos: int
    logs: list[AgenteLogEntry] = []
