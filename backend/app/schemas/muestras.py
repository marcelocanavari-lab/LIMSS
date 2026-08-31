from pydantic import BaseModel, Field, model_validator
from typing import Optional
from datetime import date, datetime


# ── ERP: líneas de un IR (solo lectura) ───────────────────────

class LineaIR(BaseModel):
    N01Id: int
    NUMCOMO: str
    IdM21: int
    CODART: str
    DESART: str
    CANTID: float
    unidad: Optional[str] = None
    proveedor: Optional[str] = None
    proveedor_codigo: Optional[str] = None
    fecha_ingreso: Optional[date] = None
    fecha_vencimiento: Optional[date] = None
    cantidad_ingresada: Optional[float] = None
    advertencia: Optional[str] = None
    # FECCOR del comprobante (no confundir con fecha_ingreso=FECCOM) -- el
    # campo que efectivamente se usa para resolver colisiones de
    # (NUMCOMO, año). Solo relevante para diferenciar candidatos cuando hay
    # más de un N01Id para el mismo "NNN/AA" (ver buscar_todos_candidatos_ir
    # en erp_ir.py); en el caso normal (sin colisión) es informativo nomás.
    fecha_comprobante: Optional[date] = None


# ── Materiales (búsqueda unificada por tipo: IR o lote) ──────────

class MaterialEncontrado(BaseModel):
    referencia: str
    IdM21: int
    CODART: str
    DESART: str
    cantidad: Optional[float] = None
    unidad: Optional[str] = None
    proveedor: Optional[str] = None
    proveedor_codigo: Optional[str] = None
    fecha_ingreso: Optional[date] = None
    fecha_vencimiento: Optional[date] = None
    cantidad_ingresada: Optional[float] = None
    advertencia: Optional[str] = None
    # Subartículo del ERP (GIT59SAR.CODSAR) -- solo viene poblado en la
    # búsqueda por IR (rama 'materia_prima' de buscar_material). Lo usa
    # SolicitudesMuestreoPage.jsx para saber si el material es '0006'
    # (Material de Empaque sin codificar) y relajar lote_proveedor/
    # fecha_vencimiento como opcionales -- ver crear_solicitud.
    CODSAR: Optional[str] = None
    # N01Id/fecha_comprobante: solo poblados en la rama 'materia_prima' (por
    # IR) -- ver LineaIR más arriba para la misma distinción FECCOR vs
    # FECCOM. Cuando hay colisión de (NUMCOMO, año), buscar_material devuelve
    # un MaterialEncontrado por cada comprobante candidato con su propio
    # N01Id, para que el frontend arme el selector (ver
    # SolicitudesMuestreoPage.jsx/MuestraNuevaPage.jsx) y ese N01Id viaje tal
    # cual hasta la creación de la solicitud/muestra.
    N01Id: Optional[int] = None
    fecha_comprobante: Optional[date] = None


# ── Muestras ───────────────────────────────────────────────────

class MuestraCreate(BaseModel):
    tipo_referencia: str = Field(..., pattern=r"^(ir|lote)$")
    tipo_material: str = Field(..., pattern=r"^(materia_prima|granel|semi_elaborado|producto_terminado)$")
    nro_referencia: str = Field(..., min_length=1, max_length=50)
    erp_IdM21: int
    erp_CODART: str = Field(..., min_length=1, max_length=20)
    erp_DESART: str = Field(..., min_length=1, max_length=100)
    erp_cantidad_lote: Optional[float] = None
    erp_proveedor: Optional[str] = Field(None, max_length=100)
    cantidad_enviada: Optional[float] = None
    unidad_enviada: Optional[str] = Field(None, max_length=20)
    observaciones: Optional[str] = Field(None, max_length=500)
    # N01Id del comprobante IR ya resuelto en la búsqueda previa (ver
    # MaterialEncontrado.N01Id) -- solo aplica cuando tipo_referencia='ir'.
    # Se guarda tal cual llega, sin volver a resolver contra el ERP acá (este
    # endpoint no consulta el ERP, confía en lo que ya resolvió el frontend).
    erp_n01id: Optional[int] = None


class MuestraUpdate(BaseModel):
    """Edición post-ingreso: solo estos dos campos son editables -- todo lo
    que viene del ERP (erp_IdM21/erp_CODART/erp_DESART) y el estado del
    flujo quedan fuera a propósito, no hay endpoint para tocarlos."""
    tipo_material: Optional[str] = Field(None, pattern=r"^(materia_prima|granel|semi_elaborado|producto_terminado)$")
    observaciones: Optional[str] = Field(None, max_length=500)


