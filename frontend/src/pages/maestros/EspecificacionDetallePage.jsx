import { useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { useAuth } from '../../context/AuthContext';
import TopBar from '../../components/TopBar';
import { maestrosApi } from '../../api/maestros';
import { muestrasApi } from '../../api/muestras';
import { materialesApi } from '../../api/materiales';
import { empaqueIaApi } from '../../api/empaqueIa';
import { ApiError } from '../../api/client';

const TIPOS_MATERIAL = [
  { value: 'materia_prima', label: 'Materia Prima' },
  { value: 'granel', label: 'Granel' },
  { value: 'semi_elaborado', label: 'Semi-Elaborado' },
  { value: 'producto_terminado', label: 'Producto Terminado' },
  { value: 'material_empaque', label: 'Material de Empaque' },
];

function formatearEspecificacion(en) {
  if (en.tipo_dato === 'numerico') {
    const unidad = en.unidad_medida ? ` ${en.unidad_medida}` : '';
    if (en.limite_inferior != null && en.limite_superior != null) {
      return `${en.limite_inferior} – ${en.limite_superior}${unidad}`;
    }
    if (en.limite_superior != null) {
      return `≤ ${en.limite_superior}${unidad}`;
    }
    if (en.limite_inferior != null) {
      return `≥ ${en.limite_inferior}${unidad}`;
    }
    return en.especificacion_texto || '—';
  }
  return en.valor_requerido || en.especificacion_texto || '—';
}

const UNIDADES_MUESTRA = ['g', 'mg', 'ml', 'unidades'];

function formatFechaVencimiento(iso) {
  if (!iso) return 'Sin vencimiento';
  const [anio, mes, dia] = iso.split('-');
  return `${dia}/${mes}/${anio}`;
}

function BadgeEstadoTestigo({ testigo }) {
  if (!testigo.fecha_vencimiento) return <span className="badge badge-neutral">Sin vencimiento</span>;
  if (testigo.vencido) return <span className="badge badge-danger">Vencido</span>;
  if (testigo.por_vencer) return <span className="badge badge-warn">Por vencer</span>;
  return <span className="badge badge-ok">Normal</span>;
}

const BADGE_TIPO_MUESTRA = {
  analisis: 'badge-info',
  contramuestra: 'badge-warn',
  testigo: 'badge-ok',
};

const LABEL_TIPO_MUESTRA = {
  analisis: 'Análisis',
  contramuestra: 'Contramuestra',
  testigo: 'Testigo',
};

const MUESTRA_FORM_VACIO = {
  tipo_muestra: 'analisis',
  cantidad: '',
  unidad: 'g',
  genera_etiqueta: true,
  id_laboratorio: '',
};

const ENSAYO_FORM_VACIO = {
  orden: 1,
  etapa: 'analisis',
  metodologia: '',
  tipo_dato: 'numerico',
  limite_inferior: '',
  limite_superior: '',
  unidad_medida: '',
  valor_requerido: '',
  especificacion_texto: '',
  obligatorio: true,
  requerido_por_defecto: true,
  id_laboratorio: '',
  analito: '',
};

const LABEL_ETAPA = {
  analisis: 'Análisis de laboratorio',
  muestreo: 'Muestreo físico',
};

// "Valoración — Trimetoprima" cuando el mismo ensayo del catálogo se repite
// en la especificación con distinto analito; si no tiene analito cargado,
// se muestra tal cual (sin guion ni espacio de más).
function nombreConAnalito(en) {
  return en.analito ? `${en.nombre_ensayo} — ${en.analito}` : en.nombre_ensayo;
}

export default function EspecificacionDetallePage() {
  const { id } = useParams();
  const navigate = useNavigate();
  const { user } = useAuth();
  const puedeGestionar = ['analista_qc', 'qa', 'admin'].includes(user?.rol);

  const [especificacion, setEspecificacion] = useState(null);
  const [ensayos, setEnsayos] = useState([]);
  const [etapaActiva, setEtapaActiva] = useState('analisis');
  const [muestrasDefinidas, setMuestrasDefinidas] = useState([]);
  const [laboratorios, setLaboratorios] = useState([]);
  const [testigosAsociados, setTestigosAsociados] = useState([]);
  const [testigosDisponibles, setTestigosDisponibles] = useState([]);
  const [idTestigoNuevo, setIdTestigoNuevo] = useState('');
  const [errorTestigos, setErrorTestigos] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);

  // ── Modal de agregar/editar ensayo ──────────────────────────────
  const [modalAbierto, setModalAbierto] = useState(false);
  const [editandoIdEspecEnsayo, setEditandoIdEspecEnsayo] = useState(null);
  const [catalogoBuscar, setCatalogoBuscar] = useState('');
  const [catalogoResultados, setCatalogoResultados] = useState([]);
  const [ensayoMaestroElegido, setEnsayoMaestroElegido] = useState(null);
  const [nombreNuevoEnsayo, setNombreNuevoEnsayo] = useState('');
  const [formEnsayo, setFormEnsayo] = useState(ENSAYO_FORM_VACIO);
  const [errorEnsayo, setErrorEnsayo] = useState('');
  const [guardandoEnsayo, setGuardandoEnsayo] = useState(false);

  // ── Modal de agregar/editar muestra definida ────────────────────
  const [muestraModalAbierto, setMuestraModalAbierto] = useState(false);
  const [editandoIdMuestra, setEditandoIdMuestra] = useState(null);
  const [formMuestra, setFormMuestra] = useState(MUESTRA_FORM_VACIO);
  const [errorMuestra, setErrorMuestra] = useState('');
  const [guardandoMuestra, setGuardandoMuestra] = useState(false);

  // ── Modal de copiar como nueva especificación ───────────────────
  const [copiarModalAbierto, setCopiarModalAbierto] = useState(false);
  const [copiarTipo, setCopiarTipo] = useState('');
  const [copiarNombre, setCopiarNombre] = useState('');
  const [copiarVersion, setCopiarVersion] = useState('1.0');
  const [copiarArticuloBuscar, setCopiarArticuloBuscar] = useState('');
  const [copiarArticulos, setCopiarArticulos] = useState([]);
  const [copiarArticuloElegido, setCopiarArticuloElegido] = useState(null);
  const [errorCopiar, setErrorCopiar] = useState('');
  const [guardandoCopia, setGuardandoCopia] = useState(false);

  // ── Imagen de referencia (Comparación de etiquetas con IA) ──────
  const [referencia, setReferencia] = useState(null); // null = todavía no se buscó / sin referencia
  const [referenciaImagenUrl, setReferenciaImagenUrl] = useState(null);
  const [subiendoReferencia, setSubiendoReferencia] = useState(false);
  const [errorReferencia, setErrorReferencia] = useState('');

  const puedeEditarEnsayos = puedeGestionar && especificacion?.vigente;

  function cargarTestigosAsociados() {
    return maestrosApi.listarTestigosEspecificacion(id).then(setTestigosAsociados);
  }

  function cargarEnsayos() {
    return maestrosApi.listarEnsayosEspecificacion(id).then(setEnsayos);
  }

  function ensayosDeEtapa(etapa) {
    return ensayos.filter((en) => (en.etapa || 'analisis') === etapa);
  }

  function cargarMuestrasDefinidas() {
    return maestrosApi.listarMuestrasEspecificacion(id).then(setMuestrasDefinidas);
  }

  useEffect(() => {
    setLoading(true);
    Promise.all([
      maestrosApi.obtenerEspecificacion(id).then(setEspecificacion),
      cargarEnsayos(),
      cargarMuestrasDefinidas(),
      cargarTestigosAsociados(),
      maestrosApi.listarTestigos({ activo: true }).then(setTestigosDisponibles),
      muestrasApi.listarLaboratorios(true).then(setLaboratorios),
    ])
      .catch((err) => setError(err instanceof ApiError ? err.message : 'No se pudo cargar la especificación'))
      .finally(() => setLoading(false));
  }, [id]);

  function cargarReferencia(erpCodart) {
    empaqueIaApi
      .obtenerReferencia(erpCodart)
      .then((r) => {
        setReferencia(r);
        return empaqueIaApi.imagenReferenciaBlob(erpCodart);
      })
      .then((blob) => setReferenciaImagenUrl((prev) => { if (prev) URL.revokeObjectURL(prev); return URL.createObjectURL(blob); }))
      .catch((err) => {
        if (err instanceof ApiError && err.status === 404) {
          setReferencia('none');
          setReferenciaImagenUrl(null);
        }
      });
  }

  useEffect(() => {
    if (especificacion?.tipo_material === 'material_empaque') {
      cargarReferencia(especificacion.erp_CODART);
    }
    return () => {
      setReferenciaImagenUrl((prev) => { if (prev) URL.revokeObjectURL(prev); return null; });
    };
  }, [especificacion?.tipo_material, especificacion?.erp_CODART]);

  async function handleSubirReferencia(e) {
    const archivo = e.target.files?.[0];
    e.target.value = '';
    if (!archivo) return;
    setSubiendoReferencia(true);
    setErrorReferencia('');
    try {
      await empaqueIaApi.subirReferencia(especificacion.erp_CODART, archivo);
      cargarReferencia(especificacion.erp_CODART);
    } catch (err) {
      setErrorReferencia(err instanceof ApiError ? err.message : 'No se pudo subir la imagen de referencia');
    } finally {
      setSubiendoReferencia(false);
    }
  }

  useEffect(() => {
    if (!modalAbierto || ensayoMaestroElegido || catalogoBuscar.trim().length < 2) {
      setCatalogoResultados([]);
      return;
    }
    const timer = setTimeout(() => {
      maestrosApi.listarEnsayosMaestro(catalogoBuscar).then(setCatalogoResultados).catch(() => setCatalogoResultados([]));
    }, 300);
    return () => clearTimeout(timer);
  }, [catalogoBuscar, modalAbierto, ensayoMaestroElegido]);

  useEffect(() => {
    if (!copiarModalAbierto || copiarArticuloElegido || copiarArticuloBuscar.trim().length < 2) {
      setCopiarArticulos([]);
      return;
    }
    const timer = setTimeout(() => {
      materialesApi.buscarMateriales(copiarTipo, copiarArticuloBuscar).then(setCopiarArticulos).catch(() => setCopiarArticulos([]));
    }, 300);
    return () => clearTimeout(timer);
  }, [copiarArticuloBuscar, copiarModalAbierto, copiarArticuloElegido, copiarTipo]);

  async function handleAsociarTestigo() {
    if (!idTestigoNuevo) return;
    setErrorTestigos('');
    try {
      await maestrosApi.asociarTestigoEspecificacion(id, Number(idTestigoNuevo));
      setIdTestigoNuevo('');
      await cargarTestigosAsociados();
    } catch (err) {
      setErrorTestigos(err instanceof ApiError ? err.message : 'No se pudo asociar el testigo');
    }
  }

  async function handleDesasociarTestigo(idTestigo) {
    setErrorTestigos('');
    try {
      await maestrosApi.desasociarTestigoEspecificacion(id, idTestigo);
      await cargarTestigosAsociados();
    } catch (err) {
      setErrorTestigos(err instanceof ApiError ? err.message : 'No se pudo quitar el testigo');
    }
  }

  function abrirAgregarEnsayo() {
    setEditandoIdEspecEnsayo(null);
    setEnsayoMaestroElegido(null);
    setCatalogoBuscar('');
    setCatalogoResultados([]);
    setNombreNuevoEnsayo('');
    setFormEnsayo({
      ...ENSAYO_FORM_VACIO,
      etapa: etapaActiva,
      tipo_dato: etapaActiva === 'muestreo' ? 'cualitativo' : 'numerico',
      orden: ensayosDeEtapa(etapaActiva).length + 1,
    });
    setErrorEnsayo('');
    setModalAbierto(true);
  }

  function abrirEditarEnsayo(en) {
    setEditandoIdEspecEnsayo(en.id_espec_ensayo);
    setEnsayoMaestroElegido({ id_ensayo_maestro: en.id_ensayo_maestro, nombre_ensayo: en.nombre_ensayo });
    setCatalogoBuscar('');
    setCatalogoResultados([]);
    setNombreNuevoEnsayo('');
    setFormEnsayo({
      orden: en.orden,
      etapa: en.etapa || 'analisis',
      metodologia: en.metodologia || '',
      tipo_dato: en.tipo_dato,
      limite_inferior: en.limite_inferior ?? '',
      limite_superior: en.limite_superior ?? '',
      unidad_medida: en.unidad_medida || '',
      valor_requerido: en.valor_requerido || '',
      especificacion_texto: en.especificacion_texto || '',
      obligatorio: en.obligatorio,
      requerido_por_defecto: en.requerido_por_defecto,
      id_laboratorio: en.id_laboratorio ?? '',
      analito: en.analito || '',
    });
    setErrorEnsayo('');
    setModalAbierto(true);
  }

  function cerrarModal() {
    setModalAbierto(false);
  }

  async function handleCrearEnsayoCatalogo() {
    if (!nombreNuevoEnsayo.trim()) return;
    setErrorEnsayo('');
    try {
      const creado = await maestrosApi.crearEnsayoMaestro({ nombre_ensayo: nombreNuevoEnsayo.trim() });
      setEnsayoMaestroElegido(creado);
      setCatalogoResultados([]);
    } catch (err) {
      setErrorEnsayo(err instanceof ApiError ? err.message : 'No se pudo crear el ensayo en el catálogo');
    }
  }

  async function handleGuardarEnsayo(e) {
    e.preventDefault();
    if (!ensayoMaestroElegido) {
      setErrorEnsayo('Elegí un ensayo del catálogo o creá uno nuevo');
      return;
    }
    if (formEnsayo.tipo_dato === 'numerico' && formEnsayo.limite_inferior === '' && formEnsayo.limite_superior === '') {
      setErrorEnsayo('Necesita al menos un límite (inferior o superior)');
      return;
    }
    if (formEnsayo.tipo_dato === 'cualitativo' && !formEnsayo.valor_requerido.trim()) {
      setErrorEnsayo('Necesita el valor cualitativo requerido');
      return;
    }

    const body = {
      id_ensayo_maestro: ensayoMaestroElegido.id_ensayo_maestro,
      orden: Number(formEnsayo.orden),
      etapa: formEnsayo.etapa,
      metodologia: formEnsayo.metodologia.trim() || null,
      tipo_dato: formEnsayo.tipo_dato,
      limite_inferior: formEnsayo.tipo_dato === 'numerico' && formEnsayo.limite_inferior !== '' ? Number(formEnsayo.limite_inferior) : null,
      limite_superior: formEnsayo.tipo_dato === 'numerico' && formEnsayo.limite_superior !== '' ? Number(formEnsayo.limite_superior) : null,
      unidad_medida: formEnsayo.unidad_medida.trim() || null,
      valor_requerido: formEnsayo.tipo_dato === 'cualitativo' ? formEnsayo.valor_requerido.trim() : null,
      especificacion_texto: formEnsayo.especificacion_texto.trim() || null,
      obligatorio: formEnsayo.obligatorio,
      requerido_por_defecto: formEnsayo.requerido_por_defecto,
      id_laboratorio: formEnsayo.etapa === 'muestreo' || formEnsayo.id_laboratorio === '' ? null : Number(formEnsayo.id_laboratorio),
      analito: formEnsayo.analito.trim() || null,
    };

    setGuardandoEnsayo(true);
    setErrorEnsayo('');
    try {
      if (editandoIdEspecEnsayo) {
        await maestrosApi.editarEnsayoEspecificacion(id, editandoIdEspecEnsayo, body);
      } else {
        await maestrosApi.agregarEnsayoEspecificacion(id, body);
      }
      await cargarEnsayos();
      setModalAbierto(false);
    } catch (err) {
      setErrorEnsayo(err instanceof ApiError ? err.message : 'No se pudo guardar el ensayo');
    } finally {
      setGuardandoEnsayo(false);
    }
  }

  async function handleEliminarEnsayo(en) {
    if (!window.confirm(`¿Quitar el ensayo "${nombreConAnalito(en)}" de esta especificación?`)) return;
    try {
      await maestrosApi.eliminarEnsayoEspecificacion(id, en.id_espec_ensayo);
      await cargarEnsayos();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'No se pudo quitar el ensayo');
    }
  }

  function abrirAgregarMuestra() {
    setEditandoIdMuestra(null);
    setFormMuestra(MUESTRA_FORM_VACIO);
    setErrorMuestra('');
    setMuestraModalAbierto(true);
  }

  function abrirEditarMuestra(m) {
    setEditandoIdMuestra(m.id);
    setFormMuestra({
      tipo_muestra: m.tipo_muestra,
      cantidad: m.cantidad,
      unidad: m.unidad,
      genera_etiqueta: m.genera_etiqueta,
      id_laboratorio: m.id_laboratorio ?? '',
    });
    setErrorMuestra('');
    setMuestraModalAbierto(true);
  }

  function cerrarModalMuestra() {
    setMuestraModalAbierto(false);
  }

  async function handleGuardarMuestra(e) {
    e.preventDefault();
    if (formMuestra.cantidad === '' || Number(formMuestra.cantidad) <= 0) {
      setErrorMuestra('Ingresá una cantidad válida');
      return;
    }
    const body = {
      tipo_muestra: formMuestra.tipo_muestra,
      cantidad: Number(formMuestra.cantidad),
      unidad: formMuestra.unidad,
      genera_etiqueta: formMuestra.genera_etiqueta,
      id_laboratorio: formMuestra.id_laboratorio !== '' ? Number(formMuestra.id_laboratorio) : null,
    };
    setGuardandoMuestra(true);
    setErrorMuestra('');
    try {
      if (editandoIdMuestra) {
        await maestrosApi.editarMuestraEspecificacion(id, editandoIdMuestra, body);
      } else {
        await maestrosApi.crearMuestraEspecificacion(id, body);
      }
      await cargarMuestrasDefinidas();
      setMuestraModalAbierto(false);
    } catch (err) {
      setErrorMuestra(err instanceof ApiError ? err.message : 'No se pudo guardar la muestra');
    } finally {
      setGuardandoMuestra(false);
    }
  }

  async function handleEliminarMuestra(m) {
    if (!window.confirm(`¿Eliminar esta muestra de tipo "${m.tipo_muestra}"?`)) return;
    try {
      await maestrosApi.eliminarMuestraEspecificacion(id, m.id);
      await cargarMuestrasDefinidas();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'No se pudo eliminar la muestra');
    }
  }

  function abrirCopiar() {
    setCopiarTipo(especificacion.tipo_material);
    setCopiarNombre(especificacion.erp_DESART);
    setCopiarVersion('1.0');
    setCopiarArticuloBuscar('');
    setCopiarArticulos([]);
    setCopiarArticuloElegido(null);
    setErrorCopiar('');
    setCopiarModalAbierto(true);
  }

  function cerrarCopiar() {
    setCopiarModalAbierto(false);
  }

  function cambiarCopiarTipo(valor) {
    setCopiarTipo(valor);
    setCopiarArticuloElegido(null);
    setCopiarArticuloBuscar('');
    setCopiarArticulos([]);
  }

  function elegirCopiarArticulo(articulo) {
    setCopiarArticuloElegido(articulo);
    setCopiarNombre(articulo.DESART);
    setCopiarArticuloBuscar('');
    setCopiarArticulos([]);
  }

  async function handleCopiar(e) {
    e.preventDefault();
    if (!copiarArticuloElegido) {
      setErrorCopiar('Buscá y seleccioná el artículo de la nueva especificación');
      return;
    }
    if (!copiarNombre.trim()) {
      setErrorCopiar('El nombre es obligatorio');
      return;
    }
    setErrorCopiar('');
    setGuardandoCopia(true);
    try {
      const nueva = await maestrosApi.copiarEspecificacion(id, {
        erp_IdM21: copiarArticuloElegido.IdM21,
        erp_CODART: copiarArticuloElegido.CODART,
        erp_DESART: copiarNombre.trim(),
        tipo_material: copiarTipo,
        version: copiarVersion.trim() || '1.0',
      });
      navigate(`/maestros/especificaciones/${nueva.id_especificacion}`, { replace: true });
    } catch (err) {
      setErrorCopiar(err instanceof ApiError ? err.message : 'No se pudo copiar la especificación');
    } finally {
      setGuardandoCopia(false);
    }
  }

  if (loading) {
    return (
      <div className="screen" style={{ alignItems: 'center', justifyContent: 'center' }}>
        <span className="spinner" />
      </div>
    );
  }

  // Qué pestañas de etapa mostrar según la config del subarticulo (ver
  // incluye_bloque_analisis_laboratorio/incluye_bloque_muestreo_fisico) --
  // si la etapa activa quedó oculta (ej. cambió la config), se cae a la
  // primera visible en vez de mostrar una pestaña sin botón para volver.
  const etapasVisibles = especificacion
    ? ['analisis', 'muestreo'].filter((etapa) => (
        etapa === 'analisis' ? especificacion.incluye_bloque_analisis_laboratorio : especificacion.incluye_bloque_muestreo_fisico
      ))
    : [];
  const etapaMostrada = etapasVisibles.includes(etapaActiva) ? etapaActiva : etapasVisibles[0];

  if (error || !especificacion) {
    return (
      <div className="screen">
        <TopBar titulo="Especificación" subtitulo="Datos Maestros" onBack={() => navigate(-1)} />
        <div className="screen-content">
          <div className="alert alert-danger">{error || 'No encontrada'}</div>
        </div>
      </div>
    );
  }

  return (
    <div className="screen">
      <TopBar titulo={especificacion.erp_DESART} subtitulo="Ficha de especificación" onBack={() => navigate(-1)} />
      <div className="screen-content">
        <div className="card" style={{ marginBottom: 'var(--sp-5)' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 'var(--sp-3)' }}>
            <div>
              <div style={{ fontFamily: 'var(--font-mono)', color: 'var(--ink-2)', fontSize: 'var(--fs-sm)' }}>
                {especificacion.erp_CODART}
              </div>
              <h1 style={{ fontSize: 'var(--fs-xl)' }}>{especificacion.erp_DESART}</h1>
            </div>
            {especificacion.vigente ? (
              <span className="badge badge-ok">Vigente</span>
            ) : (
              <span className="badge badge-neutral">Obsoleta</span>
            )}
          </div>

          <div style={{ display: 'flex', gap: 'var(--sp-5)', fontSize: 'var(--fs-sm)', color: 'var(--ink-2)' }}>
            <span>Tipo: <strong style={{ color: 'var(--ink-1)' }}>{especificacion.tipo_material.replace('_', ' ')}</strong></span>
            <span>Versión: <strong style={{ color: 'var(--ink-1)' }}>{especificacion.version}</strong></span>
          </div>

          {puedeGestionar && (
            <div style={{ display: 'flex', gap: 'var(--sp-3)', marginTop: 'var(--sp-4)', flexWrap: 'wrap' }}>
              {especificacion.vigente && (
                <button
                  className="btn btn-secondary"
                  onClick={() => navigate(`/maestros/especificaciones/${id}/revisar`)}
                >
                  Revisar (crear nueva versión) →
                </button>
              )}
              <button className="btn btn-secondary" onClick={abrirCopiar}>
                Copiar como nueva especificación
              </button>
            </div>
          )}
        </div>

        {especificacion.tipo_material === 'material_empaque' && (
          <div className="card" style={{ marginBottom: 'var(--sp-5)' }}>
            <h2 style={{ fontSize: 'var(--fs-lg)', marginBottom: 'var(--sp-2)' }}>Imagen de referencia (Comparación con IA)</h2>
            <p style={{ color: 'var(--ink-2)', fontSize: 'var(--fs-sm)', marginBottom: 'var(--sp-3)' }}>
              El arte aprobado de la etiqueta de este artículo -- se usa para comparar contra la foto de la etiqueta
              recibida en cada inspección (ver Carga de Resultados). Es una ayuda visual, no reemplaza el criterio de
              quien inspecciona.
            </p>

            {errorReferencia && <div className="alert alert-danger" style={{ marginBottom: 'var(--sp-3)' }}>{errorReferencia}</div>}

            <div style={{ display: 'flex', gap: 'var(--sp-4)', alignItems: 'flex-start', flexWrap: 'wrap' }}>
              {referencia && referencia !== 'none' && referenciaImagenUrl && (
                <div>
                  <img
                    src={referenciaImagenUrl}
                    alt="Referencia de etiqueta"
                    style={{ maxWidth: 220, maxHeight: 220, border: '1px solid var(--border)', borderRadius: 4 }}
                  />
                  <p style={{ fontSize: 'var(--fs-xs)', color: 'var(--ink-3)', marginTop: 'var(--sp-1)' }}>
                    Subida el {new Date(referencia.fecha_carga).toLocaleString()} por {referencia.usuario_carga_nombre}
                  </p>
                </div>
              )}
              {referencia === 'none' && (
                <div className="state-block" style={{ flex: 1 }}>
                  <span className="state-block-title">Sin imagen de referencia cargada</span>
                </div>
              )}
              {puedeGestionar && (
                <label className="btn btn-secondary" style={{ cursor: subiendoReferencia ? 'default' : 'pointer' }}>
                  {subiendoReferencia ? <span className="spinner" /> : (referencia && referencia !== 'none' ? 'Reemplazar imagen' : 'Subir imagen de referencia')}
                  <input
                    type="file"
                    accept="image/jpeg,image/png,application/pdf"
                    style={{ display: 'none' }}
                    disabled={subiendoReferencia}
                    onChange={handleSubirReferencia}
                  />
                </label>
              )}
            </div>
          </div>
        )}

        {especificacion.incluye_bloque_muestras && (
          <>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 'var(--sp-3)' }}>
              <h2 style={{ fontSize: 'var(--fs-lg)' }}>Muestras definidas ({muestrasDefinidas.length})</h2>
              {puedeGestionar && (
                <button className="btn btn-secondary" onClick={abrirAgregarMuestra}>
                  + Agregar muestra
                </button>
              )}
            </div>
            {muestrasDefinidas.length === 0 ? (
              <div className="alert alert-warn" style={{ marginBottom: 'var(--sp-5)' }}>
                Esta especificación no tiene muestras definidas. Configurá las muestras acá para que estén disponibles al generar una Solicitud de Muestreo.
              </div>
            ) : (
              <table className="data-table data-table-compact" style={{ marginBottom: 'var(--sp-5)' }}>
                <thead>
                  <tr>
                    <th>Tipo</th>
                    <th>Cantidad</th>
                    <th>Unidad</th>
                    <th>Genera etiqueta</th>
                    <th>Laboratorio</th>
                    {puedeGestionar && <th>Acciones</th>}
                  </tr>
                </thead>
                <tbody>
                  {muestrasDefinidas.map((m) => (
                    <tr key={m.id}>
                      <td>
                        <span className={`badge ${BADGE_TIPO_MUESTRA[m.tipo_muestra] || 'badge-neutral'}`}>
                          {LABEL_TIPO_MUESTRA[m.tipo_muestra] || m.tipo_muestra}
                        </span>
                      </td>
                      <td className="num">{m.cantidad}</td>
                      <td>{m.unidad}</td>
                      <td>{m.genera_etiqueta ? '✓' : '—'}</td>
                      <td>{m.laboratorio_nombre || 'Sin asignar'}</td>
                      {puedeGestionar && (
                        <td style={{ whiteSpace: 'nowrap' }}>
                          <button className="btn btn-ghost" onClick={() => abrirEditarMuestra(m)}>Editar</button>
                          <button className="btn btn-ghost" style={{ color: 'var(--danger)', marginLeft: 'var(--sp-2)' }} onClick={() => handleEliminarMuestra(m)}>
                            Eliminar
                          </button>
                        </td>
                      )}
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </>
        )}

        {etapasVisibles.length > 0 && (
          <>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 'var(--sp-3)' }}>
              <div style={{ display: 'flex', gap: 'var(--sp-2)' }}>
                {etapasVisibles.map((etapa) => (
                  <button
                    key={etapa}
                    type="button"
                    className={etapaMostrada === etapa ? 'btn btn-primary' : 'btn btn-secondary'}
                    onClick={() => setEtapaActiva(etapa)}
                  >
                    {LABEL_ETAPA[etapa]} ({ensayosDeEtapa(etapa).length})
                  </button>
                ))}
              </div>
              {puedeEditarEnsayos && (
                <button className="btn btn-secondary" onClick={abrirAgregarEnsayo}>
                  + Agregar ítem
                </button>
              )}
            </div>
            {etapaMostrada === 'muestreo' && (
              <p style={{ color: 'var(--ink-2)', fontSize: 'var(--fs-sm)', marginBottom: 'var(--sp-3)' }}>
                Checklist físico que se revisa al ejecutar el muestreo (Cumple/No cumple) -- ver Orden de Trabajo digital.
              </p>
            )}
            <table className="data-table data-table-compact" style={{ marginBottom: 'var(--sp-5)' }}>
              <thead>
                <tr>
                  <th style={{ textAlign: 'center' }}>Orden</th>
                  <th>Nombre del ensayo</th>
                  <th>Metodología</th>
                  <th>Tipo</th>
                  <th>Especificación/Límites</th>
                  <th>Unidad</th>
                  <th>Laboratorio</th>
                  {puedeEditarEnsayos && <th>Acciones</th>}
                </tr>
              </thead>
              <tbody>
                {ensayosDeEtapa(etapaMostrada).map((en) => (
                  <tr key={en.id_espec_ensayo}>
                    <td style={{ textAlign: 'center' }}>{en.orden}</td>
                    <td>{nombreConAnalito(en)}</td>
                    <td>{en.metodologia || '—'}</td>
                    <td>
                      {en.tipo_dato === 'numerico' ? (
                        <span className="badge badge-info">Numérico</span>
                      ) : (
                        <span className="badge badge-neutral">Cualitativo</span>
                      )}
                    </td>
                    <td>{formatearEspecificacion(en)}</td>
                    <td>{en.tipo_dato === 'numerico' ? (en.unidad_medida || '—') : '—'}</td>
                    <td>{en.etapa === 'muestreo' ? 'N/A' : (en.laboratorio_nombre || '—')}</td>
                    {puedeEditarEnsayos && (
                      <td style={{ whiteSpace: 'nowrap' }}>
                        <button className="btn btn-ghost" onClick={() => abrirEditarEnsayo(en)}>Editar</button>
                        <button className="btn btn-ghost" style={{ color: 'var(--danger)', marginLeft: 'var(--sp-2)' }} onClick={() => handleEliminarEnsayo(en)}>
                          Eliminar
                        </button>
                      </td>
                    )}
                  </tr>
                ))}
                {ensayosDeEtapa(etapaMostrada).length === 0 && (
                  <tr>
                    <td colSpan={puedeEditarEnsayos ? 8 : 7} style={{ textAlign: 'center', color: 'var(--ink-2)' }}>
                      Sin ítems configurados para {LABEL_ETAPA[etapaMostrada].toLowerCase()}.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </>
        )}

        {especificacion.incluye_bloque_testigos && (
          <>
            <h2 style={{ fontSize: 'var(--fs-lg)', margin: 'var(--sp-5) 0 var(--sp-3)' }}>
              Testigos asociados ({testigosAsociados.length})
            </h2>
            <div className="card" style={{ marginBottom: 'var(--sp-5)' }}>
              {testigosAsociados.length === 0 ? (
                <p style={{ color: 'var(--ink-2)' }}>Ningún testigo asociado todavía.</p>
              ) : (
                <table className="data-table" style={{ marginBottom: puedeGestionar ? 'var(--sp-4)' : 0 }}>
                  <thead>
                    <tr>
                      <th>Código</th>
                      <th>Nombre</th>
                      <th>Vencimiento</th>
                      <th>Estado</th>
                      <th>Stock</th>
                      {puedeGestionar && <th></th>}
                    </tr>
                  </thead>
                  <tbody>
                    {testigosAsociados.map((t) => (
                      <tr key={t.id_testigo}>
                        <td style={{ textAlign: 'left', fontFamily: 'var(--font-mono)' }}>{t.codigo}</td>
                        <td style={{ textAlign: 'left' }}>{t.nombre}</td>
                        <td style={{ textAlign: 'left' }}>{formatFechaVencimiento(t.fecha_vencimiento)}</td>
                        <td style={{ textAlign: 'left' }}><BadgeEstadoTestigo testigo={t} /></td>
                        <td style={{ textAlign: 'left' }}>{t.stock_actual != null ? `${t.stock_actual} ${t.unidad_medida || ''}` : '—'}</td>
                        {puedeGestionar && (
                          <td style={{ textAlign: 'left' }}>
                            <button className="btn btn-ghost" style={{ color: 'var(--danger)' }} onClick={() => handleDesasociarTestigo(t.id_testigo)}>
                              Quitar
                            </button>
                          </td>
                        )}
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}

              {puedeGestionar && (
                <div style={{ display: 'flex', gap: 'var(--sp-3)' }}>
                  <select className="field-input" style={{ flex: 1 }} value={idTestigoNuevo} onChange={(e) => setIdTestigoNuevo(e.target.value)}>
                    <option value="">Seleccioná un testigo para asociar...</option>
                    {testigosDisponibles
                      .filter((t) => !testigosAsociados.some((ta) => ta.id_testigo === t.id_testigo))
                      .map((t) => (
                        <option key={t.id_testigo} value={t.id_testigo}>{t.codigo} — {t.nombre}</option>
                      ))}
                  </select>
                  <button type="button" className="btn btn-secondary" disabled={!idTestigoNuevo} onClick={handleAsociarTestigo}>
                    Asociar
                  </button>
                </div>
              )}

              {errorTestigos && <div className="alert alert-danger" style={{ marginTop: 'var(--sp-3)' }}>{errorTestigos}</div>}
            </div>
          </>
        )}
      </div>

      {modalAbierto && (
        <div
          style={{
            position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.5)',
            display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 100, padding: 'var(--sp-4)',
          }}
          onClick={cerrarModal}
        >
          <form
            onSubmit={handleGuardarEnsayo}
            className="card"
            style={{ width: '90%', maxWidth: 640, maxHeight: '90vh', overflowY: 'auto' }}
            onClick={(e) => e.stopPropagation()}
          >
            <h2 style={{ fontSize: 'var(--fs-lg)', marginBottom: 'var(--sp-3)' }}>
              {editandoIdEspecEnsayo ? 'Editar ensayo' : 'Agregar ensayo'}
            </h2>

            {!ensayoMaestroElegido ? (
              <div className="field">
                <label className="field-label">Buscar en el catálogo de ensayos</label>
                <input
                  className="field-input"
                  placeholder="Ej. pH, Aspecto, Valoración..."
                  value={catalogoBuscar}
                  onChange={(e) => setCatalogoBuscar(e.target.value)}
                  autoFocus
                />
                {catalogoResultados.length > 0 && (
                  <div className="select-list" style={{ marginTop: 'var(--sp-2)' }}>
                    {catalogoResultados.map((em) => (
                      <button
                        type="button"
                        key={em.id_ensayo_maestro}
                        className="select-item"
                        onClick={() => setEnsayoMaestroElegido(em)}
                      >
                        <span className="select-item-title">{em.nombre_ensayo}</span>
                      </button>
                    ))}
                  </div>
                )}
                {catalogoBuscar.trim().length >= 2 && catalogoResultados.length === 0 && (
                  <div style={{ marginTop: 'var(--sp-3)' }}>
                    <p style={{ color: 'var(--ink-2)', fontSize: 'var(--fs-sm)', marginBottom: 'var(--sp-2)' }}>
                      No se encontró ningún ensayo con ese nombre en el catálogo.
                    </p>
                    <div style={{ display: 'flex', gap: 'var(--sp-2)' }}>
                      <input
                        className="field-input"
                        placeholder="Nombre del ensayo nuevo"
                        value={nombreNuevoEnsayo}
                        onChange={(e) => setNombreNuevoEnsayo(e.target.value)}
                      />
                      <button type="button" className="btn btn-secondary" onClick={handleCrearEnsayoCatalogo}>
                        Crear nuevo
                      </button>
                    </div>
                  </div>
                )}
              </div>
            ) : (
              <>
                <div className="select-item select-item-active" style={{ marginBottom: 'var(--sp-3)' }}>
                  <span className="select-item-title">{ensayoMaestroElegido.nombre_ensayo}</span>
                  {!editandoIdEspecEnsayo && (
                    <button type="button" className="btn btn-ghost" onClick={() => setEnsayoMaestroElegido(null)}>
                      Cambiar
                    </button>
                  )}
                </div>

                <div style={{ display: 'flex', gap: 'var(--sp-3)', flexWrap: 'wrap' }}>
                  <div className="field" style={{ flex: '1 1 160px' }}>
                    <label className="field-label">Etapa</label>
                    <select
                      className="field-input"
                      value={formEnsayo.etapa}
                      onChange={(e) => {
                        const etapa = e.target.value;
                        setFormEnsayo((prev) => ({
                          ...prev,
                          etapa,
                          tipo_dato: etapa === 'muestreo' ? 'cualitativo' : prev.tipo_dato,
                          id_laboratorio: etapa === 'muestreo' ? '' : prev.id_laboratorio,
                        }));
                      }}
                    >
                      <option value="analisis">Análisis de laboratorio</option>
                      <option value="muestreo">Muestreo físico</option>
                    </select>
                  </div>
                  <div className="field" style={{ flex: '2 1 220px' }}>
                    <label className="field-label">Analito (opcional)</label>
                    <input
                      className="field-input"
                      placeholder='Ej. "Trimetoprima" -- para diferenciar si este ensayo se repite'
                      value={formEnsayo.analito}
                      onChange={(e) => setFormEnsayo((prev) => ({ ...prev, analito: e.target.value }))}
                    />
                  </div>
                  <div className="field" style={{ flex: '1 1 100px' }}>
                    <label className="field-label">Orden</label>
                    <input
                      className="field-input"
                      type="number"
                      value={formEnsayo.orden}
                      onChange={(e) => setFormEnsayo((prev) => ({ ...prev, orden: e.target.value }))}
                    />
                  </div>
                  <div className="field" style={{ flex: '1 1 160px' }}>
                    <label className="field-label">Tipo de dato</label>
                    <select
                      className="field-input"
                      value={formEnsayo.tipo_dato}
                      onChange={(e) => setFormEnsayo((prev) => ({ ...prev, tipo_dato: e.target.value }))}
                    >
                      <option value="numerico">Numérico</option>
                      <option value="cualitativo">Cualitativo</option>
                    </select>
                  </div>
                </div>

                {formEnsayo.tipo_dato === 'numerico' ? (
                  <div style={{ display: 'flex', gap: 'var(--sp-3)', flexWrap: 'wrap' }}>
                    <div className="field" style={{ flex: '1 1 160px' }}>
                      <label className="field-label">Límite inferior</label>
                      <input
                        className="field-input"
                        type="number"
                        step="any"
                        value={formEnsayo.limite_inferior}
                        onChange={(e) => setFormEnsayo((prev) => ({ ...prev, limite_inferior: e.target.value }))}
                      />
                    </div>
                    <div className="field" style={{ flex: '1 1 160px' }}>
                      <label className="field-label">Límite superior</label>
                      <input
                        className="field-input"
                        type="number"
                        step="any"
                        value={formEnsayo.limite_superior}
                        onChange={(e) => setFormEnsayo((prev) => ({ ...prev, limite_superior: e.target.value }))}
                      />
                    </div>
                    <div className="field" style={{ flex: '1 1 160px' }}>
                      <label className="field-label">Unidad</label>
                      <input
                        className="field-input"
                        placeholder="%, g/mL, pH..."
                        value={formEnsayo.unidad_medida}
                        onChange={(e) => setFormEnsayo((prev) => ({ ...prev, unidad_medida: e.target.value }))}
                      />
                    </div>
                  </div>
                ) : (
                  <div className="field">
                    <label className="field-label">Valor exacto requerido</label>
                    <input
                      className="field-input"
                      placeholder='Ej. "Polvo cristalino blanco"'
                      value={formEnsayo.valor_requerido}
                      onChange={(e) => setFormEnsayo((prev) => ({ ...prev, valor_requerido: e.target.value }))}
                    />
                  </div>
                )}

                <div className="field">
                  <label className="field-label">Metodología</label>
                  <input
                    className="field-input"
                    placeholder="Ej. USP, PE, Interna M-04"
                    value={formEnsayo.metodologia}
                    onChange={(e) => setFormEnsayo((prev) => ({ ...prev, metodologia: e.target.value }))}
                  />
                </div>

                <div className="field">
                  <label className="field-label">Especificación (texto libre, opcional)</label>
                  <input
                    className="field-input"
                    placeholder="Notas de la especificación para este ensayo"
                    value={formEnsayo.especificacion_texto}
                    onChange={(e) => setFormEnsayo((prev) => ({ ...prev, especificacion_texto: e.target.value }))}
                  />
                </div>

                {formEnsayo.etapa !== 'muestreo' && (
                  <div className="field">
                    <label className="field-label">Laboratorio</label>
                    <select
                      className="field-input"
                      value={formEnsayo.id_laboratorio}
                      onChange={(e) => setFormEnsayo((prev) => ({ ...prev, id_laboratorio: e.target.value }))}
                    >
                      <option value="">(sin asignar)</option>
                      {laboratorios.map((lab) => (
                        <option key={lab.id_laboratorio} value={lab.id_laboratorio}>{lab.nombre}</option>
                      ))}
                    </select>
                  </div>
                )}

                <div style={{ display: 'flex', gap: 'var(--sp-4)', flexWrap: 'wrap', marginTop: 'var(--sp-2)', marginBottom: 'var(--sp-3)' }}>
                  <label style={{ display: 'flex', alignItems: 'center', gap: 'var(--sp-2)' }}>
                    <input
                      type="checkbox"
                      checked={formEnsayo.obligatorio}
                      onChange={(e) => setFormEnsayo((prev) => ({ ...prev, obligatorio: e.target.checked }))}
                    />
                    Obligatorio
                  </label>
                  <label style={{ display: 'flex', alignItems: 'center', gap: 'var(--sp-2)' }}>
                    <input
                      type="checkbox"
                      checked={formEnsayo.requerido_por_defecto}
                      onChange={(e) => setFormEnsayo((prev) => ({ ...prev, requerido_por_defecto: e.target.checked }))}
                    />
                    Requerido por defecto al confirmar el envío
                  </label>
                </div>
              </>
            )}

            {errorEnsayo && <div className="alert alert-danger" style={{ marginTop: 'var(--sp-3)' }}>{errorEnsayo}</div>}

            <div style={{ display: 'flex', gap: 'var(--sp-3)', marginTop: 'var(--sp-4)' }}>
              <button type="button" className="btn btn-ghost" onClick={cerrarModal} disabled={guardandoEnsayo}>Cancelar</button>
              <button type="submit" className="btn btn-primary" disabled={guardandoEnsayo || !ensayoMaestroElegido}>
                {guardandoEnsayo ? <span className="spinner" /> : 'Guardar'}
              </button>
            </div>
          </form>
        </div>
      )}

      {muestraModalAbierto && (
        <div
          style={{
            position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.5)',
            display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 100, padding: 'var(--sp-4)',
          }}
          onClick={cerrarModalMuestra}
        >
          <form
            onSubmit={handleGuardarMuestra}
            className="card"
            style={{ width: '90%', maxWidth: 480, maxHeight: '90vh', overflowY: 'auto' }}
            onClick={(e) => e.stopPropagation()}
          >
            <h2 style={{ fontSize: 'var(--fs-lg)', marginBottom: 'var(--sp-3)' }}>
              {editandoIdMuestra ? 'Editar muestra' : 'Agregar muestra'}
            </h2>

            <div className="field">
              <label className="field-label">Tipo</label>
              <select
                className="field-input"
                value={formMuestra.tipo_muestra}
                onChange={(e) => setFormMuestra((prev) => ({ ...prev, tipo_muestra: e.target.value }))}
              >
                <option value="analisis">Análisis</option>
                <option value="contramuestra">Contramuestra</option>
                <option value="testigo">Testigo</option>
              </select>
            </div>

            <div style={{ display: 'flex', gap: 'var(--sp-3)' }}>
              <div className="field" style={{ flex: 1 }}>
                <label className="field-label">Cantidad</label>
                <input
                  className="field-input"
                  type="number"
                  step="any"
                  value={formMuestra.cantidad}
                  onChange={(e) => setFormMuestra((prev) => ({ ...prev, cantidad: e.target.value }))}
                  disabled={guardandoMuestra}
                  autoFocus
                />
              </div>
              <div className="field" style={{ flex: 1 }}>
                <label className="field-label">Unidad</label>
                <select
                  className="field-input"
                  value={formMuestra.unidad}
                  onChange={(e) => setFormMuestra((prev) => ({ ...prev, unidad: e.target.value }))}
                  disabled={guardandoMuestra}
                >
                  {UNIDADES_MUESTRA.map((u) => (
                    <option key={u} value={u}>{u}</option>
                  ))}
                </select>
              </div>
            </div>

            <div className="field">
              <label className="field-label">Laboratorio</label>
              <select
                className="field-input"
                value={formMuestra.id_laboratorio}
                onChange={(e) => setFormMuestra((prev) => ({ ...prev, id_laboratorio: e.target.value }))}
                disabled={guardandoMuestra}
              >
                <option value="">Sin asignar</option>
                {laboratorios.map((lab) => (
                  <option key={lab.id_laboratorio} value={lab.id_laboratorio}>{lab.nombre}</option>
                ))}
              </select>
            </div>

            <label style={{ display: 'flex', alignItems: 'center', gap: 'var(--sp-2)', marginTop: 'var(--sp-2)', marginBottom: 'var(--sp-3)' }}>
              <input
                type="checkbox"
                checked={formMuestra.genera_etiqueta}
                onChange={(e) => setFormMuestra((prev) => ({ ...prev, genera_etiqueta: e.target.checked }))}
                disabled={guardandoMuestra}
              />
              Genera etiqueta
            </label>

            {errorMuestra && <div className="alert alert-danger" style={{ marginBottom: 'var(--sp-3)' }}>{errorMuestra}</div>}

            <div style={{ display: 'flex', gap: 'var(--sp-3)' }}>
              <button type="button" className="btn btn-ghost" onClick={cerrarModalMuestra} disabled={guardandoMuestra}>Cancelar</button>
              <button type="submit" className="btn btn-primary" disabled={guardandoMuestra}>
                {guardandoMuestra ? <span className="spinner" /> : 'Guardar'}
              </button>
            </div>
          </form>
        </div>
      )}

      {copiarModalAbierto && (
        <div
          style={{
            position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.5)',
            display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 100, padding: 'var(--sp-4)',
          }}
          onClick={cerrarCopiar}
        >
          <form
            onSubmit={handleCopiar}
            className="card"
            style={{ width: '90%', maxWidth: 480, maxHeight: '90vh', overflowY: 'auto' }}
            onClick={(e) => e.stopPropagation()}
          >
            <h2 style={{ fontSize: 'var(--fs-lg)', marginBottom: 'var(--sp-3)' }}>Copiar como nueva especificación</h2>
            <p style={{ color: 'var(--ink-2)', fontSize: 'var(--fs-sm)', marginBottom: 'var(--sp-4)' }}>
              Crea una especificación nueva e independiente, con los mismos ensayos y datos descriptivos que{' '}
              {especificacion.erp_DESART}. No modifica la especificación original ni copia sus testigos asociados.
            </p>

            <div className="field">
              <label className="field-label">Tipo de material</label>
              <select
                className="field-input"
                value={copiarTipo}
                onChange={(e) => cambiarCopiarTipo(e.target.value)}
              >
                {TIPOS_MATERIAL.map((t) => (
                  <option key={t.value} value={t.value}>{t.label}</option>
                ))}
              </select>
            </div>

            {!copiarArticuloElegido ? (
              <div className="field">
                <label className="field-label">Artículo (código o descripción)</label>
                <input
                  className="field-input"
                  placeholder="Buscar en el ERP..."
                  value={copiarArticuloBuscar}
                  onChange={(e) => setCopiarArticuloBuscar(e.target.value)}
                  autoFocus
                />
                {copiarArticulos.length > 0 && (
                  <div className="select-list" style={{ marginTop: 'var(--sp-2)' }}>
                    {copiarArticulos.slice(0, 8).map((a) => (
                      <button
                        type="button"
                        key={a.IdM21}
                        className="select-item"
                        onClick={() => elegirCopiarArticulo(a)}
                      >
                        <span className="select-item-main">
                          <span className="select-item-title">{a.DESART}</span>
                          <span className="select-item-sub">{a.CODART}</span>
                        </span>
                      </button>
                    ))}
                  </div>
                )}
              </div>
            ) : (
              <div className="select-item select-item-active" style={{ marginBottom: 'var(--sp-3)' }}>
                <span className="select-item-main">
                  <span className="select-item-title">{copiarArticuloElegido.DESART}</span>
                  <span className="select-item-sub">{copiarArticuloElegido.CODART}</span>
                </span>
                <button type="button" className="btn btn-ghost" onClick={() => setCopiarArticuloElegido(null)}>
                  Cambiar
                </button>
              </div>
            )}

            <div className="field">
              <label className="field-label">Nombre</label>
              <input
                className="field-input"
                value={copiarNombre}
                onChange={(e) => setCopiarNombre(e.target.value)}
              />
            </div>

            <div className="field" style={{ marginBottom: 0 }}>
              <label className="field-label">Versión</label>
              <input
                className="field-input"
                value={copiarVersion}
                onChange={(e) => setCopiarVersion(e.target.value)}
              />
            </div>

            {errorCopiar && <div className="alert alert-danger" style={{ marginTop: 'var(--sp-3)' }}>{errorCopiar}</div>}

            <div style={{ display: 'flex', gap: 'var(--sp-3)', marginTop: 'var(--sp-4)' }}>
              <button type="button" className="btn btn-ghost" onClick={cerrarCopiar} disabled={guardandoCopia}>Cancelar</button>
              <button type="submit" className="btn btn-primary" disabled={guardandoCopia || !copiarArticuloElegido}>
                {guardandoCopia ? <span className="spinner" /> : 'Crear copia'}
              </button>
            </div>
          </form>
        </div>
      )}
    </div>
  );
}
