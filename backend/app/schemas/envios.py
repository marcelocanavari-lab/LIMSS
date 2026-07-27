from pydantic import BaseModel
from typing import Optional
from datetime import date, datetime


class RemitoPdfResponse(BaseModel):
    id_remito: int
    id_envio: int
    nro_remito_interno: str
    url_descarga: str
    id_usuario_genera: int
    fecha_generacion: datetime
    # Constancia de recepción (copia firmada por el laboratorio) -- mismo
    # concepto que ya existía para remitos de testigos, ver testigos_remitos.py.
    tiene_copia_firmada: bool = False
    fecha_recepcion: Optional[date] = None
    recibido_por: Optional[str] = None
