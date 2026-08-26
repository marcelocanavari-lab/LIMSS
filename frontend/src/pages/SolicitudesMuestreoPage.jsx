import { useEffect, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import TopBar from '../components/TopBar';
import GruposBultos from '../components/GruposBultos';
import { solicitudesMuestreoApi } from '../api/solicitudesMuestreo';
import { maestrosApi } from '../api/maestros';
import { muestrasApi } from '../api/muestras';
import { ApiError, abrirPdfConAuth } from '../api/client';

const FILTROS_ESTADO = [
  { value: '', label: 'Todas' },
  { value: 'pendiente', label: 'Pendientes' },
  { value: 'ejecutada', label: 'Ejecutadas' },
  { value: 'anulada', label: 'Anuladas' },
];

const BADGE_ESTADO = {
  pendiente: 'badge-warn',
  ejecutada: 'badge-ok',
  anulada: 'badge-danger',
};

function labelEstado(estado) {
  return FILTROS_ESTADO.find((f) => f.value === estado)?.label?.replace(/s$/, '') || estado;
}

function formatFecha(iso) {
  return new Date(iso).toLocaleDateString();
}

// Filtra filas incompletas (el usuario tocó "+ Agregar grupo" pero no
// llegó a completarla) y convierte los valores de texto de los inputs a
// número antes de mandarlos al backend (ver BultoGrupoInput en
// app/schemas/solicitudes_muestreo.py).
function gruposBultosParaApi(grupos) {
  return grupos
    .filter((g) => g.cantidad_bultos !== '' && g.cantidad_unidades !== '')
    .map((g) => ({
      cantidad_bultos: Number(g.cantidad_bultos),
      cantidad_unidades: Number(g.cantidad_unidades),
      unidad_medida: g.unidad_medida.trim() || null,
    }));
}

// Trunca con "…" en vez de dejar que el texto largo salte de línea -- una
// sola fila que se parte en 2 líneas alcanza para desalinear la altura de
// toda la tabla (los bordes entre filas dejan de estar parejos). display:
// inline-block + maxWidth trunca sin depender de table-layout: fixed en
// toda la tabla (que rompería el ancho de Acciones, con contenido variable).
function celdaTruncada(maxWidth) {
  return {
    display: 'inline-block', maxWidth, overflow: 'hidden',
    textOverflow: 'ellipsis', whiteSpace: 'nowrap', verticalAlign: 'middle',
  };
}

function formatFechaSimple(fechaISO) {
  if (!fechaISO) return '—';
  // fecha_ingreso/fecha_vencimiento vienen como "YYYY-MM-DD" (sin hora) --
  // parsear con new Date(...) directo corre riesgo de desfasarse un día
  // por huso horario, arma la fecha local a partir de las partes.
  const [anio, mes, dia] = fechaISO.split('-');
  return `${dia}/${mes}/${anio}`;
}

export default function SolicitudesMuestreoPage() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const puedeCrear = ['qa', 'admin'].includes(user?.rol);
  const puedeAnular = ['qa', 'admin'].includes(user?.rol);
  // Generar envío por adelantado es tarea de quien gestiona envíos (mismo
  // criterio que EnvioFormPage/confirmar_envio), no solo de quien crea/anula
  // solicitudes -- analista_qc también puede.
  const puedeGenerarEnvio = ['analista_qc', 'qa', 'admin'].includes(user?.rol);

  const estadoInicial = searchParams.get('estado');
  const [estado, setEstado] = useState(
    FILTROS_ESTADO.some((f) => f.value === estadoInicial) ? estadoInicial : ''
  );
  const [idMuestreadorFiltro, setIdMuestreadorFiltro] = useState('');
  const [muestreadoresFiltro, setMuestreadoresFiltro] = useState([]);
  const [solicitudes, setSolicitudes] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [generandoEnvioId, setGenerandoEnvioId] = useState(null);

  const [modalAbierto, setModalAbierto] = useState(false);

  // ── Modal: nueva solicitud ──────────────────────────────────────
  const [nroIr, setNroIr] = useState('');
  const [buscando, setBuscando] = useState(false);
  const [material, setMaterial] = useState(null);
  const [lineasMaterial, setLineasMaterial] = useState(null);
  const [especificacion, setEspecificacion] = useState(null);
  const [laboratorios, setLaboratorios] = useState([]);
  const [idLaboratorio, setIdLaboratorio] = useState('');
  const [muestreadores, setMuestreadores] = useState([]);
  const [idMuestreador, setIdMuestreador] = useState('');
  const [observaciones, setObservaciones] = useState('');
  const [advertenciaEspec, setAdvertenciaEspec] = useState('');
  const [advertenciaLink, setAdvertenciaLink] = useState(null);
  const [errorForm, setErrorForm] = useState('');
  const [guardando, setGuardando] = useState(false);

  // Fecha de vencimiento: se precarga con el valor del ERP (VENCOM) al
  // buscar el IR, pero queda editable -- el dato del ERP puede estar mal o
  // desactualizado.
  const [fechaVencimiento, setFechaVencimiento] = useState('');

  // Datos manuales del ingreso (no vienen del ERP -- ver P_CC002-1/2)
  const [loteProveedor, setLoteProveedor] = useState('');
  const [fechaReanalisis, setFechaReanalisis] = useState('');
  const [paisOrigen, setPaisOrigen] = useState('');
  const [nroBultos, setNroBultos] = useState('');
  const [gruposBultos, setGruposBultos] = useState([]);
  const [metodologiaAnalisis, setMetodologiaAnalisis] = useState('');
  const [fabricante, setFabricante] = useState('');
  const [protocoloProveedor, setProtocoloProveedor] = useState(null);
  // A diferencia del protocolo, es opcional -- se puede omitir acá y
  // adjuntar después desde el listado (ver el modal "Completar").
  const [documentacionProveedor, setDocumentacionProveedor] = useState(null);

  // ── Modal: anular ────────────────────────────────────────────────
  const [anulandoId, setAnulandoId] = useState(null);
  const [motivoAnular, setMotivoAnular] = useState('');
  const [errorAnular, setErrorAnular] = useState('');
  const [guardandoAnular, setGuardandoAnular] = useState(false);

  // ── Modal: imprimir CUARENTENA (una etiqueta por bulto) ───────────
  const [cuarentenaSolicitud, setCuarentenaSolicitud] = useState(null);
  const [impresorasCuarentena, setImpresorasCuarentena] = useState([]);
  const [idImpresoraCuarentena, setIdImpresoraCuarentena] = useState('');
  const [imprimiendoCuarentena, setImprimiendoCuarentena] = useState(false);
  const [mensajeCuarentena, setMensajeCuarentena] = useState(null); // { tipo: 'ok'|'error', texto }

  // ── Modal: imprimir etiquetas de MUESTRA directo por SATO ──────────
  // Mismo patrón que el modal de Cuarentena de arriba y que ya usan
  // Consulta de Muestras/Impresión de Etiquetas -- el botón "Etiquetas"
  // de esta pantalla solo ofrecía PDF (verEtiquetas), nunca se conectó al
  // mecanismo de impresión directa ya usado en el resto del sistema.
  const [etiquetaMuestraSolicitud, setEtiquetaMuestraSolicitud] = useState(null);
  const [impresorasEtiquetaMuestra, setImpresorasEtiquetaMuestra] = useState([]);
  const [idImpresoraEtiquetaMuestra, setIdImpresoraEtiquetaMuestra] = useState('');
  const [imprimiendoEtiquetaMuestra, setImprimiendoEtiquetaMuestra] = useState(false);
  const [mensajeEtiquetaMuestra, setMensajeEtiquetaMuestra] = useState(null); // { tipo: 'ok'|'error', texto }
  // Cantidad a imprimir (mismo criterio que el aviso de Cuarentena arriba,
  // "se van a imprimir N etiquetas" antes de confirmar) -- acá la cantidad
  // no viene ya armada en la fila de la solicitud como nro_bultos, así que
  // se pide en el mismo momento en que se abre el modal (ver GET
  // /{id_muestra}/etiquetas-cantidad, mismos datos que ya usa el PDF).
  const [cantidadEtiquetaMuestra, setCantidadEtiquetaMuestra] = useState(null);

  // ── Modal: completar datos (cualquier solicitud pendiente) ──
  const [completandoId, setCompletandoId] = useState(null);
  const [completarLaboratorios, setCompletarLaboratorios] = useState([]);
  const [completarIdLaboratorio, setCompletarIdLaboratorio] = useState('');
  const [completarIdMuestreador, setCompletarIdMuestreador] = useState('');
  const [completarLoteProveedor, setCompletarLoteProveedor] = useState('');
  const [completarPaisOrigen, setCompletarPaisOrigen] = useState('');
  const [completarFechaReanalisis, setCompletarFechaReanalisis] = useState('');
  const [completarNroBultos, setCompletarNroBultos] = useState('');
  const [completarGruposBultos, setCompletarGruposBultos] = useState([]);
  const [completarMetodologiaAnalisis, setCompletarMetodologiaAnalisis] = useState('');
  const [completarFabricante, setCompletarFabricante] = useState('');
  const [completarProtocoloProveedorActual, setCompletarProtocoloProveedorActual] = useState('');
  const [completarProtocoloProveedor, setCompletarProtocoloProveedor] = useState(null);
  const [completarDocumentacionProveedorActual, setCompletarDocumentacionProveedorActual] = useState('');
  const [completarDocumentacionProveedor, setCompletarDocumentacionProveedor] = useState(null);
  const [errorCompletar, setErrorCompletar] = useState('');
  const [guardandoCompletar, setGuardandoCompletar] = useState(false);

  function cargar() {
    setLoading(true);
    setError('');
    solicitudesMuestreoApi
      .listar({ estado: estado || undefined, idMuestreador: idMuestreadorFiltro || undefined })
      .then(setSolicitudes)
      .catch((err) => setError(err instanceof ApiError ? err.message : 'No se pudo cargar el listado'))
      .finally(() => setLoading(false));
  }

  useEffect(cargar, [estado, idMuestreadorFiltro]);

  useEffect(() => {
    if (!puedeCrear) return;
    solicitudesMuestreoApi.listarMuestreadores().then((data) => {
      setMuestreadoresFiltro(data);
      setMuestreadores(data);
    }).catch(() => {});
  }, [puedeCrear]);

  function limpiarModal() {
    setNroIr('');
    setMaterial(null);
    setLineasMaterial(null);
    setEspecificacion(null);
    setMuestrasDefinidas([]);
    setMuestrasConfirmadas({});
    setLaboratorios([]);
    setIdLaboratorio('');
    setIdMuestreador('');
    setObservaciones('');
    setAdvertenciaEspec('');
    setAdvertenciaLink(null);
    setErrorForm('');
    setFechaVencimiento('');
    setLoteProveedor('');
    setFechaReanalisis('');
    setPaisOrigen('');
    setNroBultos('');
    setGruposBultos([]);
    setMetodologiaAnalisis('');
    setFabricante('');
    setProtocoloProveedor(null);
    setDocumentacionProveedor(null);
  }

  function abrirModal() {
    limpiarModal();
    setModalAbierto(true);
  }

  function cerrarModal() {
    setModalAbierto(false);
  }

  async function cargarEspecificacionDeMaterial(linea) {
    setEspecificacion(null);
    setMuestrasDefinidas([]);
    setMuestrasConfirmadas({});
    setLaboratorios([]);
    setIdLaboratorio('');
    setAdvertenciaEspec('');
    setAdvertenciaLink(null);

    let specs;
    try {
      // El CODART que devuelve el ERP viene con el padding de ancho fijo de
      // la columna (ej. "MP071       ", 12 caracteres) -- lims_especificaciones
      // lo guarda sin ese padding, así que hay que recortarlo antes de usarlo
      // como término de LIKE o la búsqueda no matchea nunca.
      specs = await maestrosApi.listarEspecificaciones({ vigente: true, buscar: linea.CODART.trim() });
    } catch {
      specs = [];
    }
    const spec = specs.find((s) => s.erp_IdM21 === linea.IdM21);
    if (!spec) {
      setAdvertenciaEspec('Este material no tiene una especificación vigente cargada en Datos Maestros.');
      return;
    }

    setEspecificacion(spec);

    let ensayos = [];
    try {
      ensayos = await maestrosApi.listarEnsayosEspecificacion(spec.id_especificacion);
    } catch {
      ensayos = [];
    }
    const labs = [];
    const vistos = new Set();
    for (const en of ensayos) {
      if (en.id_laboratorio && !vistos.has(en.id_laboratorio)) {
        vistos.add(en.id_laboratorio);
        labs.push({ id_laboratorio: en.id_laboratorio, nombre: en.laboratorio_nombre });
      }
    }
    setLaboratorios(labs);
    if (labs.length === 0) {
      setAdvertenciaEspec('Ningún laboratorio tiene ensayos asignados para la especificación de este material.');
    }

    // Preselecciona el laboratorio de análisis con el que ya está configurado
    // en la especificación (lims_especificacion_muestras, tipo_muestra =
    // 'analisis') -- el usuario lo puede cambiar igual, es solo un default.
    // La confirmación de "Muestras a tomar" (incluida la posibilidad de
    // agregar una ad-hoc) se hace en "Ejecutar Muestreo", no acá.
    let muestrasEspec = [];
    try {
      muestrasEspec = await maestrosApi.listarMuestrasEspecificacion(spec.id_especificacion);
    } catch {
      muestrasEspec = [];
    }
    const muestraAnalisis = muestrasEspec.find((m) => m.tipo_muestra === 'analisis');
    if (muestraAnalisis?.id_laboratorio) {
      setIdLaboratorio(String(muestraAnalisis.id_laboratorio));
    }
  }

  async function handleBuscarIr(e) {
    e.preventDefault();
    if (!nroIr.trim()) return;
    setErrorForm('');
    setMaterial(null);
    setLineasMaterial(null);
    setEspecificacion(null);
    setLaboratorios([]);
    setAdvertenciaEspec('');
    setAdvertenciaLink(null);
    setBuscando(true);
    try {
      const data = await muestrasApi.buscarMaterial('materia_prima', nroIr.trim());
      if (data.length === 1) {
        setMaterial(data[0]);
        setFechaVencimiento(data[0].fecha_vencimiento || '');
        await cargarEspecificacionDeMaterial(data[0]);
      } else {
        setLineasMaterial(data);
      }
    } catch (err) {
      setErrorForm(err instanceof ApiError ? err.message : 'No se pudo buscar el IR');
    } finally {
      setBuscando(false);
    }
  }

  async function elegirLinea(linea) {
    setMaterial(linea);
    setFechaVencimiento(linea.fecha_vencimiento || '');
    setLineasMaterial(null);
    await cargarEspecificacionDeMaterial(linea);
  }

  async function handleCrearSolicitud(e) {
    e.preventDefault();
    if (!material || !especificacion || !idLaboratorio) {
      setErrorForm('Completá el IR, verificá la especificación y elegí un laboratorio');
      return;
    }
    if (!idMuestreador) {
      setErrorForm('Elegí el muestreador asignado');
      return;
    }
    if (!material.proveedor_codigo) {
      setErrorForm('El material no tiene proveedor cargado en el ERP');
      return;
    }
    if (material.CODSAR !== '0006' && !loteProveedor.trim()) {
      setErrorForm('El lote del proveedor es obligatorio');
      return;
    }
    if (!protocoloProveedor) {
      setErrorForm('Adjuntá el protocolo del proveedor (foto o PDF) para generar la solicitud');
      return;
    }
    const tiposValidos = ['application/pdf', 'image/jpeg', 'image/jpg', 'image/png'];
    if (!tiposValidos.includes(protocoloProveedor.type)) {
      setErrorForm('El protocolo del proveedor debe ser una imagen (JPG/PNG) o un PDF');
      return;
    }
    if (documentacionProveedor && !tiposValidos.includes(documentacionProveedor.type)) {
      setErrorForm('La documentación del proveedor debe ser una imagen (JPG/PNG) o un PDF');
      return;
    }
    setErrorForm('');
    setGuardando(true);
    try {
      const nueva = await solicitudesMuestreoApi.crear({
        erp_nro_ir: material.referencia,
        erp_n01id: material.N01Id ?? null,
        id_laboratorio: Number(idLaboratorio),
        id_muestreador: Number(idMuestreador),
        observaciones: observaciones.trim() || null,
        proveedor_codigo: material.proveedor_codigo,
        proveedor_nombre: material.proveedor,
        lote_proveedor: loteProveedor.trim(),
        fecha_vencimiento: fechaVencimiento || null,
        fecha_reanalisis: fechaReanalisis || null,
        pais_origen: paisOrigen.trim() || null,
        nro_bultos: nroBultos !== '' ? Number(nroBultos) : null,
        grupos_bultos: gruposBultosParaApi(gruposBultos),
        metodologia_analisis: metodologiaAnalisis.trim() || null,
        fabricante: fabricante.trim() || null,
      }, protocoloProveedor, documentacionProveedor);
      cerrarModal();
      cargar();
      try {
        await abrirPdfConAuth(`/api/solicitudes-muestreo/${nueva.id_solicitud}/etiquetas`);
      } catch {
        // la solicitud ya se creó igual; si falla la apertura del PDF no bloqueamos el flujo
      }
    } catch (err) {
      setErrorForm(err instanceof ApiError ? err.message : 'No se pudo generar la solicitud');
    } finally {
      setGuardando(false);
    }
  }

  async function verEtiquetas(s) {
    try {
      await abrirPdfConAuth(`/api/solicitudes-muestreo/${s.id_solicitud}/etiquetas`);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'No se pudieron descargar las etiquetas');
    }
  }

  // Si la solicitud YA tiene id_muestra (muestreo ejecutado), se usa el
  // endpoint de muestras.py que resuelve todo a partir de la muestra real
  // (mismo mecanismo que ya usan MuestraEtiquetaPage/ConsultaMuestraDetalle
  // Page/ImpresionEtiquetasPage). Si todavía es PENDIENTE (sin id_muestra),
  // se usa el endpoint de solicitudes-muestreo.py, que arma las mismas
  // etiquetas directo desde la especificación -- igual que ya hace
  // "Etiquetas (PDF)" para ese mismo caso (antes SATO quedaba oculto acá
  // porque el único camino de impresión directa necesitaba una muestra
  // real; ahora ambos caminos ofrecen las mismas dos opciones).
  function contarEtiquetasParaSolicitud(s) {
    return s.id_muestra ? muestrasApi.contarEtiquetas(s.id_muestra) : solicitudesMuestreoApi.contarEtiquetas(s.id_solicitud);
  }

  function imprimirDirectoParaSolicitud(s, idImpresora) {
    return s.id_muestra
      ? muestrasApi.imprimirDirecto(s.id_muestra, idImpresora)
      : solicitudesMuestreoApi.imprimirDirecto(s.id_solicitud, idImpresora);
  }

  function abrirImprimirEtiquetaMuestra(s) {
    setEtiquetaMuestraSolicitud(s);
    setMensajeEtiquetaMuestra(null);
    setCantidadEtiquetaMuestra(null);
    contarEtiquetasParaSolicitud(s)
      .then(setCantidadEtiquetaMuestra)
      .catch(() => setMensajeEtiquetaMuestra({ tipo: 'error', texto: 'No se pudo calcular la cantidad de etiquetas a imprimir' }));
    if (impresorasEtiquetaMuestra.length === 0) {
      muestrasApi
        .listarImpresoras(true)
        .then((data) => {
          setImpresorasEtiquetaMuestra(data);
          if (data.length === 1) setIdImpresoraEtiquetaMuestra(String(data[0].id_impresora));
        })
        .catch(() => setMensajeEtiquetaMuestra({ tipo: 'error', texto: 'No se pudo cargar el listado de impresoras' }));
    }
  }

  function cerrarImprimirEtiquetaMuestra() {
    setEtiquetaMuestraSolicitud(null);
    setCantidadEtiquetaMuestra(null);
  }

  async function confirmarImprimirEtiquetaMuestra() {
    if (!idImpresoraEtiquetaMuestra || !etiquetaMuestraSolicitud) return;
    setImprimiendoEtiquetaMuestra(true);
    setMensajeEtiquetaMuestra(null);
    try {
      const resp = await imprimirDirectoParaSolicitud(etiquetaMuestraSolicitud, Number(idImpresoraEtiquetaMuestra));
      setMensajeEtiquetaMuestra({ tipo: 'ok', texto: resp.mensaje });
    } catch (err) {
      setMensajeEtiquetaMuestra({ tipo: 'error', texto: err instanceof ApiError ? err.message : 'No se pudo imprimir la etiqueta' });
    } finally {
      setImprimiendoEtiquetaMuestra(false);
    }
  }

  async function generarEnvio(s) {
    setError('');
    setGenerandoEnvioId(s.id_solicitud);
    try {
      const resp = await solicitudesMuestreoApi.generarEnvioAnticipado(s.id_solicitud);
      // La muestra se crea con datos_muestreo_pendientes=true -- se sigue con
      // el flujo normal de Envío de Muestras sobre esa muestra recién creada.
      navigate(`/muestras/${resp.id_muestra}/envio`);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'No se pudo generar el envío');
      setGenerandoEnvioId(null);
    }
  }

  async function verProtocoloProveedor(idSolicitud) {
    try {
      await abrirPdfConAuth(`/api/solicitudes-muestreo/${idSolicitud}/protocolo-proveedor`);
    } catch (err) {
      setErrorCompletar(err instanceof ApiError ? err.message : 'No se pudo abrir el protocolo del proveedor');
    }
  }

  async function verDocumentacionProveedor(idSolicitud) {
    try {
      await abrirPdfConAuth(`/api/solicitudes-muestreo/${idSolicitud}/documentacion-proveedor`);
    } catch (err) {
      setErrorCompletar(err instanceof ApiError ? err.message : 'No se pudo abrir la documentación del proveedor');
    }
  }

  async function abrirCompletar(s) {
    setCompletandoId(s.id_solicitud);
    setErrorCompletar('');
    setCompletarIdLaboratorio(s.id_laboratorio ? String(s.id_laboratorio) : '');
    setCompletarIdMuestreador(s.id_muestreador ? String(s.id_muestreador) : '');
    setCompletarLoteProveedor(s.lote_proveedor || '');
    setCompletarPaisOrigen(s.pais_origen || '');
    setCompletarFechaReanalisis(s.fecha_reanalisis || '');
    setCompletarNroBultos(s.nro_bultos != null ? String(s.nro_bultos) : '');
    setCompletarGruposBultos([]);
    setCompletarMetodologiaAnalisis(s.metodologia_analisis || '');
    setCompletarFabricante(s.fabricante || '');
    setCompletarProtocoloProveedorActual(s.protocolo_proveedor_nombre_original || '');
    setCompletarProtocoloProveedor(null);
    setCompletarDocumentacionProveedorActual(s.documentacion_proveedor_nombre_original || '');
    setCompletarDocumentacionProveedor(null);
    setCompletarLaboratorios([]);
    try {
      const detalle = await solicitudesMuestreoApi.obtener(s.id_solicitud);
      if (detalle.grupos_bultos?.length) {
        setCompletarGruposBultos(detalle.grupos_bultos.map((g) => ({
          cantidad_bultos: String(g.cantidad_bultos),
          cantidad_unidades: String(g.cantidad_unidades),
          unidad_medida: g.unidad_medida || '',
        })));
      }
      if (detalle.id_especificacion) {
        const ensayos = await maestrosApi.listarEnsayosEspecificacion(detalle.id_especificacion);
        const labs = [];
        const vistos = new Set();
        for (const en of ensayos) {
          if (en.id_laboratorio && !vistos.has(en.id_laboratorio)) {
            vistos.add(en.id_laboratorio);
            labs.push({ id_laboratorio: en.id_laboratorio, nombre: en.laboratorio_nombre });
          }
        }
        setCompletarLaboratorios(labs);
      }
    } catch (err) {
      setErrorCompletar(err instanceof ApiError ? err.message : 'No se pudieron cargar los laboratorios disponibles');
    }
  }

  function cerrarCompletar() {
    setCompletandoId(null);
  }

  async function handleCompletar(e) {
    e.preventDefault();
    setErrorCompletar('');
    setGuardandoCompletar(true);
    try {
      await solicitudesMuestreoApi.completarDatos(completandoId, {
        id_laboratorio: completarIdLaboratorio ? Number(completarIdLaboratorio) : null,
        id_muestreador: completarIdMuestreador ? Number(completarIdMuestreador) : null,
        lote_proveedor: completarLoteProveedor.trim() || null,
        pais_origen: completarPaisOrigen.trim() || null,
        fecha_reanalisis: completarFechaReanalisis || null,
        nro_bultos: completarNroBultos !== '' ? Number(completarNroBultos) : null,
        grupos_bultos: gruposBultosParaApi(completarGruposBultos),
        metodologia_analisis: completarMetodologiaAnalisis.trim() || null,
        fabricante: completarFabricante.trim() || null,
      });
      // Protocolo y documentación del proveedor van por endpoints aparte (son
      // archivos, no campos del body de completar-datos) -- se pueden subir
      // en momentos distintos entre sí y del resto de los datos, cada uno
      // solo si el usuario eligió un archivo nuevo.
      if (completarProtocoloProveedor) {
        await solicitudesMuestreoApi.subirProtocoloProveedor(completandoId, completarProtocoloProveedor);
      }
      if (completarDocumentacionProveedor) {
        await solicitudesMuestreoApi.subirDocumentacionProveedor(completandoId, completarDocumentacionProveedor);
      }
      cerrarCompletar();
      cargar();
    } catch (err) {
      setErrorCompletar(err instanceof ApiError ? err.message : 'No se pudo completar la solicitud');
    } finally {
      setGuardandoCompletar(false);
    }
  }

  function abrirAnular(s) {
    setAnulandoId(s.id_solicitud);
    setMotivoAnular('');
    setErrorAnular('');
  }

  function cerrarAnular() {
    setAnulandoId(null);
  }

  async function handleAnular(e) {
    e.preventDefault();
    if (!motivoAnular.trim()) {
      setErrorAnular('El motivo es obligatorio');
      return;
    }
    setErrorAnular('');
    setGuardandoAnular(true);
    try {
      await solicitudesMuestreoApi.anular(anulandoId, motivoAnular.trim());
      cerrarAnular();
      cargar();
    } catch (err) {
      setErrorAnular(err instanceof ApiError ? err.message : 'No se pudo anular la solicitud');
    } finally {
      setGuardandoAnular(false);
    }
  }

  function abrirImprimirCuarentena(s) {
    setCuarentenaSolicitud(s);
    setMensajeCuarentena(null);
    if (impresorasCuarentena.length === 0) {
      muestrasApi
        .listarImpresoras(true)
        .then((data) => {
          setImpresorasCuarentena(data);
          if (data.length === 1) setIdImpresoraCuarentena(String(data[0].id_impresora));
        })
        .catch(() => setMensajeCuarentena({ tipo: 'error', texto: 'No se pudo cargar el listado de impresoras' }));
    }
  }

  function cerrarImprimirCuarentena() {
    setCuarentenaSolicitud(null);
  }

  async function confirmarImprimirCuarentena() {
    if (!idImpresoraCuarentena || !cuarentenaSolicitud) return;
    setImprimiendoCuarentena(true);
    setMensajeCuarentena(null);
    try {
      const resp = await solicitudesMuestreoApi.imprimirCuarentena(cuarentenaSolicitud.id_solicitud, Number(idImpresoraCuarentena));
      setMensajeCuarentena({ tipo: 'ok', texto: resp.mensaje });
    } catch (err) {
      setMensajeCuarentena({ tipo: 'error', texto: err instanceof ApiError ? err.message : 'No se pudo imprimir las etiquetas' });
    } finally {
      setImprimiendoCuarentena(false);
    }
  }

  return (
    <div className="screen">
      <TopBar titulo="Solicitudes de Muestreo" subtitulo="Materias Primas" onBack={() => navigate(-1)} />
      <div className="screen-content">
        <div style={{ display: 'flex', gap: 'var(--sp-3)', marginBottom: 'var(--sp-4)', alignItems: 'center', flexWrap: 'wrap' }}>
          <select className="field-input" style={{ maxWidth: 200 }} value={estado} onChange={(e) => setEstado(e.target.value)}>
            {FILTROS_ESTADO.map((f) => (
              <option key={f.value} value={f.value}>{f.label}</option>
            ))}
          </select>
          {puedeCrear && (
            <select
              className="field-input"
              style={{ maxWidth: 220 }}
              value={idMuestreadorFiltro}
              onChange={(e) => setIdMuestreadorFiltro(e.target.value)}
            >
              <option value="">Todos los muestreadores</option>
              {muestreadoresFiltro.map((m) => (
                <option key={m.id_usuario} value={m.id_usuario}>{m.nombre_completo}</option>
              ))}
            </select>
          )}
          <div style={{ flex: 1 }} />
          {puedeCrear && (
            <button className="btn btn-primary" onClick={abrirModal}>+ Nueva solicitud</button>
          )}
        </div>

        {error && <div className="alert alert-danger" style={{ marginBottom: 'var(--sp-4)' }}>{error}</div>}

        {loading ? (
          <div className="state-block"><span className="spinner" /></div>
        ) : solicitudes.length === 0 ? (
          <div className="state-block">
            <span className="state-block-title">Sin solicitudes</span>
            <span>No hay solicitudes de muestreo con estos filtros</span>
          </div>
        ) : (
          // overflowX: 'auto' además del scroll vertical propio de .table-scroll --
          // red de seguridad para la fila con más botones de Acciones (hasta 5
          // según el estado -- protocolo/documentación del proveedor ya no son
          // botones sueltos acá, se completan desde "Completar"): ya achicados
          // y en una sola línea, si aun así no entran en el ancho visible, la
          // tabla scrollea horizontal en vez de partir la fila a una segunda línea.
          <div className="table-scroll" style={{ overflowX: 'auto' }}>
            <table className="data-table data-table-compact">
              <thead>
                <tr>
                  <th>N° Solicitud</th>
                  <th>IR</th>
                  <th>Material</th>
                  <th>Origen</th>
                  <th>Laboratorio</th>
                  <th>Muestreador</th>
                  <th>Estado</th>
                  <th>Fecha</th>
                  <th>Acciones</th>
                </tr>
              </thead>
              <tbody>
                {solicitudes.map((s) => (
                  <tr key={s.id_solicitud}>
                    <td style={{ fontFamily: 'var(--font-mono)' }}>{s.nro_solicitud}</td>
                    <td style={{ fontFamily: 'var(--font-mono)' }}>{s.erp_nro_ir}</td>
                    <td title={`${s.erp_DESART} (${s.erp_CODART.trim()})`}>
                      <span style={celdaTruncada(260)}>
                        {s.erp_DESART} <span style={{ color: 'var(--ink-3)' }}>({s.erp_CODART.trim()})</span>
                      </span>
                    </td>
                    <td>
                      {s.origen === 'agente' ? (
                        <span className="badge badge-info" title="Generada automáticamente por el Agente de Muestreo">Agente IA</span>
                      ) : (
                        <span style={{ color: 'var(--ink-3)' }}>—</span>
                      )}
                    </td>
                    <td title={s.laboratorio_nombre || ''}>
                      {s.laboratorio_nombre ? (
                        <span style={celdaTruncada(190)}>{s.laboratorio_nombre}</span>
                      ) : (
                        <span style={{ color: 'var(--ink-3)' }}>Sin asignar</span>
                      )}
                    </td>
                    <td title={s.muestreador_nombre || ''}>
                      {s.muestreador_nombre ? <span style={celdaTruncada(140)}>{s.muestreador_nombre}</span> : '—'}
                    </td>
                    <td>
                      <span className={`badge ${BADGE_ESTADO[s.estado] || 'badge-neutral'}`}>{labelEstado(s.estado)}</span>
                      {s.estado === 'pendiente' && s.id_muestra && (
                        <span
                          className="badge badge-info"
                          style={{ marginLeft: 4 }}
                          title="El envío ya se generó por adelantado -- todavía falta ejecutar el muestreo físico"
                        >
                          Envío generado
                        </span>
                      )}
                    </td>
                    <td>{formatFecha(s.fecha_solicitud)}</td>
                    <td className="acciones-compactas">
                      <button className="btn btn-ghost" onClick={() => verEtiquetas(s)}>Etiquetas (PDF)</button>
                      <button className="btn btn-ghost" onClick={() => abrirImprimirEtiquetaMuestra(s)}>Etiquetas (SATO)</button>
                      {!!s.nro_bultos && (
                        <button className="btn btn-ghost" onClick={() => abrirImprimirCuarentena(s)}>Cuarentena</button>
                      )}
                      {s.estado === 'pendiente' && puedeCrear && (
                        <button className="btn btn-ghost" onClick={() => abrirCompletar(s)}>Completar</button>
                      )}
                      {s.estado === 'pendiente' && !s.id_muestra && puedeGenerarEnvio && (
                        <button
                          className="btn btn-ghost"
                          onClick={() => generarEnvio(s)}
                          disabled={generandoEnvioId === s.id_solicitud}
                        >
                          {generandoEnvioId === s.id_solicitud ? <span className="spinner" /> : 'Generar envío'}
                        </button>
                      )}
                      {s.estado === 'pendiente' && (
                        <button
                          className="btn btn-ghost"
                          onClick={() => navigate(`/solicitudes-muestreo/${s.id_solicitud}/orden-trabajo-digital`)}
                        >
                          Ejecutar muestreo
                        </button>
                      )}
                      {s.estado === 'ejecutada' && (
                        <button
                          className="btn btn-ghost"
                          onClick={() => navigate(`/solicitudes-muestreo/${s.id_solicitud}/orden-trabajo-digital`)}
                        >
                          Ver Orden de Trabajo
                        </button>
                      )}
                      {s.estado === 'pendiente' && puedeAnular && (
                        <button className="btn btn-ghost" style={{ color: 'var(--danger)' }} onClick={() => abrirAnular(s)}>Anular</button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {modalAbierto && (
        <div
          style={{
            position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.5)',
            display: 'flex', justifyContent: 'flex-end', zIndex: 100,
          }}
          onClick={cerrarModal}
        >
          <form
            onSubmit={handleCrearSolicitud}
            className="card"
            style={{
              width: 'min(800px, 100%)', height: '100vh', maxHeight: '100vh',
              overflowY: 'auto', borderRadius: 0, margin: 0,
            }}
            onClick={(e) => e.stopPropagation()}
          >
            <h2 style={{ fontSize: 'var(--fs-lg)', marginBottom: 'var(--sp-3)' }}>Nueva solicitud de muestreo</h2>

            <div className="field">
              <label className="field-label">N° de IR</label>
              <div style={{ display: 'flex', gap: 'var(--sp-2)' }}>
                <input
                  className="field-input"
                  style={{ flex: 1 }}
                  placeholder="Ej. 366/20"
                  value={nroIr}
                  onChange={(e) => setNroIr(e.target.value)}
                  disabled={buscando || guardando}
                  autoFocus
                />
                <button type="button" className="btn btn-secondary" onClick={handleBuscarIr} disabled={buscando || guardando}>
                  {buscando ? <span className="spinner" /> : 'Buscar'}
                </button>
              </div>
            </div>

            {lineasMaterial && lineasMaterial.length > 1 && (
              <div style={{ marginBottom: 'var(--sp-3)' }}>
                <p style={{ fontSize: 'var(--fs-sm)', color: 'var(--ink-2)', marginBottom: 'var(--sp-2)' }}>
                  Hay más de un comprobante para este IR en el ERP -- elegí cuál corresponde:
                </p>
                <div className="select-list">
                  {lineasMaterial.map((l) => (
                    <button type="button" key={l.N01Id ?? l.IdM21} className="select-item" onClick={() => elegirLinea(l)}>
                      <span className="select-item-main">
                        <span className="select-item-title">{l.DESART}</span>
                        <span className="select-item-sub">
                          {l.CODART} — Proveedor: {l.proveedor_codigo ? `${l.proveedor_codigo} - ${l.proveedor}` : '—'}
                        </span>
                        <span className="select-item-sub">
                          Fecha del comprobante: {formatFechaSimple(l.fecha_comprobante)} — Vencimiento: {formatFechaSimple(l.fecha_vencimiento)}
                        </span>
                      </span>
                    </button>
                  ))}
                </div>
              </div>
            )}

            {material && (
              <>
                <div className="select-item select-item-active" style={{ marginBottom: 'var(--sp-3)' }}>
                  <span className="select-item-main">
                    <span className="select-item-title">{material.DESART}</span>
                    <span className="select-item-sub">{material.CODART}</span>
                  </span>
                </div>

                <div className="card" style={{ background: 'var(--surf-2)', marginBottom: 'var(--sp-3)' }}>
                  <div style={{ fontSize: 'var(--fs-sm)', display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 'var(--sp-2)', alignItems: 'center' }}>
                    <span>Proveedor según ERP (IR): <strong>{material.proveedor_codigo ? `${material.proveedor_codigo} - ${material.proveedor}` : '—'}</strong></span>
                    <span>Cantidad ingresada: <strong>{material.cantidad_ingresada != null ? `${material.cantidad_ingresada} ${material.unidad || ''}` : '—'}</strong></span>
                    <span>Fecha de ingreso: <strong>{formatFechaSimple(material.fecha_ingreso)}</strong></span>
                    <span style={{ display: 'flex', alignItems: 'center', gap: 'var(--sp-2)' }}>
                      Fecha de vencimiento:
                      <input
                        className="field-input"
                        type="date"
                        style={{ maxWidth: 160 }}
                        value={fechaVencimiento}
                        onChange={(e) => setFechaVencimiento(e.target.value)}
                        title="Precargada desde el ERP -- se puede corregir si el dato está mal o desactualizado"
                      />
                    </span>
                  </div>
                </div>
              </>
            )}

            {advertenciaEspec && (
              <div className="alert alert-danger" style={{ marginBottom: 'var(--sp-3)' }}>
                {advertenciaEspec}
                {advertenciaLink && (
                  <>
                    {' '}
                    <a href={advertenciaLink} target="_blank" rel="noreferrer" style={{ color: 'inherit', textDecoration: 'underline' }}>
                      Ir a Datos Maestros →
                    </a>
                  </>
                )}
              </div>
            )}

            {especificacion && (
              <>
                <div className="field">
                  <label className="field-label">Laboratorio</label>
                  <select
                    className="field-input"
                    value={idLaboratorio}
                    onChange={(e) => setIdLaboratorio(e.target.value)}
                    disabled={laboratorios.length === 0}
                  >
                    <option value="">Seleccioná un laboratorio...</option>
                    {laboratorios.map((l) => (
                      <option key={l.id_laboratorio} value={l.id_laboratorio}>{l.nombre}</option>
                    ))}
                  </select>
                </div>

                <div className="field">
                  <label className="field-label">Muestreador asignado</label>
                  <select
                    className="field-input"
                    value={idMuestreador}
                    onChange={(e) => setIdMuestreador(e.target.value)}
                  >
                    <option value="">Seleccioná un muestreador...</option>
                    {muestreadores.map((m) => (
                      <option key={m.id_usuario} value={m.id_usuario}>{m.nombre_completo}</option>
                    ))}
                  </select>
                </div>

                <div style={{ display: 'flex', gap: 'var(--sp-3)' }}>
                  <div className="field" style={{ flex: 1 }}>
                    <label className="field-label">
                      Lote del proveedor{material?.CODSAR === '0006' && ' (opcional -- material sin codificar)'}
                    </label>
                    <input
                      className="field-input"
                      value={loteProveedor}
                      onChange={(e) => setLoteProveedor(e.target.value)}
                    />
                  </div>
                  <div className="field" style={{ flex: 1 }}>
                    <label className="field-label">Fecha de reanálisis (opcional)</label>
                    <input
                      className="field-input"
                      type="date"
                      value={fechaReanalisis}
                      onChange={(e) => setFechaReanalisis(e.target.value)}
                    />
                  </div>
                </div>

                <div className="field">
                  <label className="field-label">Protocolo del proveedor (foto o PDF) *</label>
                  <input
                    className="field-input"
                    type="file"
                    accept="image/*,application/pdf"
                    capture="environment"
                    onChange={(e) => setProtocoloProveedor(e.target.files?.[0] || null)}
                    disabled={guardando}
                  />
                  {protocoloProveedor && (
                    <span style={{ fontSize: 'var(--fs-sm)', color: 'var(--ink-3)' }}>{protocoloProveedor.name}</span>
                  )}
                </div>

                <div className="field">
                  <label className="field-label">Documentación del proveedor -- remito y/o factura (opcional)</label>
                  <input
                    className="field-input"
                    type="file"
                    accept="image/*,application/pdf"
                    capture="environment"
                    onChange={(e) => setDocumentacionProveedor(e.target.files?.[0] || null)}
                    disabled={guardando}
                  />
                  <span style={{ fontSize: 'var(--fs-xs)', color: 'var(--ink-3)' }}>
                    {documentacionProveedor ? documentacionProveedor.name : 'Se puede adjuntar ahora o más tarde desde el listado.'}
                  </span>
                </div>

                <div style={{ display: 'flex', gap: 'var(--sp-3)' }}>
                  <div className="field" style={{ flex: 1 }}>
                    <label className="field-label">País de origen (opcional)</label>
                    <input
                      className="field-input"
                      value={paisOrigen}
                      onChange={(e) => setPaisOrigen(e.target.value)}
                    />
                  </div>
                  <div className="field" style={{ flex: 1 }}>
                    <label className="field-label">N° de bultos (opcional)</label>
                    <input
                      className="field-input"
                      type="number"
                      step="1"
                      value={nroBultos}
                      onChange={(e) => setNroBultos(e.target.value)}
                    />
                  </div>
                </div>

                <GruposBultos grupos={gruposBultos} onChange={setGruposBultos} disabled={guardando} />

                <div className="field">
                  <label className="field-label">Metodología de análisis (opcional)</label>
                  <input
                    className="field-input"
                    value={metodologiaAnalisis}
                    onChange={(e) => setMetodologiaAnalisis(e.target.value)}
                  />
                </div>

                <div className="field">
                  <label className="field-label">Fabricante (opcional)</label>
                  <input
                    className="field-input"
                    value={fabricante}
                    onChange={(e) => setFabricante(e.target.value)}
                  />
                </div>

                <div className="field">
                  <label className="field-label">Observaciones (opcional)</label>
                  <textarea
                    className="field-input"
                    style={{ height: 70, paddingTop: 'var(--sp-2)' }}
                    value={observaciones}
                    onChange={(e) => setObservaciones(e.target.value)}
                  />
                </div>

              </>
            )}

            {errorForm && <div className="alert alert-danger" style={{ marginTop: 'var(--sp-3)' }}>{errorForm}</div>}

            <div style={{ display: 'flex', gap: 'var(--sp-3)', marginTop: 'var(--sp-4)' }}>
              <button type="button" className="btn btn-ghost" onClick={cerrarModal} disabled={guardando}>Cancelar</button>
              <button
                type="submit"
                className="btn btn-primary"
                disabled={
                  guardando || !especificacion
                  || !idLaboratorio || !idMuestreador || !material?.proveedor_codigo
                  || (material?.CODSAR !== '0006' && !loteProveedor.trim())
                  || !protocoloProveedor
                }
              >
                {guardando ? <span className="spinner" /> : 'Generar solicitud'}
              </button>
            </div>
          </form>
        </div>
      )}

      {cuarentenaSolicitud && (
        <div
          style={{
            position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.5)',
            display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 100, padding: 'var(--sp-4)',
          }}
          onClick={cerrarImprimirCuarentena}
        >
          <div className="card" style={{ width: '90%', maxWidth: 400 }} onClick={(e) => e.stopPropagation()}>
            <h2 style={{ fontSize: 'var(--fs-lg)', marginBottom: 'var(--sp-2)' }}>Imprimir CUARENTENA</h2>
            <p style={{ fontSize: 'var(--fs-sm)', color: 'var(--ink-2)', marginBottom: 'var(--sp-3)' }}>
              Se van a imprimir {cuarentenaSolicitud.nro_bultos} etiqueta{cuarentenaSolicitud.nro_bultos === 1 ? '' : 's'} (una
              por bulto) para {cuarentenaSolicitud.nro_solicitud}.
            </p>

            {impresorasCuarentena.length === 0 && !mensajeCuarentena ? (
              <div className="state-block"><span className="spinner" /></div>
            ) : impresorasCuarentena.length === 0 ? null : (
              <>
                <div className="alert alert-warn" style={{ marginBottom: 'var(--sp-3)' }}>
                  Verificá que la impresora tenga cargado el rollo de etiquetas AMARILLAS antes de continuar.
                </div>
                <div className="field">
                  <label className="field-label" htmlFor="impresoraCuarentena">Impresora</label>
                  <select
                    id="impresoraCuarentena"
                    className="field-input"
                    value={idImpresoraCuarentena}
                    onChange={(e) => setIdImpresoraCuarentena(e.target.value)}
                    disabled={imprimiendoCuarentena}
                  >
                    <option value="">Seleccioná una impresora...</option>
                    {impresorasCuarentena.map((imp) => (
                      <option key={imp.id_impresora} value={imp.id_impresora}>{imp.nombre} ({imp.modelo})</option>
                    ))}
                  </select>
                </div>
              </>
            )}

            {mensajeCuarentena && (
              <div className={`alert ${mensajeCuarentena.tipo === 'ok' ? 'alert-ok' : 'alert-danger'}`} style={{ marginBottom: 'var(--sp-3)' }}>
                {mensajeCuarentena.texto}
              </div>
            )}

            <div style={{ display: 'flex', gap: 'var(--sp-3)' }}>
              <button type="button" className="btn btn-ghost" onClick={cerrarImprimirCuarentena} disabled={imprimiendoCuarentena}>
                Cerrar
              </button>
              <button
                type="button"
                className="btn btn-primary"
                onClick={confirmarImprimirCuarentena}
                disabled={imprimiendoCuarentena || !idImpresoraCuarentena}
              >
                {imprimiendoCuarentena ? <span className="spinner" /> : 'Imprimir'}
              </button>
            </div>
          </div>
        </div>
      )}

      {etiquetaMuestraSolicitud && (
        <div
          style={{
            position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.5)',
            display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 100, padding: 'var(--sp-4)',
          }}
          onClick={cerrarImprimirEtiquetaMuestra}
        >
          <div className="card" style={{ width: '90%', maxWidth: 400 }} onClick={(e) => e.stopPropagation()}>
            <h2 style={{ fontSize: 'var(--fs-lg)', marginBottom: 'var(--sp-2)' }}>
              Imprimir etiquetas de muestra -- {etiquetaMuestraSolicitud.nro_solicitud}
            </h2>

            {cantidadEtiquetaMuestra ? (
              <p style={{ fontSize: 'var(--fs-sm)', color: 'var(--ink-2)', marginBottom: 'var(--sp-3)' }}>
                Se van a imprimir {cantidadEtiquetaMuestra.cantidad_etiquetas_fisicas} etiqueta
                {cantidadEtiquetaMuestra.cantidad_etiquetas_fisicas === 1 ? '' : 's'} física
                {cantidadEtiquetaMuestra.cantidad_etiquetas_fisicas === 1 ? '' : 's'} ({cantidadEtiquetaMuestra.cantidad_muestras} muestra
                {cantidadEtiquetaMuestra.cantidad_muestras === 1 ? '' : 's'} confirmada
                {cantidadEtiquetaMuestra.cantidad_muestras === 1 ? '' : 's'}, dos por etiqueta) para {etiquetaMuestraSolicitud.nro_solicitud}.
              </p>
            ) : !mensajeEtiquetaMuestra && (
              <div className="state-block" style={{ marginBottom: 'var(--sp-3)' }}><span className="spinner" /></div>
            )}

            {impresorasEtiquetaMuestra.length === 0 && !mensajeEtiquetaMuestra ? (
              <div className="state-block"><span className="spinner" /></div>
            ) : impresorasEtiquetaMuestra.length === 0 ? null : (
              <div className="field">
                <label className="field-label" htmlFor="impresoraEtiquetaMuestra">Impresora</label>
                <select
                  id="impresoraEtiquetaMuestra"
                  className="field-input"
                  value={idImpresoraEtiquetaMuestra}
                  onChange={(e) => setIdImpresoraEtiquetaMuestra(e.target.value)}
                  disabled={imprimiendoEtiquetaMuestra}
                >
                  <option value="">Seleccioná una impresora...</option>
                  {impresorasEtiquetaMuestra.map((imp) => (
                    <option key={imp.id_impresora} value={imp.id_impresora}>{imp.nombre} ({imp.modelo})</option>
                  ))}
                </select>
              </div>
            )}

            {mensajeEtiquetaMuestra && (
              <div className={`alert ${mensajeEtiquetaMuestra.tipo === 'ok' ? 'alert-ok' : 'alert-danger'}`} style={{ marginBottom: 'var(--sp-3)' }}>
                {mensajeEtiquetaMuestra.texto}
              </div>
            )}

            <div style={{ display: 'flex', gap: 'var(--sp-3)' }}>
              <button type="button" className="btn btn-ghost" onClick={cerrarImprimirEtiquetaMuestra} disabled={imprimiendoEtiquetaMuestra}>
                Cerrar
              </button>
              <button
                type="button"
                className="btn btn-primary"
                onClick={confirmarImprimirEtiquetaMuestra}
                disabled={imprimiendoEtiquetaMuestra || !idImpresoraEtiquetaMuestra}
              >
                {imprimiendoEtiquetaMuestra ? <span className="spinner" /> : 'Imprimir'}
              </button>
            </div>
          </div>
        </div>
      )}

      {anulandoId && (
        <div
          style={{
            position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.5)',
            display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 100, padding: 'var(--sp-4)',
          }}
          onClick={cerrarAnular}
        >
          <form
            onSubmit={handleAnular}
            className="card"
            style={{ width: '90%', maxWidth: 400 }}
            onClick={(e) => e.stopPropagation()}
          >
            <h2 style={{ fontSize: 'var(--fs-lg)', marginBottom: 'var(--sp-3)' }}>Anular solicitud</h2>
            <div className="field" style={{ marginBottom: 0 }}>
              <label className="field-label">Motivo</label>
              <textarea
                className="field-input"
                style={{ height: 80, paddingTop: 'var(--sp-2)' }}
                value={motivoAnular}
                onChange={(e) => setMotivoAnular(e.target.value)}
                autoFocus
              />
            </div>
            {errorAnular && <div className="alert alert-danger" style={{ marginTop: 'var(--sp-3)' }}>{errorAnular}</div>}
            <div style={{ display: 'flex', gap: 'var(--sp-3)', marginTop: 'var(--sp-4)' }}>
              <button type="button" className="btn btn-ghost" onClick={cerrarAnular} disabled={guardandoAnular}>Cancelar</button>
              <button type="submit" className="btn btn-primary" disabled={guardandoAnular}>
                {guardandoAnular ? <span className="spinner" /> : 'Anular'}
              </button>
            </div>
          </form>
        </div>
      )}


      {completandoId && (
        <div
          style={{
            position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.5)',
            display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 100, padding: 'var(--sp-4)',
          }}
          onClick={cerrarCompletar}
        >
          <form
            onSubmit={handleCompletar}
            className="card"
            style={{ width: '98%', maxWidth: 860, maxHeight: '98vh', overflowY: 'auto' }}
            onClick={(e) => e.stopPropagation()}
          >
            <h2 style={{ fontSize: 'var(--fs-lg)', marginBottom: 'var(--sp-3)' }}>Completar solicitud</h2>
            <p style={{ color: 'var(--ink-2)', fontSize: 'var(--fs-sm)', marginBottom: 'var(--sp-3)' }}>
              Laboratorio y muestreador son necesarios para poder ejecutar el muestreo. El resto
              (lote, protocolo, documentación del proveedor, etc.) se puede completar en cualquier
              momento, incluso después de ejecutado -- no hace falta esperar para que el muestreador
              haga su parte.
            </p>

            <div style={{ display: 'flex', gap: 'var(--sp-3)' }}>
              <div className="field" style={{ flex: 1 }}>
                <label className="field-label">Laboratorio</label>
                <select
                  className="field-input"
                  value={completarIdLaboratorio}
                  onChange={(e) => setCompletarIdLaboratorio(e.target.value)}
                  disabled={guardandoCompletar || completarLaboratorios.length === 0}
                >
                  <option value="">
                    {completarLaboratorios.length === 0 ? 'Sin laboratorios disponibles' : 'Seleccioná un laboratorio...'}
                  </option>
                  {completarLaboratorios.map((l) => (
                    <option key={l.id_laboratorio} value={l.id_laboratorio}>{l.nombre}</option>
                  ))}
                </select>
              </div>
              <div className="field" style={{ flex: 1 }}>
                <label className="field-label">Muestreador asignado</label>
                <select
                  className="field-input"
                  value={completarIdMuestreador}
                  onChange={(e) => setCompletarIdMuestreador(e.target.value)}
                  disabled={guardandoCompletar}
                >
                  <option value="">Seleccioná un muestreador...</option>
                  {muestreadores.map((m) => (
                    <option key={m.id_usuario} value={m.id_usuario}>{m.nombre_completo}</option>
                  ))}
                </select>
              </div>
            </div>

            <div style={{ display: 'flex', gap: 'var(--sp-3)' }}>
              <div className="field" style={{ flex: 1 }}>
                <label className="field-label">Lote del proveedor</label>
                <input
                  className="field-input"
                  value={completarLoteProveedor}
                  onChange={(e) => setCompletarLoteProveedor(e.target.value)}
                  disabled={guardandoCompletar}
                />
              </div>
              <div className="field" style={{ flex: 1 }}>
                <label className="field-label">N° de bultos (opcional)</label>
                <input
                  className="field-input"
                  type="number"
                  step="1"
                  value={completarNroBultos}
                  onChange={(e) => setCompletarNroBultos(e.target.value)}
                  disabled={guardandoCompletar}
                />
              </div>
            </div>

            <GruposBultos grupos={completarGruposBultos} onChange={setCompletarGruposBultos} disabled={guardandoCompletar} />

            <div style={{ display: 'flex', gap: 'var(--sp-3)' }}>
              <div className="field" style={{ flex: 1 }}>
                <label className="field-label">Protocolo del proveedor (foto o PDF)</label>
                <input
                  className="field-input"
                  type="file"
                  accept="image/*,application/pdf"
                  capture="environment"
                  onChange={(e) => setCompletarProtocoloProveedor(e.target.files?.[0] || null)}
                  disabled={guardandoCompletar}
                />
                <span style={{ fontSize: 'var(--fs-xs)', color: 'var(--ink-3)' }}>
                  {completarProtocoloProveedor ? (
                    completarProtocoloProveedor.name
                  ) : completarProtocoloProveedorActual ? (
                    <>
                      {completarProtocoloProveedorActual}{' '}
                      <button type="button" className="btn btn-ghost" style={{ padding: 0, minHeight: 'auto' }} onClick={() => verProtocoloProveedor(completandoId)}>
                        Ver
                      </button>
                    </>
                  ) : (
                    'Todavía no tiene protocolo cargado'
                  )}
                </span>
              </div>
              <div className="field" style={{ flex: 1 }}>
                <label className="field-label">Documentación del proveedor -- remito y/o factura (opcional)</label>
                <input
                  className="field-input"
                  type="file"
                  accept="image/*,application/pdf"
                  capture="environment"
                  onChange={(e) => setCompletarDocumentacionProveedor(e.target.files?.[0] || null)}
                  disabled={guardandoCompletar}
                />
                <span style={{ fontSize: 'var(--fs-xs)', color: 'var(--ink-3)' }}>
                  {completarDocumentacionProveedor ? (
                    completarDocumentacionProveedor.name
                  ) : completarDocumentacionProveedorActual ? (
                    <>
                      {completarDocumentacionProveedorActual}{' '}
                      <button type="button" className="btn btn-ghost" style={{ padding: 0, minHeight: 'auto' }} onClick={() => verDocumentacionProveedor(completandoId)}>
                        Ver
                      </button>
                    </>
                  ) : (
                    'Todavía no tiene documentación cargada'
                  )}
                </span>
              </div>
            </div>

            <div style={{ display: 'flex', gap: 'var(--sp-3)' }}>
              <div className="field" style={{ flex: 1 }}>
                <label className="field-label">País de origen (opcional)</label>
                <input
                  className="field-input"
                  value={completarPaisOrigen}
                  onChange={(e) => setCompletarPaisOrigen(e.target.value)}
                  disabled={guardandoCompletar}
                />
              </div>
              <div className="field" style={{ flex: 1 }}>
                <label className="field-label">Fecha de reanálisis (opcional)</label>
                <input
                  className="field-input"
                  type="date"
                  value={completarFechaReanalisis}
                  onChange={(e) => setCompletarFechaReanalisis(e.target.value)}
                  disabled={guardandoCompletar}
                />
              </div>
            </div>

            <div style={{ display: 'flex', gap: 'var(--sp-3)' }}>
              <div className="field" style={{ flex: 1 }}>
                <label className="field-label">Metodología de análisis (opcional)</label>
                <input
                  className="field-input"
                  value={completarMetodologiaAnalisis}
                  onChange={(e) => setCompletarMetodologiaAnalisis(e.target.value)}
                  disabled={guardandoCompletar}
                />
              </div>
              <div className="field" style={{ flex: 1, marginBottom: 0 }}>
                <label className="field-label">Fabricante (opcional)</label>
                <input
                  className="field-input"
                  value={completarFabricante}
                  onChange={(e) => setCompletarFabricante(e.target.value)}
                  disabled={guardandoCompletar}
                />
              </div>
            </div>

            {errorCompletar && <div className="alert alert-danger" style={{ marginTop: 'var(--sp-3)' }}>{errorCompletar}</div>}
            <div style={{ display: 'flex', gap: 'var(--sp-3)', marginTop: 'var(--sp-4)' }}>
              <button type="button" className="btn btn-ghost" onClick={cerrarCompletar} disabled={guardandoCompletar}>Cancelar</button>
              <button type="submit" className="btn btn-primary" disabled={guardandoCompletar}>
                {guardandoCompletar ? <span className="spinner" /> : 'Guardar'}
              </button>
            </div>
          </form>
        </div>
      )}
    </div>
  );
}
