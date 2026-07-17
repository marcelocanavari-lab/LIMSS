from pydantic import BaseModel
from datetime import datetime


class RemitoPdfResponse(BaseModel):
    id_remito: int
    id_envio: int
    nro_remito_interno: str
    url_descarga: str
    id_usuario_genera: int
    fecha_generacion: datetime
