from pydantic import BaseModel, Field
from typing import Optional
from datetime import date, datetime


class MuestreadorDisponible(BaseModel):
    id_usuario: int
    nombre_completo: str


class MuestraConfirmadaInput(BaseModel):
    """Una fila de la tabla "Muestras a tomar" del formulario de nueva
    solicitud -- ver lims_solicitud_muestras. cantidad_real puede diferir de
    lims_especificacion_muestras.cantidad si el usuario la ajustó."""
    id_espec_muestra: int
    cantidad_real: float = Field(..., gt=0)
    confirmada: bool = True


class SolicitudMuestreoCreate(BaseModel):
    erp_nro_ir: str = Field(..., min_length=1, max_length=20)
    id_laboratorio: int
    id_muestreador: int
    observaciones: Optional[str] = Field(None, max_length=500)
    # Proveedor: lo elige QA con el buscador contra el ERP (GET /api/erp/
    # proveedores) -- ya NO se toma automáticamente del renglón del IR,
    # porque un mismo IR puede tener el proveedor mal cargado en el ERP.
    proveedor_codigo: str = Field(..., min_length=1, max_length=20)
    proveedor_nombre: str = Field(..., min_length=1, max_length=150)
    # Datos manuales del ingreso -- no vienen del ERP (ver P_CC002-1/2).
    lote_proveedor: str = Field(..., min_length=1, max_length=20)
    # Se precarga en el frontend con el VENCOM del ERP al buscar el IR, pero
    # el usuario la puede corregir antes de confirmar -- si no manda nada,
    # se usa el valor del ERP como antes (ver crear_solicitud).
    fecha_vencimiento: Optional[date] = None
    fecha_reanalisis: Optional[date] = None
    pais_origen: Optional[str] = Field(None, max_length=100)
    nro_bultos: Optional[int] = None
    metodologia_analisis: Optional[str] = Field(None, max_length=200)
    fabricante: Optional[str] = Field(None, max_length=200)
    # Confirmación de la tabla "Muestras a tomar" (lims_especificacion_
    # muestras de la especificación resuelta) -- ver lims_solicitud_muestras.
    muestras: list[MuestraConfirmadaInput] = []


class SolicitudMuestreoResponse(BaseModel):
    id_solicitud: int
    nro_solicitud: str
    erp_nro_ir: str
    erp_CODART: str
    erp_DESART: str
    # NULL en solicitudes generadas por el agente cuando la especificación
    # tiene 0 o más de un laboratorio posible (ver evaluar_comprobante en
    # app/services/agente_muestreo.py) -- QA la completa a mano con PUT
    # .../completar-laboratorio antes de poder ejecutar el muestreo.
    id_laboratorio: Optional[int] = None
    laboratorio_nombre: Optional[str] = None
    id_muestreador: Optional[int] = None
    muestreador_nombre: Optional[str] = None
    estado: str
    fecha_solicitud: datetime
    usuario_qa: str
    id_muestra: Optional[int] = None
    observaciones: Optional[str] = None
    # Traídos del ERP al crear la solicitud (ver POST) -- quedan fijos en la
    # solicitud aunque el dato cambie después en el ERP.
    proveedor_codigo: Optional[str] = None
    proveedor_nombre: Optional[str] = None
    fecha_ingreso: Optional[date] = None
    fecha_vencimiento: Optional[date] = None
    cantidad_ingresada: Optional[float] = None
    unidad_cantidad: Optional[str] = None
    # Cargados a mano por QA al crear la solicitud.
    lote_proveedor: Optional[str] = None
    fecha_reanalisis: Optional[date] = None
    pais_origen: Optional[str] = None
    nro_bultos: Optional[int] = None
    metodologia_analisis: Optional[str] = None
    fabricante: Optional[str] = None
    # Datos físicos cargados por el muestreador al ejecutar (Etapa 2), NULL
    # hasta entonces -- nunca incluyen resultados de ensayos, eso lo carga
    # QC/QA por el flujo de Envío.
    aspecto_externo: Optional[str] = None
    cierre: Optional[str] = None
    aspecto_interno: Optional[str] = None
    precintos: Optional[str] = None
    materias_extranas: Optional[str] = None
    olor: Optional[str] = None
    color: Optional[str] = None
    nro_bultos_muestreados: Optional[int] = None
    observaciones_muestreo: Optional[str] = None
    # Campos agregados en migrations_solicitudes_muestreo_datos_fisicos_v2.sql
    # (pendiente de ejecutar en algunos entornos) -- el backend los lee con
    # getattr/default None (ver _g en routes/solicitudes_muestreo.py) para no
    # romper el resto del módulo si todavía no existen en la BD real.
    identificacion_contenedor: Optional[str] = None
    fecha_vencimiento_real: Optional[date] = None
    fecha_reanalisis_real: Optional[date] = None
    aspecto_mp: Optional[str] = None
    # Protocolo que entrega el PROVEEDOR junto con el lote (foto o PDF),
    # adjuntado obligatoriamente por QA al crear la solicitud -- no confundir
    # con el protocolo del laboratorio de análisis (lims_protocolos, ligado a
    # un envío). Solo se expone el nombre original acá; el archivo se sirve
    # por GET /{id_solicitud}/protocolo-proveedor.
    protocolo_proveedor_nombre_original: Optional[str] = None
    # Documentación del proveedor (remito y/o factura, un solo archivo) --
    # a diferencia del protocolo, es OPCIONAL y se puede adjuntar en el
    # momento de crear la solicitud o después. None = todavía pendiente.
    # El archivo se sirve por GET /{id_solicitud}/documentacion-proveedor.
    documentacion_proveedor_nombre_original: Optional[str] = None
    # 'manual' (QA la crea desde "+ Nueva solicitud") o 'agente' (generada
    # automáticamente al detectar un IR nuevo -- ver app/services/agente_muestreo.py).
    origen: str = "manual"