class MuestraResponse(BaseModel):
    id_muestra: int
    codigo_muestra: str
    tipo_referencia: str
    tipo_material: Optional[str] = None
    nro_referencia: str
    erp_IdM21: int
    erp_CODART: str
    erp_DESART: str
    erp_cantidad_lote: Optional[float] = None
    erp_proveedor: Optional[str] = None
    cantidad_enviada: Optional[float] = None
    unidad_enviada: Optional[str] = None
    id_especificacion: Optional[int] = None
    estado: str
    id_usuario_muestreo: int
    usuario_muestreo_nombre: str
    fecha_muestreo: datetime
    observaciones: Optional[str] = None
    # True cuando el envío se generó por adelantado desde la solicitud, antes
    # de que el muestreador ejecute el muestreo físico -- fecha_muestreo es
    # un placeholder hasta ese momento (ver POST .../orden-trabajo-digital).
    datos_muestreo_pendientes: bool = False
    # N01Id del comprobante IR ya resuelto (ver MuestraCreate.erp_n01id) --
    # None para muestras por lote, o para muestras viejas creadas antes de
    # este campo.
    erp_n01id: Optional[int] = None


# ── Vincular especificación (muestra creada antes de que la especificación
# ── de su artículo existiera en Datos Maestros, ver GET/POST más abajo) ──

class EspecificacionCandidata(BaseModel):
    id_especificacion: int
    erp_CODART: str
    erp_DESART: str
    tipo_material: str
    version: str


class VincularEspecificacionBody(BaseModel):
    id_especificacion: int


# ── Laboratorios ───────────────────────────────────────────────

class LaboratorioCreate(BaseModel):
    nombre: str = Field(..., min_length=1, max_length=150)
    direccion: Optional[str] = Field(None, max_length=200)
    contacto: Optional[str] = Field(None, max_length=100)
    email: Optional[str] = Field(None, max_length=100)
    telefono: Optional[str] = Field(None, max_length=30)
    # Ver migrations_laboratorio_requiere_coas.sql -- si está en True, al
    # generar el remito se adjunta el protocolo del proveedor (COAS) ya
    # cargado en la solicitud, o se avisa antes de continuar si todavía no
    # está cargado (ver generar_remito en envios.py).
    requiere_coas_proveedor: bool = False


class LaboratorioResponse(LaboratorioCreate):
    id_laboratorio: int
    activo: bool


class LaboratorioUpdate(BaseModel):
    nombre: str = Field(..., min_length=1, max_length=150)
    direccion: Optional[str] = Field(None, max_length=200)
    contacto: Optional[str] = Field(None, max_length=100)
    email: Optional[str] = Field(None, max_length=100)
    telefono: Optional[str] = Field(None, max_length=30)
    activo: bool
    requiere_coas_proveedor: bool = False


# ── Impresoras de etiquetas (SATO, impresión directa vía SBPL) ────

class ImpresoraEtiquetaCreate(BaseModel):
    nombre: str = Field(..., min_length=1, max_length=50)
    modelo: str = Field(..., min_length=1, max_length=20)
    # 'compartida': impresora conectada por USB a una PC y compartida en red
    # (mecanismo original, ver app/services/impresion_sato.py). 'red_directa':
    # impresora con IP propia en la LAN, se le escribe el SBPL directo por
    # socket TCP, sin pasar por ningún driver de Windows.
    tipo_conexion: str = Field("compartida", pattern=r"^(compartida|red_directa)$")
    # Obligatorio solo si tipo_conexion='compartida' -- formato \\NOMBREPC\Compartido.
    ruta_red: Optional[str] = Field(None, max_length=200)
    # Obligatorios solo si tipo_conexion='red_directa'. 9100 es el puerto
    # RAW/JetDirect estándar de facto, editable por si alguna impresora
    # puntual usa otro.
    ip_directa: Optional[str] = Field(None, max_length=50)
    puerto_directo: int = Field(9100, gt=0, le=65535)
    resolucion_dpi: int = Field(203, gt=0)
    ancho_mm: int = Field(100, gt=0)
    alto_mm: int = Field(85, gt=0)

    @model_validator(mode="after")
    def _validar_datos_conexion(self):
        if self.tipo_conexion == "compartida" and not (self.ruta_red and self.ruta_red.strip()):
            raise ValueError("ruta_red es obligatorio para impresoras de tipo 'compartida'")
        if self.tipo_conexion == "red_directa" and not (self.ip_directa and self.ip_directa.strip()):
            raise ValueError("ip_directa es obligatorio para impresoras de tipo 'red_directa'")
        return self


class ImpresoraEtiquetaUpdate(ImpresoraEtiquetaCreate):
    activa: bool


class ImpresoraEtiquetaResponse(ImpresoraEtiquetaCreate):
    id_impresora: int
    activa: bool


