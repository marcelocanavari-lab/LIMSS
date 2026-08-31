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

  const estadoInicial = searchParams.get('estado');
  const [estado, setEstado] = useState(
    FILTROS_ESTADO.some((f) => f.value === estadoInicial) ? estadoInicial : ''
  );
  const [idMuestreadorFiltro, setIdMuestreadorFiltro] = useState('');
  const [muestreadoresFiltro, setMuestreadoresFiltro] = useState([]);
  const [solicitudes, setSolicitudes] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  // ── Modal unificado: Nueva solicitud / Completar ──────────────────
  //
  // Antes eran dos modales separados ("Ingreso de Solicitudes" e "Completar
  // Datos"), con dos juegos de campos parcialmente distintos y en distinto
  // orden. Rediseño: un solo formulario, un solo juego de estado --
  // completandoId en null es modo "nueva" (arranca con la búsqueda de IR);
  // con un id_solicitud es modo "completar" (arranca directo en los campos,
  // sin buscar nada -- el material ya está resuelto). Sin campo de
  // laboratorio en ningún lado: se resuelve más adelante, por ensayo, al
  // generar el envío (ver EnvioFormPage.jsx).
  const [modalAbierto, setModalAbierto] = useState(false);
  const [completandoId, setCompletandoId] = useState(null);
  const [solicitudEnEdicion, setSolicitudEnEdicion] = useState(null); // fila completa, solo para mostrar contexto en modo "completar"

  // Búsqueda de IR (solo modo "nueva")
  const [nroIr, setNroIr] = useState('');
  const [buscando, setBuscando] = useState(false);
  const [material, setMaterial] = useState(null);
  const [lineasMaterial, setLineasMaterial] = useState(null);
  const [especificacion, setEspecificacion] = useState(null);
  const [advertenciaEspec, setAdvertenciaEspec] = useState('');
  const [advertenciaLink, setAdvertenciaLink] = useState(null);

  // Los 15 campos del formulario unificado, en el orden pedido.
  const [muestreadores, setMuestreadores] = useState([]);
  const [idMuestreador, setIdMuestreador] = useState('');
  const [fechaFacturaProveedor, setFechaFacturaProveedor] = useState('');
  const [numeroFacturaProveedor, setNumeroFacturaProveedor] = useState('');
  const [documentacionProveedorActual, setDocumentacionProveedorActual] = useState('');
  const [documentacionProveedor, setDocumentacionProveedor] = useState(null);
  const [protocoloProveedorActual, setProtocoloProveedorActual] = useState('');
  const [protocoloProveedor, setProtocoloProveedor] = useState(null);
  const [loteProveedor, setLoteProveedor] = useState('');
  // Se precarga con el valor del ERP (VENCOM) al buscar el IR, pero queda
  // editable -- el dato del ERP puede estar mal o desactualizado. El
  // checkbox de "sin vencimiento" es un mecanismo propio de este campo,
  // independiente del que ya existe en Ejecutar Muestreo para el
  // vencimiento confirmado físicamente (fecha_vencimiento_real).
  const [fechaVencimiento, setFechaVencimiento] = useState('');
  const [sinVencimientoIngresoConfirmado, setSinVencimientoIngresoConfirmado] = useState(false);
  const [fechaReanalisis, setFechaReanalisis] = useState('');
  const [paisOrigen, setPaisOrigen] = useState('');
  const [nroBultos, setNroBultos] = useState('');
  const [gruposBultos, setGruposBultos] = useState([]);
  const [metodologiaAnalisis, setMetodologiaAnalisis] = useState('');
  const [fabricante, setFabricante] = useState('');
  const [idUsuarioRecibio, setIdUsuarioRecibio] = useState('');
  const [idUsuarioRotulo, setIdUsuarioRotulo] = useState('');
  const [observaciones, setObservaciones] = useState('');

  const [usuariosActivos, setUsuariosActivos] = useState([]);
  const [errorForm, setErrorForm] = useState('');
  const [guardando, setGuardando] = useState(false);

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
    solicitudesMuestreoApi.listarUsuariosActivos().then(setUsuariosActivos).catch(() => {});
  }, []);

  useEffect(() => {
    if (!puedeCrear) return;
    solicitudesMuestreoApi.listarMuestreadores().then((data) => {
      setMuestreadoresFiltro(data);
      setMuestreadores(data);
    }).catch(() => {});
  }, [puedeCrear]);

  // Limpia TODOS los campos compartidos del formulario unificado -- se usa
  // tanto al abrir "Nueva solicitud" (arranca todo en blanco) como después
  // de guardar en cualquiera de los dos modos.
  function limpiarCamposFormulario() {
    setIdMuestreador('');
    setFechaFacturaProveedor('');
    setNumeroFacturaProveedor('');
    setDocumentacionProveedorActual('');
    setDocumentacionProveedor(null);
    setProtocoloProveedorActual('');
    setProtocoloProveedor(null);
    setLoteProveedor('');
    setFechaVencimiento('');
    setSinVencimientoIngresoConfirmado(false);
    setFechaReanalisis('');
    setPaisOrigen('');
    setNroBultos('');
    setGruposBultos([]);
    setMetodologiaAnalisis('');
    setFabricante('');
    setIdUsuarioRecibio('');
    setIdUsuarioRotulo('');
    setObservaciones('');
    setErrorForm('');
  }

  function abrirModal() {
    setCompletandoId(null);
    setSolicitudEnEdicion(null);
    setNroIr('');
    setMaterial(null);
    setLineasMaterial(null);
    setEspecificacion(null);
    setAdvertenciaEspec('');
    setAdvertenciaLink(null);
    limpiarCamposFormulario();
    setModalAbierto(true);
  }

  function cerrarModal() {
    setModalAbierto(false);
    setCompletandoId(null);
    setSolicitudEnEdicion(null);
  }

  async function cargarEspecificacionDeMaterial(linea) {
    setEspecificacion(null);
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
  }

  async function handleBuscarIr(e) {
    e.preventDefault();
    if (!nroIr.trim()) return;
    setErrorForm('');
    setMaterial(null);
    setLineasMaterial(null);
    setEspecificacion(null);
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
    if (!material || !especificacion) {
      setErrorForm('Completá el IR y verificá la especificación');
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
      await intentarCrearSolicitud(false);
    } catch (err) {
      setErrorForm(err instanceof ApiError ? err.message : 'No se pudo generar la solicitud');
    } finally {
      setGuardando(false);
    }
  }

  // Separado de handleCrearSolicitud para poder reintentar una sola vez con
  // confirmar_duplicado_ir=true sin repetir las validaciones de arriba --
  // ver 409 "ir_duplicado" más abajo. El agente automático nunca duplica
  // (bloqueo duro, sin excepción, ver solicitud_activa_existente en el
  // backend); acá, en cambio, puede ser legítimo necesitar una segunda
  // solicitud para el mismo IR (ej. análisis adicionales pedidos después),
  // así que solo se avisa con los datos de la existente y se deja confirmar.
  async function intentarCrearSolicitud(confirmarDuplicadoIr) {
    try {
      const nueva = await solicitudesMuestreoApi.crear({
        erp_nro_ir: material.referencia,
        erp_n01id: material.N01Id ?? null,
        id_muestreador: Number(idMuestreador),
        observaciones: observaciones.trim() || null,
        proveedor_codigo: material.proveedor_codigo,
        proveedor_nombre: material.proveedor,
        lote_proveedor: loteProveedor.trim(),
        fecha_vencimiento: fechaVencimiento || null,
        sin_vencimiento_ingreso_confirmado: sinVencimientoIngresoConfirmado,
        fecha_reanalisis: fechaReanalisis || null,
        pais_origen: paisOrigen.trim() || null,
        nro_bultos: nroBultos !== '' ? Number(nroBultos) : null,
        grupos_bultos: gruposBultosParaApi(gruposBultos),
        metodologia_analisis: metodologiaAnalisis.trim() || null,
        fabricante: fabricante.trim() || null,
        fecha_factura_proveedor: fechaFacturaProveedor || null,
        numero_factura_proveedor: numeroFacturaProveedor.trim() || null,
        id_usuario_recibio: idUsuarioRecibio ? Number(idUsuarioRecibio) : null,
        id_usuario_rotulo: idUsuarioRotulo ? Number(idUsuarioRotulo) : null,
        confirmar_duplicado_ir: confirmarDuplicadoIr,
      }, protocoloProveedor, documentacionProveedor);
      cerrarModal();
      cargar();
      try {
        await abrirPdfConAuth(`/api/solicitudes-muestreo/${nueva.id_solicitud}/etiquetas`);
      } catch {
        // la solicitud ya se creó igual; si falla la apertura del PDF no bloqueamos el flujo
      }
    } catch (err) {
      if (!confirmarDuplicadoIr && err instanceof ApiError && err.status === 409 && err.detail?.error === 'ir_duplicado') {
        const d = err.detail;
        const seguir = window.confirm(
          `Ya existe la solicitud ${d.nro_solicitud} (${labelEstado(d.estado)}, ${formatFecha(d.fecha_solicitud)}) para este IR. ` +
          '¿Confirmás que necesitás generar una nueva de todas formas?',
        );
        if (seguir) {
          await intentarCrearSolicitud(true);
          return;
        }
        return;
      }
      throw err;
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

  async function verProtocoloProveedor(idSolicitud) {
    try {
      await abrirPdfConAuth(`/api/solicitudes-muestreo/${idSolicitud}/protocolo-proveedor`);
    } catch (err) {
      setErrorForm(err instanceof ApiError ? err.message : 'No se pudo abrir el protocolo del proveedor');
    }
  }

  async function verDocumentacionProveedor(idSolicitud) {
    try {
      await abrirPdfConAuth(`/api/solicitudes-muestreo/${idSolicitud}/documentacion-proveedor`);
    } catch (err) {
      setErrorForm(err instanceof ApiError ? err.message : 'No se pudo abrir la documentación del proveedor');
    }
  }

  // Modo "completar" del formulario unificado -- mismos 15 campos que
  // "Nueva solicitud", precargados con lo que ya tenía la solicitud. Sin
  // búsqueda de IR (el material ya está resuelto) y sin laboratorio (ver
  // el encabezado del archivo).
  async function abrirCompletar(s) {
    setCompletandoId(s.id_solicitud);
    setSolicitudEnEdicion(s);
    setModalAbierto(true);
    limpiarCamposFormulario();
    setIdMuestreador(s.id_muestreador ? String(s.id_muestreador) : '');
    setFechaFacturaProveedor(s.fecha_factura_proveedor || '');
    setNumeroFacturaProveedor(s.numero_factura_proveedor || '');
    setDocumentacionProveedorActual(s.documentacion_proveedor_nombre_original || '');
    setProtocoloProveedorActual(s.protocolo_proveedor_nombre_original || '');
    setLoteProveedor(s.lote_proveedor || '');
    setFechaVencimiento(s.fecha_vencimiento || '');
    setSinVencimientoIngresoConfirmado(!!s.sin_vencimiento_ingreso_confirmado);
    setFechaReanalisis(s.fecha_reanalisis || '');
    setPaisOrigen(s.pais_origen || '');
    setNroBultos(s.nro_bultos != null ? String(s.nro_bultos) : '');
    setMetodologiaAnalisis(s.metodologia_analisis || '');
    setFabricante(s.fabricante || '');
    setIdUsuarioRecibio(s.id_usuario_recibio ? String(s.id_usuario_recibio) : '');
    setIdUsuarioRotulo(s.id_usuario_rotulo ? String(s.id_usuario_rotulo) : '');
    try {
      const detalle = await solicitudesMuestreoApi.obtener(s.id_solicitud);
      if (detalle.grupos_bultos?.length) {
        setGruposBultos(detalle.grupos_bultos.map((g) => ({
          cantidad_bultos: String(g.cantidad_bultos),
          cantidad_unidades: String(g.cantidad_unidades),
          unidad_medida: g.unidad_medida || '',
        })));
      }
    } catch (err) {
      setErrorForm(err instanceof ApiError ? err.message : 'No se pudieron cargar los datos de la solicitud');
    }
  }

  async function handleCompletar(e) {
    e.preventDefault();
    setErrorForm('');
    setGuardando(true);
    try {
      await solicitudesMuestreoApi.completarDatos(completandoId, {
        id_muestreador: idMuestreador ? Number(idMuestreador) : null,
        lote_proveedor: loteProveedor.trim() || null,
        fecha_vencimiento: fechaVencimiento || null,
        sin_vencimiento_ingreso_confirmado: sinVencimientoIngresoConfirmado,
        pais_origen: paisOrigen.trim() || null,
        fecha_reanalisis: fechaReanalisis || null,
        nro_bultos: nroBultos !== '' ? Number(nroBultos) : null,
        grupos_bultos: gruposBultosParaApi(gruposBultos),
        metodologia_analisis: metodologiaAnalisis.trim() || null,
        fabricante: fabricante.trim() || null,
        fecha_factura_proveedor: fechaFacturaProveedor || null,
        numero_factura_proveedor: numeroFacturaProveedor.trim() || null,
        id_usuario_recibio: idUsuarioRecibio ? Number(idUsuarioRecibio) : null,
        id_usuario_rotulo: idUsuarioRotulo ? Number(idUsuarioRotulo) : null,
      });
      // Protocolo y documentación del proveedor van por endpoints aparte (son
      // archivos, no campos del body de completar-datos) -- se pueden subir
      // en momentos distintos entre sí y del resto de los datos, cada uno
      // solo si el usuario eligió un archivo nuevo.
      if (protocoloProveedor) {
        await solicitudesMuestreoApi.subirProtocoloProveedor(completandoId, protocoloProveedor);
      }
      if (documentacionProveedor) {
        await solicitudesMuestreoApi.subirDocumentacionProveedor(completandoId, documentacionProveedor);
      }
      cerrarModal();
      cargar();
    } catch (err) {
      setErrorForm(err instanceof ApiError ? err.message : 'No se pudo completar la solicitud');
    } finally {
      setGuardando(false);
    }
  }

  function handleSubmitFormulario(e) {
    return completandoId ? handleCompletar(e) : handleCrearSolicitud(e);
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
            onSubmit={handleSubmitFormulario}
            className="card card-compact"
            style={{
              width: 'min(1100px, 96vw)', height: '100vh', maxHeight: '100vh',
              overflowY: 'auto', borderRadius: 0, margin: 0,
            }}
            onClick={(e) => e.stopPropagation()}
          >
            <h2 style={{ fontSize: 'var(--fs-lg)', marginBottom: '4px' }}>
              {completandoId ? `Completar solicitud -- ${solicitudEnEdicion?.nro_solicitud}` : 'Nueva solicitud de muestreo'}
            </h2>

            {/* Búsqueda de IR y resolución del material -- solo en modo "nueva",
                la solicitud a completar ya tiene el material resuelto. Layout
                compacto (.field-compact, ver components.css): el formulario
                completo (búsqueda + 15 campos) tiene que entrar sin scroll en
                una resolución de escritorio común -- ver la medición real que
                motivó este ajuste (888px de desborde con el layout anterior a
                1366x768, modo "nueva"). */}
            {!completandoId && (
              <>
                <div className="field field-compact">
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
                  // Chip de material + info del ERP combinados en UNA sola
                  // tarjeta compacta (antes eran dos bloques separados, cada
                  // uno con su propio padding/margen) -- mismo contenido,
                  // menos altura.
                  <div className="card" style={{ background: 'var(--surf-2)', marginBottom: '6px', padding: '6px var(--sp-3)' }}>
                    <div style={{ fontSize: 'var(--fs-sm)' }}>
                      <strong>{material.DESART}</strong> <span style={{ color: 'var(--ink-3)' }}>({material.CODART})</span>
                    </div>
                    <div style={{ fontSize: 'var(--fs-xs)', display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '3px', marginTop: '3px' }}>
                      <span>Prov: <strong>{material.proveedor_codigo ? `${material.proveedor_codigo} - ${material.proveedor}` : '—'}</strong></span>
                      <span>Cant: <strong>{material.cantidad_ingresada != null ? `${material.cantidad_ingresada} ${material.unidad || ''}` : '—'}</strong></span>
                      <span>Ingreso: <strong>{formatFechaSimple(material.fecha_ingreso)}</strong></span>
                    </div>
                  </div>
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
              </>
            )}

            {/* Los 15 campos, mismo formulario para "nueva" (una vez resuelta
                la especificación) y "completar" (directo, sin buscar nada).
                Sin laboratorio -- se resuelve más adelante, por ensayo, al
                generar el envío. 3 campos por fila donde el contenido es
                corto (fechas, números, selects); 2 donde hace falta más
                ancho (los dos adjuntos, que muestran nombre de archivo);
                ancho completo para bultos/grupos y observaciones. */}
            {(completandoId || especificacion) && (
              <>
                <div style={{ display: 'flex', gap: 'var(--sp-3)' }}>
                  <div className="field field-compact" style={{ flex: 1 }}>
                    <label className="field-label">1. Muestreador asignado</label>
                    <select
                      className="field-input"
                      value={idMuestreador}
                      onChange={(e) => setIdMuestreador(e.target.value)}
                      disabled={guardando}
                    >
                      <option value="">Seleccioná un muestreador...</option>
                      {muestreadores.map((m) => (
                        <option key={m.id_usuario} value={m.id_usuario}>{m.nombre_completo}</option>
                      ))}
                    </select>
                  </div>
                  <div className="field field-compact" style={{ flex: 1 }}>
                    <label className="field-label">2. Fecha de factura del proveedor (opcional)</label>
                    <input
                      className="field-input"
                      type="date"
                      value={fechaFacturaProveedor}
                      onChange={(e) => setFechaFacturaProveedor(e.target.value)}
                      disabled={guardando}
                    />
                  </div>
                  <div className="field field-compact" style={{ flex: 1 }}>
                    <label className="field-label">3. N° de factura del proveedor (opcional)</label>
                    <input
                      className="field-input"
                      value={numeroFacturaProveedor}
                      onChange={(e) => setNumeroFacturaProveedor(e.target.value)}
                      disabled={guardando}
                    />
                  </div>
                </div>

                <div style={{ display: 'flex', gap: 'var(--sp-3)' }}>
                  <div className="field field-compact" style={{ flex: 1 }}>
                    <label className="field-label">4. Documento del proveedor -- remito y/o factura (opcional)</label>
                    <input
                      className="field-input"
                      type="file"
                      accept="image/*,application/pdf"
                      capture="environment"
                      onChange={(e) => setDocumentacionProveedor(e.target.files?.[0] || null)}
                      disabled={guardando}
                    />
                    <span style={{ fontSize: 'var(--fs-xs)', color: 'var(--ink-3)' }}>
                      {documentacionProveedor ? (
                        documentacionProveedor.name
                      ) : documentacionProveedorActual ? (
                        <>
                          {documentacionProveedorActual}{' '}
                          <button type="button" className="btn btn-ghost" style={{ padding: 0, minHeight: 'auto' }} onClick={() => verDocumentacionProveedor(completandoId)}>
                            Ver
                          </button>
                        </>
                      ) : (
                        'Se puede adjuntar ahora o más tarde.'
                      )}
                    </span>
                  </div>
                  <div className="field field-compact" style={{ flex: 1 }}>
                    <label className="field-label">5. Protocolo del proveedor -- foto o PDF{!completandoId && ' *'} (COAS)</label>
                    <input
                      className="field-input"
                      type="file"
                      accept="image/*,application/pdf"
                      capture="environment"
                      onChange={(e) => setProtocoloProveedor(e.target.files?.[0] || null)}
                      disabled={guardando}
                    />
                    <span style={{ fontSize: 'var(--fs-xs)', color: 'var(--ink-3)' }}>
                      {protocoloProveedor ? (
                        protocoloProveedor.name
                      ) : protocoloProveedorActual ? (
                        <>
                          {protocoloProveedorActual}{' '}
                          <button type="button" className="btn btn-ghost" style={{ padding: 0, minHeight: 'auto' }} onClick={() => verProtocoloProveedor(completandoId)}>
                            Ver
                          </button>
                        </>
                      ) : completandoId ? (
                        'Todavía no tiene protocolo cargado'
                      ) : null}
                    </span>
                  </div>
                </div>

                <div style={{ display: 'flex', gap: 'var(--sp-3)' }}>
                  <div className="field field-compact" style={{ flex: 1 }}>
                    <label className="field-label">
                      6. Lote del proveedor{!completandoId && material?.CODSAR === '0006' && ' (opcional -- material sin codificar)'}
                    </label>
                    <input
                      className="field-input"
                      value={loteProveedor}
                      onChange={(e) => setLoteProveedor(e.target.value)}
                      disabled={guardando}
                    />
                  </div>
                  <div className="field field-compact" style={{ flex: 1 }}>
                    <label className="field-label">7. Fecha de vencimiento del lote del proveedor</label>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--sp-2)' }}>
                      <input
                        className="field-input"
                        style={{ flex: 1 }}
                        type="date"
                        value={fechaVencimiento}
                        onChange={(e) => setFechaVencimiento(e.target.value)}
                        disabled={guardando || sinVencimientoIngresoConfirmado}
                      />
                      <label style={{ display: 'flex', alignItems: 'center', gap: '3px', fontSize: 'var(--fs-xs)', whiteSpace: 'nowrap' }}>
                        <input
                          type="checkbox"
                          checked={sinVencimientoIngresoConfirmado}
                          onChange={(e) => {
                            setSinVencimientoIngresoConfirmado(e.target.checked);
                            if (e.target.checked) setFechaVencimiento('');
                          }}
                          disabled={guardando}
                        />
                        Sin venc.
                      </label>
                    </div>
                  </div>
                  <div className="field field-compact" style={{ flex: 1 }}>
                    <label className="field-label">8. Fecha de reanálisis del lote (opcional)</label>
                    <input
                      className="field-input"
                      type="date"
                      value={fechaReanalisis}
                      onChange={(e) => setFechaReanalisis(e.target.value)}
                      disabled={guardando}
                    />
                  </div>
                </div>

                <div style={{ display: 'flex', gap: 'var(--sp-3)' }}>
                  <div className="field field-compact" style={{ flex: 1 }}>
                    <label className="field-label">9. País de origen (opcional)</label>
                    <input
                      className="field-input"
                      value={paisOrigen}
                      onChange={(e) => setPaisOrigen(e.target.value)}
                      disabled={guardando}
                    />
                  </div>
                  <div className="field field-compact" style={{ flex: 1 }}>
                    <label className="field-label">10. N° de bultos (opcional)</label>
                    <input
                      className="field-input"
                      type="number"
                      step="1"
                      value={nroBultos}
                      onChange={(e) => setNroBultos(e.target.value)}
                      disabled={guardando}
                    />
                  </div>
                  <div className="field field-compact" style={{ flex: 1 }}>
                    <label className="field-label">11. Método de análisis (opcional)</label>
                    <input
                      className="field-input"
                      value={metodologiaAnalisis}
                      onChange={(e) => setMetodologiaAnalisis(e.target.value)}
                      disabled={guardando}
                    />
                  </div>
                </div>

                <GruposBultos grupos={gruposBultos} onChange={setGruposBultos} disabled={guardando} />

                <div style={{ display: 'flex', gap: 'var(--sp-3)' }}>
                  <div className="field field-compact" style={{ flex: 1 }}>
                    <label className="field-label">12. Fabricante (opcional)</label>
                    <input
                      className="field-input"
                      value={fabricante}
                      onChange={(e) => setFabricante(e.target.value)}
                      disabled={guardando}
                    />
                  </div>
                  <div className="field field-compact" style={{ flex: 1 }}>
                    <label className="field-label">13. Recibió (opcional)</label>
                    <select
                      className="field-input"
                      value={idUsuarioRecibio}
                      onChange={(e) => setIdUsuarioRecibio(e.target.value)}
                      disabled={guardando}
                    >
                      <option value="">Seleccioná un usuario...</option>
                      {usuariosActivos.map((u) => (
                        <option key={u.id_usuario} value={u.id_usuario}>{u.nombre_completo}</option>
                      ))}
                    </select>
                  </div>
                  <div className="field field-compact" style={{ flex: 1 }}>
                    <label className="field-label">14. Rotuló (opcional)</label>
                    <select
                      className="field-input"
                      value={idUsuarioRotulo}
                      onChange={(e) => setIdUsuarioRotulo(e.target.value)}
                      disabled={guardando}
                    >
                      <option value="">Seleccioná un usuario...</option>
                      {usuariosActivos.map((u) => (
                        <option key={u.id_usuario} value={u.id_usuario}>{u.nombre_completo}</option>
                      ))}
                    </select>
                  </div>
                </div>

                <div className="field field-compact" style={{ marginBottom: 0 }}>
                  <label className="field-label">15. Observaciones (opcional)</label>
                  <textarea
                    className="field-input"
                    style={{ height: 36, paddingTop: '6px' }}
                    value={observaciones}
                    onChange={(e) => setObservaciones(e.target.value)}
                    disabled={guardando}
                  />
                </div>
              </>
            )}

            {errorForm && <div className="alert alert-danger" style={{ marginTop: 'var(--sp-3)' }}>{errorForm}</div>}

            <div style={{ display: 'flex', gap: 'var(--sp-3)', marginTop: 'var(--sp-2)' }}>
              <button type="button" className="btn btn-ghost" onClick={cerrarModal} disabled={guardando}>Cancelar</button>
              <button
                type="submit"
                className="btn btn-primary"
                disabled={
                  guardando || (!completandoId && (
                    !especificacion || !idMuestreador || !material?.proveedor_codigo
                    || (material?.CODSAR !== '0006' && !loteProveedor.trim())
                    || !protocoloProveedor
                  ))
                }
              >
                {guardando ? <span className="spinner" /> : completandoId ? 'Guardar' : 'Generar solicitud'}
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
              <>
                <div className="alert alert-warn" style={{ marginBottom: 'var(--sp-3)' }}>
                  Verificá que la impresora tenga cargado el rollo de etiquetas BLANCAS antes de continuar.
                </div>
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
              </>
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

    </div>
  );
}
