from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime

# El detalle para revisión es exactamente el recorrido completo de la muestra
# (todos sus envíos, cada uno con sus propios ensayos/resultados/protocolo) --
# mismo shape que usa Consulta de Muestras, ver app/schemas/recorrido.py.
from app.schemas.recorrido import RecorridoResponse as DictamenDetalleResponse  # noqa: F401


# ── Bandeja de pendientes (REQ-DEC-001) ───────────────────────────

class DictamenPendienteResponse(BaseModel):
    id_muestra: int
    codigo_muestra: str
    erp_CODART: str
    erp_DESART: str
    fecha_muestreo: datetime
    cantidad_envios: int
    cantidad_oos: int


# ── Emisión del dictamen (REQ-DEC-003/004) ────────────────────────

class DictamenCreate(BaseModel):
    estado_dictamen: str = Field(..., pattern=r"^(aprobado|rechazado|cuarentena)$")
    justificacion_oos: Optional[str] = Field(None, max_length=1000)
    observaciones: Optional[str] = Field(None, max_length=500)
    pin_confirmacion: str = Field(..., min_length=4, max_length=6)


class DictamenResponse(BaseModel):
    id_dictamen: int
    id_muestra: int
    estado_dictamen: str
    justificacion_oos: Optional[str] = None
    observaciones: Optional[str] = None
    id_usuario_qa: int
    fecha_dictamen: datetime