class ImprimirDirectoBody(BaseModel):
    id_impresora: int
    # Cantidad de copias a imprimir -- el operador la confirma en pantalla
    # antes de mandar el trabajo (ver <Q> en impresion_sato.py). Default 1
    # para no romper llamadas viejas que todavía no manden este campo.
    cantidad: int = Field(1, ge=1, le=99)


class ImprimirDirectoResponse(BaseModel):
    ok: bool
    mensaje: str


class CantidadEtiquetasResponse(BaseModel):
    """Preview de cuántas etiquetas se van a generar para una muestra si se
    imprime por SATO -- para mostrar "se van a imprimir N" ANTES de mandar
    el trabajo real (mismo criterio ya usado para CUARENTENA, cantidad
    conocida de antemano)."""
    cantidad_muestras: int
    cantidad_etiquetas_fisicas: int


# ── Impresión de Etiquetas (acceso general desde el Dashboard) ────
#
# Búsqueda unificada solicitud + muestra: CUARENTENA se imprime al ingreso
# de la solicitud (puede no tener muestra vinculada todavía, si el
# muestreo físico no se ejecutó), MUESTRA y APROBADO son por muestra.

class ItemImpresionEtiquetas(BaseModel):
    tipo: str  # 'solicitud' | 'muestra'
    id: int  # id_solicitud o id_muestra, según `tipo`
    identificador: str  # nro_solicitud o codigo_muestra
    erp_CODART: str
    erp_DESART: str
    estado: str
    # Subconjunto de ['muestra', 'cuarentena', 'aprobado', 'rechazado'] --
    # lo que corresponde imprimir para este ítem según su estado actual.
    # Las etiquetas complementarias de Aprobado (si la especificación tiene
    # cantidad_etiquetas_complementarias > 0) NO son una opción aparte acá
    # -- se adjuntan automáticamente al trabajo de impresión de "aprobado"
    # (ver _imprimir_etiqueta_estado_muestra en routes/muestras.py).
    etiquetas_disponibles: list[str]


# ── Contactos por laboratorio ───────────────────────────────────
#
# Distinto del campo legacy lims_laboratorios.contacto (texto libre, un solo
# nombre): esto es una lista de personas de contacto reales, seleccionables
# al confirmar un envío ("Dirigido a:") y en el remito de testigos.

class ContactoLaboratorioCreate(BaseModel):
    nombre: str = Field(..., min_length=1, max_length=150)
    cargo: Optional[str] = Field(None, max_length=100)
    email: Optional[str] = Field(None, max_length=100)
    telefono: Optional[str] = Field(None, max_length=30)


class ContactoLaboratorioUpdate(BaseModel):
    nombre: str = Field(..., min_length=1, max_length=150)
    cargo: Optional[str] = Field(None, max_length=100)
    email: Optional[str] = Field(None, max_length=100)
    telefono: Optional[str] = Field(None, max_length=30)
    activo: bool


class ContactoLaboratorioResponse(BaseModel):
    id_contacto: int
    id_laboratorio: int
    nombre: str
    cargo: Optional[str] = None
    email: Optional[str] = None
    telefono: Optional[str] = None
    activo: bool


# ── Envíos ─────────────────────────────────────────────────────

class TestigoEnvioItem(BaseModel):
    id_testigo: int


class EnvioCreate(BaseModel):
    id_laboratorio: int
    id_contacto: Optional[int] = None
    testigos: list[TestigoEnvioItem] = []
    temperatura_transporte: Optional[str] = Field(None, max_length=50)
    nro_remito: Optional[str] = Field(None, max_length=50)
    transportista: Optional[str] = Field(None, max_length=100)
    analisis_solicitados: Optional[str] = Field(None, max_length=500)
    protocolo_utilizar: Optional[str] = Field(None, max_length=100)
    id_espec_ensayo: Optional[list[int]] = None


class EnsayoSolicitado(BaseModel):
    id_espec_ensayo: int
    nombre_ensayo: str
    requerido_por_defecto: bool
    id_laboratorio: Optional[int] = None
    laboratorio_nombre: Optional[str] = None
    obligatorio: bool = False
    # Resultado ya cargado para este envío, si lo hay (None = todavía no se cargó).
    valor_numerico: Optional[float] = None
    valor_cualitativo: Optional[str] = None
    dentro_especificacion: Optional[bool] = None


class TestigoEnviado(BaseModel):
    id_testigo: int
    codigo: str
    nombre: str
    nro_ir: Optional[str] = None


class TestigoRemito(BaseModel):
    id_testigo: int
    codigo: str
    nombre: str
    nro_ir: Optional[str] = None
    nro_lote: Optional[str] = None
    fecha_vencimiento: Optional[date] = None


class ProtocoloEnvio(BaseModel):
    id_protocolo: int
    nro_protocolo_ext: str
    fecha_emision: date
    pdf_nombre_original: str
    fecha_carga: datetime


