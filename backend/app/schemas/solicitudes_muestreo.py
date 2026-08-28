from pydantic import BaseModel, Field, model_validator
from typing import Optional
from datetime import date, datetime


class MuestreadorDisponible(BaseModel):
    id_usuario: int
    nombre_completo: str


class UsuarioDisponible(BaseModel):
    """Igual forma que MuestreadorDisponible pero sin filtrar por rol --
    "quién recibió"/"quién rotuló" (ver OrdenTrabajoDigitalBody) puede ser
    cualquier usuario activo, no solo los de rol 'muestreador'."""
    id_usuario: int
    nombre_completo: str


class BultoGrupoInput(BaseModel):
    """Un grupo de bultos (cantidad de bultos x cantidad de unidades cada
    uno -- ver lims_solicitud_bultos), cargado en el formulario de crear o
    completar una Solicitud de Muestreo. Ejemplo real: "4 x 50 kg" + "1 x 30
    kg" -- dos grupos, cada uno imprime esa cantidad de etiquetas
    CUARENTENA/APROBADO/RECHAZADO con SU cantidad_unidades particular (ver
    app/services/bultos.py)."""
    cantidad_bultos: int = Field(..., gt=0)
    cantidad_unidades: float = Field(..., gt=0)
    unidad_medida: Optional[str] = Field(None, max_length=20)


class BultoGrupoResponse(BultoGrupoInput):
    id_bulto_grupo: int


class MuestraConfirmadaInput(BaseModel):
    """Una fila de la tabla "Muestras a tomar", confirmada al Ejecutar
    Muestreo (Orden de Trabajo digital) -- ver lims_solicitud_muestras.
    cantidad_real puede diferir de lims_especificacion_muestras.cantidad si
    el usuario la ajustó.

    Dos formas:
    - Estándar (viene de la especificación): id_espec_muestra con valor,
      tipo_muestra/unidad en None -- se toman de la especificación al
      guardar (ver confirmar_orden_trabajo).
    - Ad-hoc (agregada a mano para esta solicitud puntual, no está en la
      especificación del producto): id_espec_muestra=None, tipo_muestra y
      unidad SÍ tienen que venir. No modifica la especificación -- queda
      asociada solo a esta solicitud/muestra."""
    id_espec_muestra: Optional[int] = None
    tipo_muestra: Optional[str] = Field(None, pattern=r"^(analisis|contramuestra|testigo)$")
    unidad: Optional[str] = Field(None, max_length=20)
    cantidad_real: float = Field(..., gt=0)
    confirmada: bool = True

    @model_validator(mode="after")
    def _validar_ad_hoc(self):
        if self.id_espec_muestra is None and not (self.tipo_muestra and self.unidad):
            raise ValueError("Una muestra ad-hoc (sin id_espec_muestra) necesita indicar tipo_muestra y unidad")
        return self