class SolicitudMuestreoCompletar(BaseModel):
    """Completa id_laboratorio y/o id_muestreador en una solicitud
    'pendiente' que quedó sin alguno de los dos -- pensado para las que
    generó el agente (ver SolicitudMuestreoResponse.origen), que puede
    dejarlos en blanco cuando la especificación no resuelve un único
    laboratorio o para que QA elija quién muestrea."""
    id_laboratorio: Optional[int] = None
    id_muestreador: Optional[int] = None


class EnsayoSolicitudMuestreo(BaseModel):
    id_espec_ensayo: int
    orden: int
    nombre_ensayo: str
    metodologia: Optional[str] = None
    tipo_dato: str
    limite_inferior: Optional[float] = None
    limite_superior: Optional[float] = None
    unidad_medida: Optional[str] = None
    valor_requerido: Optional[str] = None
    especificacion_texto: Optional[str] = None
    obligatorio: bool = False
    # Resultado ya cargado en la Orden de Trabajo digital, si lo hay (None =
    # todavía no se confirmó el muestreo para esta solicitud).
    valor_numerico: Optional[float] = None
    valor_cualitativo: Optional[str] = None
    dentro_especificacion: Optional[bool] = None


class SolicitudMuestreoDetalle(SolicitudMuestreoResponse):
    erp_IdM21: int
    id_especificacion: Optional[int] = None
    cantidad_muestra: Optional[float] = None
    unidad_muestra: Optional[str] = None
    cantidad_contramuestra: Optional[float] = None
    unidad_contramuestra: Optional[str] = None
    ensayos: list[EnsayoSolicitudMuestreo]


class SolicitudMuestreoAnular(BaseModel):
    motivo: str = Field(..., min_length=1, max_length=300)


# ── Orden de Trabajo digital (Etapa 2: el muestreador ejecuta) ────
#
# Solo datos físicos observables del muestreo -- el muestreador nunca carga
# resultados de ensayos, eso lo hace QC/QA más adelante por envío (Carga de
# Resultados). Al confirmar, la muestra se crea automáticamente en estado
# 'pendiente_envio', sin excepción; QC/QA sigue el flujo normal de Envío
# para despachar al laboratorio.

class DatosFisicosMuestreo(BaseModel):
    aspecto_externo: Optional[str] = Field(None, max_length=200)
    cierre: Optional[str] = Field(None, max_length=200)
    aspecto_interno: Optional[str] = Field(None, max_length=200)
    precintos: Optional[str] = Field(None, max_length=200)
    identificacion_contenedor: Optional[str] = Field(None, max_length=200)
    fecha_vencimiento_real: Optional[date] = None
    fecha_reanalisis_real: Optional[date] = None
    aspecto_mp: Optional[str] = Field(None, max_length=200)
    materias_extranas: Optional[str] = Field(None, max_length=200)
    olor: Optional[str] = Field(None, max_length=200)
    color: Optional[str] = Field(None, max_length=200)
    observaciones_muestreo: Optional[str] = Field(None, max_length=500)
    nro_bultos_muestreados: Optional[int] = None


class EnsayosParaOrdenResponse(BaseModel):
    id_solicitud: int
    nro_solicitud: str
    erp_CODART: str
    erp_DESART: str
    estado: str
    datos_fisicos: DatosFisicosMuestreo


class OrdenTrabajoDigitalBody(BaseModel):
    datos_fisicos: DatosFisicosMuestreo


class OrdenTrabajoDigitalResponse(BaseModel):
    id_solicitud: int
    id_muestra: int
    codigo_muestra: str