class FacturaResumenEnvio(BaseModel):
    id_factura: int
    nro_factura: str
    estado_pago: str


class EnvioResponse(BaseModel):
    id_envio: int
    id_muestra: int
    id_laboratorio: int
    laboratorio_nombre: Optional[str] = None
    id_contacto: Optional[int] = None
    contacto_nombre: Optional[str] = None
    testigos: list[TestigoEnviado] = []
    fecha_despacho: datetime
    temperatura_transporte: Optional[str] = None
    nro_remito: Optional[str] = None
    transportista: Optional[str] = None
    analisis_solicitados: Optional[str] = None
    protocolo_utilizar: Optional[str] = None
    id_usuario_envio: int
    alerta_testigo_por_vencer: bool = False
    alerta_reorden: bool = False
    ensayos_solicitados: list[EnsayoSolicitado] = []
    protocolo: Optional[ProtocoloEnvio] = None
    completo: bool = False
    factura: Optional[FacturaResumenEnvio] = None
    # Al menos un ensayo de este envío tiene una fila en lims_factura_detalle
    # -- indicador simple de "Facturado"/"Sin Facturar" para la pantalla de
    # Envío de Muestras (distinto de `factura`, que trae el resumen de la
    # factura si existe vía lims_factura_envios).
    facturado: bool = False
    # Ya existe un remito en PDF generado para este envío (lims_remitos) --
    # gatea si corresponde ofrecer el acceso directo a "Constancia de
    # Recepción" (no tiene sentido antes de que exista el remito).
    tiene_remito: bool = False


class RemitoResponse(BaseModel):
    id_remito: Optional[int] = None
    id_envio: int
    codigo_muestra: str
    tipo_referencia: str
    nro_referencia: str
    erp_CODART: str
    erp_DESART: str
    fecha_muestreo: datetime
    usuario_muestreo_nombre: str
    cantidad_enviada: Optional[float] = None
    unidad_enviada: Optional[str] = None
    laboratorio_nombre: str
    laboratorio_direccion: Optional[str] = None
    laboratorio_contacto: Optional[str] = None
    id_contacto: Optional[int] = None
    contacto_nombre: Optional[str] = None
    contacto_cargo: Optional[str] = None
    fecha_despacho: datetime
    temperatura_transporte: Optional[str] = None
    nro_remito: Optional[str] = None
    transportista: Optional[str] = None
    analisis_solicitados: Optional[str] = None
    protocolo_utilizar: Optional[str] = None
    ensayos_solicitados: list[EnsayoSolicitado] = []
    testigos: list[TestigoRemito] = []
    # Constancia de recepción (copia firmada por el laboratorio), ver
    # POST/GET /api/envios/{id_envio}/remito/copia-firmada en envios.py.
    tiene_copia_firmada: bool = False
    fecha_recepcion: Optional[date] = None
    recibido_por: Optional[str] = None
    # Vencimiento confirmado en Ejecutar Muestreo (ver DatosFisicosMuestreo
    # en solicitudes_muestreo.py) -- para que RemitoImprimirPage.jsx pueda
    # avisar ANTES de generar el PDF si nadie lo revisó todavía (ninguno de
    # los dos campos cargado), en vez de que la persona recién se entere
    # mirando el documento ya generado.
    fecha_vencimiento_confirmada: Optional[date] = None
    sin_vencimiento_confirmado: bool = False
    # False solo cuando la muestra no tiene ninguna Solicitud de Muestreo
    # asociada (creada directo con Nueva Muestra) -- ese mecanismo de
    # confirmación vive en lims_solicitudes_muestreo, así que para esas
    # muestras nunca puede haber una confirmación explícita y el aviso de
    # vencimiento sin confirmar no debe dispararse (bug real: SAMP-2026-0010).
    tiene_solicitud_muestreo: bool = True
    # COAS del proveedor (ver requiere_coas_proveedor en lims_laboratorios y
    # protocolo_proveedor_path en lims_solicitudes_muestreo) -- mismo
    # criterio de aviso previo que los dos campos de arriba: si el
    # laboratorio lo requiere y todavía no está cargado, RemitoImprimirPage.jsx
    # avisa antes de generar en vez de que el remito salga sin adjuntarlo.
    laboratorio_requiere_coas: bool = False
    tiene_protocolo_proveedor: bool = False


# ── Etiquetas (REQ-ENV-003) ───────────────────────────────────────

class EtiquetaResponse(BaseModel):
    id_etiqueta: int
    id_muestra: int
    codigo_muestra: str
    erp_CODART: str
    erp_DESART: str
    tipo_referencia: str
    nro_referencia: str
    fecha_muestreo: datetime
    usuario_muestreo_nombre: str
    es_reimpresion: bool
    id_usuario_impresion: int
    fecha_hora: datetime