class SolicitudMuestreoCreate(BaseModel):
    erp_nro_ir: str = Field(..., min_length=1, max_length=20)
    # N01Id del comprobante ya resuelto por el frontend (ver búsqueda previa,
    # GET /api/muestras/buscar-material) -- si viene, crear_solicitud lo usa
    # directo (lineas_comprobante_por_id) en vez de volver a resolver
    # erp_nro_ir por texto, así que una colisión de (NUMCOMO, año) no puede
    # traer el comprobante equivocado. None = comportamiento de siempre
    # (buscar_lineas_ir resuelve por texto) -- válido solo cuando no hay
    # colisión, que es el caso normal.
    erp_n01id: Optional[int] = None
    id_laboratorio: int
    id_muestreador: int
    observaciones: Optional[str] = Field(None, max_length=500)
    # Proveedor: lo elige QA con el buscador contra el ERP (GET /api/erp/
    # proveedores) -- ya NO se toma automáticamente del renglón del IR,
    # porque un mismo IR puede tener el proveedor mal cargado en el ERP.
    proveedor_codigo: str = Field(..., min_length=1, max_length=20)
    proveedor_nombre: str = Field(..., min_length=1, max_length=150)
    # Datos manuales del ingreso -- no vienen del ERP (ver P_CC002-1/2).
    # Opcional a nivel de schema porque Material de Empaque sin codificar
    # (GIT59SAR.CODSAR '0006') no lo exige -- crear_solicitud valida que
    # venga completo para cualquier otro subartículo (ver ese endpoint).
    lote_proveedor: Optional[str] = Field(None, max_length=20)
    # Se precarga en el frontend con el VENCOM del ERP al buscar el IR, pero
    # el usuario la puede corregir antes de confirmar -- si no manda nada,
    # se usa el valor del ERP como antes (ver crear_solicitud).
    fecha_vencimiento: Optional[date] = None
    fecha_reanalisis: Optional[date] = None
    pais_origen: Optional[str] = Field(None, max_length=100)
    nro_bultos: Optional[int] = None
    # Grupos de bultos (opcional) -- si viene con al menos un grupo, nro_bultos
    # de arriba se ignora y se recalcula solo como la suma de cantidad_bultos
    # de todos los grupos (ver crear_solicitud). Sin grupos, se sigue usando
    # nro_bultos tal cual (caso simple, compatibilidad con lo de siempre).
    grupos_bultos: list[BultoGrupoInput] = []
    metodologia_analisis: Optional[str] = Field(None, max_length=200)
    fabricante: Optional[str] = Field(None, max_length=200)
    # Si ya existe una solicitud activa (no anulada) para este mismo IR,
    # crear_solicitud devuelve 409 con los datos de esa solicitud en vez de
    # crear -- a menos que venga en True, que es como el frontend confirma
    # que la persona vio ese aviso y quiere generar una nueva de todas
    # formas (ej. análisis adicionales pedidos después). Solo aplica a la
    # creación MANUAL -- el agente automático nunca genera un duplicado, ver
    # solicitud_activa_existente en app/services/erp_ir.py.
    confirmar_duplicado_ir: bool = False
    # La confirmación de la tabla "Muestras a tomar" se movió a Ejecutar
    # Muestreo (OrdenTrabajoDigitalBody.muestras, más abajo) -- antes se
    # pedía acá, al crear, pero eso dejaba a las solicitudes del agente sin
    # este paso (el agente nunca pasa por este formulario). Ahora es un
    # solo lugar para los dos orígenes, justo antes de generar la muestra.


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
    grupos_bultos: list[BultoGrupoResponse] = []
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
    # N01Id del comprobante ya resuelto (ver SolicitudMuestreoCreate.erp_n01id)
    # -- None en solicitudes creadas antes de este campo.
    erp_n01id: Optional[int] = None
    # Recepción del proveedor (Libro de Ingresos) -- cargados por QA al
    # completar la solicitud (ver SolicitudMuestreoCompletar/completar_datos,
    # movidos ahí desde Ejecutar Muestreo). Se exponen acá para que el
    # formulario de "Completar" pueda precargarlos si ya se habían cargado
    # en una llamada anterior, mismo criterio que lote_proveedor/pais_origen.
    fecha_factura_proveedor: Optional[date] = None
    numero_factura_proveedor: Optional[str] = None
    id_usuario_recibio: Optional[int] = None
    id_usuario_rotulo: Optional[int] = None


class SolicitudMuestreoCompletar(BaseModel):
    """Completa los datos que una solicitud generada por el agente (ver
    SolicitudMuestreoResponse.origen) no puede resolver solo con el ERP --
    laboratorio/muestreador (el agente los deja en blanco a propósito, ver
    app/services/agente_muestreo.py) y los datos manuales del ingreso que en
    el alta manual carga QA a mano (lote del proveedor, país de origen,
    fecha de reanálisis, bultos, metodología, fabricante). Solo toca los
    campos que vengan con valor -- si un campo no se manda, se conserva el
    que ya tenía la solicitud."""
    id_laboratorio: Optional[int] = None
    id_muestreador: Optional[int] = None
    lote_proveedor: Optional[str] = Field(None, min_length=1, max_length=20)
    fecha_reanalisis: Optional[date] = None
    pais_origen: Optional[str] = Field(None, max_length=100)
    nro_bultos: Optional[int] = None
    # Igual que en SolicitudMuestreoCreate: con al menos un grupo, reemplaza
    # los grupos existentes de la solicitud (no acumula) y recalcula
    # nro_bultos como la suma. Lista vacía (default) = no tocar los grupos
    # ya cargados, mismo criterio "solo lo que venga con valor" del resto de
    # este schema.
    grupos_bultos: list[BultoGrupoInput] = []
    metodologia_analisis: Optional[str] = Field(None, max_length=200)
    fabricante: Optional[str] = Field(None, max_length=200)
    # Datos de recepción del proveedor (Libro de Ingresos) -- movidos acá
    # desde OrdenTrabajoDigitalBody (Ejecutar Muestreo): el muestreador no
    # maneja la factura del proveedor ni sabe quién recibió/rotuló
    # administrativamente el ingreso, es información que maneja QA, mismo
    # momento que el resto de los datos manuales de este schema.
    fecha_factura_proveedor: Optional[date] = None
    numero_factura_proveedor: Optional[str] = Field(None, max_length=50)
    id_usuario_recibio: Optional[int] = None
    id_usuario_rotulo: Optional[int] = None


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
    # Distingue "el muestreador todavía no revisó el vencimiento" (ambos en
    # False/None) de "revisó el envase y confirmó que este material
    # genuinamente no tiene vencimiento" -- antes fecha_vencimiento_real en
    # NULL representaba las dos situaciones por igual, así que quedaba
    # cargado solo cuando alguien se acordaba de hacerlo a mano, sin ninguna
    # exigencia real de revisarlo (ver confirmar_orden_trabajo, que ahora
    # exige uno de los dos si la especificación está resuelta contra un IR).
    sin_vencimiento_confirmado: bool = False
    fecha_reanalisis_real: Optional[date] = None
    aspecto_mp: Optional[str] = Field(None, max_length=200)
    materias_extranas: Optional[str] = Field(None, max_length=200)
    olor: Optional[str] = Field(None, max_length=200)
    color: Optional[str] = Field(None, max_length=200)
    observaciones_muestreo: Optional[str] = Field(None, max_length=500)
    nro_bultos_muestreados: Optional[int] = None


class ChecklistMuestreoItem(BaseModel):
    """Ítem del checklist físico de muestreo (etapa='muestreo' en
    lims_especificacion_ensayos), configurable por especificación -- ver
    lims_resultados_muestreo. Reemplaza al set fijo de 4 campos
    (aspecto_externo/cierre/aspecto_interno/precintos) para solicitudes
    ejecutadas de acá en adelante."""
    id_espec_ensayo: int
    orden: int
    nombre_ensayo: str
    especificacion_texto: Optional[str] = None
    # Respuesta ya cargada, si la solicitud ya fue ejecutada (None = todavía
    # no se confirmó el muestreo).
    valor_cualitativo: Optional[str] = None


class ChecklistMuestreoRespuesta(BaseModel):
    id_espec_ensayo: int
    valor_cualitativo: str = Field(..., min_length=1, max_length=20)


class EnsayosParaOrdenResponse(BaseModel):
    id_solicitud: int
    nro_solicitud: str
    erp_CODART: str
    erp_DESART: str
    estado: str
    # Para que el frontend pueda pedir las muestras definidas en la
    # especificación (GET /api/maestros/especificaciones/{id}/muestras, ya
    # existente) y armar acá la confirmación de "Muestras a tomar" -- sin
    # esto no hay forma de saber contra qué especificación consultar.
    id_especificacion: Optional[int] = None
    # Vencimiento que ya trae la solicitud (resuelto contra el ERP al
    # crearla, ver crear_solicitud) -- se ofrece como valor sugerido/
    # precargado en Ejecutar Muestreo para que la persona lo confirme en vez
    # de tener que volver a tipearlo, pero SIEMPRE pidiendo confirmación
    # explícita (ver datos_fisicos.sin_vencimiento_confirmado): que el campo
    # venga con un valor no exime de revisarlo. None si el ERP no tenía
    # vencimiento cargado (sentinel o NULL, ya normalizado en el origen).
    fecha_vencimiento_sugerida: Optional[date] = None
    datos_fisicos: DatosFisicosMuestreo
    checklist_muestreo: list[ChecklistMuestreoItem] = []


class OrdenTrabajoDigitalBody(BaseModel):
    datos_fisicos: DatosFisicosMuestreo
    checklist_muestreo: list[ChecklistMuestreoRespuesta] = []
    # Confirmación de "Muestras a tomar" (estándar de la especificación +
    # eventuales filas ad-hoc) -- se guarda en lims_solicitud_muestras al
    # confirmar el muestreo, mismo momento para solicitudes manuales y del
    # agente (ver MuestraConfirmadaInput).
    muestras: list[MuestraConfirmadaInput] = []


class OrdenTrabajoDigitalResponse(BaseModel):
    id_solicitud: int
    id_muestra: int
    codigo_muestra: str
