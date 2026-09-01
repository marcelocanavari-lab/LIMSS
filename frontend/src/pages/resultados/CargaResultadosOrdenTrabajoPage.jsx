import { useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import TopBar from '../../components/TopBar';
import ChecklistMuestreo from '../../components/ChecklistMuestreo';
import { solicitudesMuestreoApi } from '../../api/solicitudesMuestreo';
import { maestrosApi } from '../../api/maestros';
import { muestrasApi } from '../../api/muestras';
import { ApiError, abrirPdfConAuth } from '../../api/client';

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

let contadorAdHoc = 0;
function nuevaMuestraAdHoc() {
  contadorAdHoc += 1;
  return { key: `adhoc-${contadorAdHoc}`, tipo_muestra: '', cantidad_real: '', unidad: '' };
}

// Confirmación por defecto de cada muestra de la especificación (checkbox +
// cantidad real precargada con la cantidad planeada) -- preserva lo que el
// usuario ya haya tocado (confirmacionesPrevias) para las que ya conocía, y
// completa con el default de la especificación para las que recién
// aparecen (ver handleSubmit: se vuelve a llamar con la lista fresca justo
// antes de confirmar, no solo al montar la pantalla).
function defaultsConfirmacion(muestrasDeEspec, confirmacionesPrevias) {
  const siguiente = {};
  muestrasDeEspec.forEach((m) => {
    siguiente[m.id] = confirmacionesPrevias[m.id] || { confirmada: m.genera_etiqueta, cantidad_real: String(m.cantidad) };
  });
  return siguiente;
}

export default function CargaResultadosOrdenTrabajoPage() {
  const { idSolicitud } = useParams();
  const navigate = useNavigate();

  const [datos, setDatos] = useState(null);
  const [checklist, setChecklist] = useState([]); // [{ id_espec_ensayo, orden, nombre_ensayo, especificacion_texto, valor_cualitativo, id_categoria, categoria_codigo, categoria_nombre }]
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [guardando, setGuardando] = useState(false);
  const [resultado, setResultado] = useState(null); // OrdenTrabajoDigitalResponse tras confirmar
  const [codigoMuestraReadOnly, setCodigoMuestraReadOnly] = useState(null);
  const [idMuestraReadOnly, setIdMuestraReadOnly] = useState(null);
  const [descargando, setDescargando] = useState('');

  // "Muestras a tomar" -- confirmación al Ejecutar Muestreo, común a
  // solicitudes manuales y del agente (antes solo se pedía al crear una
  // solicitud manual). muestrasEspec son las definidas en la especificación
  // del producto; muestrasAdhoc son filas agregadas a mano solo para esta
  // solicitud puntual (no modifican la especificación).
  const [muestrasEspec, setMuestrasEspec] = useState([]);
  const [muestrasConfirmadas, setMuestrasConfirmadas] = useState({});
  const [muestrasAdhoc, setMuestrasAdhoc] = useState([]);

  // Impresión directa (SATO/SBPL) de las etiquetas generadas -- alternativa
  // al PDF, mismo patrón que MuestraEtiquetaPage.jsx.
  const [impresoras, setImpresoras] = useState([]);
  const [idImpresora, setIdImpresora] = useState('');
  const [mostrarImprimirDirecto, setMostrarImprimirDirecto] = useState(false);
  const [imprimiendo, setImprimiendo] = useState(false);
  const [mensajeDirecto, setMensajeDirecto] = useState(null); // { tipo: 'ok'|'error', texto }

  useEffect(() => {
    solicitudesMuestreoApi
      .obtenerEnsayosParaOrden(idSolicitud)
      .then(async (data) => {
        setDatos(data);
        setChecklist(data.checklist_muestreo || []);

        if (data.id_especificacion) {
          try {
            const muestrasDeEspec = await maestrosApi.listarMuestrasEspecificacion(data.id_especificacion);
            setMuestrasEspec(muestrasDeEspec);
            setMuestrasConfirmadas(defaultsConfirmacion(muestrasDeEspec, {}));
          } catch {
            setMuestrasEspec([]);
          }
        }

        if (data.estado !== 'pendiente') {
          try {
            const solicitud = await solicitudesMuestreoApi.obtener(idSolicitud);
            if (solicitud.id_muestra) {
              setIdMuestraReadOnly(solicitud.id_muestra);
              const muestra = await muestrasApi.obtenerMuestra(solicitud.id_muestra);
              setCodigoMuestraReadOnly(muestra.codigo_muestra);
            }
          } catch {
            // si falla, se muestra igual la vista de solo lectura sin el código
          }
        }
      })
      .catch((err) => setError(err instanceof ApiError ? err.message : 'No se pudo cargar la solicitud'))
      .finally(() => setLoading(false));
  }, [idSolicitud]);

  const soloLectura = (datos && datos.estado !== 'pendiente') || !!resultado;

  function actualizarChecklist(idEspecEnsayo, valor) {
    setChecklist((prev) => prev.map((it) => (
      it.id_espec_ensayo === idEspecEnsayo ? { ...it, valor_cualitativo: valor } : it
    )));
  }

  function toggleMuestraConfirmada(idMuestra) {
    setMuestrasConfirmadas((prev) => ({
      ...prev,
      [idMuestra]: { ...prev[idMuestra], confirmada: !prev[idMuestra]?.confirmada },
    }));
  }

  function actualizarCantidadRealMuestra(idMuestra, valor) {
    setMuestrasConfirmadas((prev) => ({
      ...prev,
      [idMuestra]: { ...prev[idMuestra], cantidad_real: valor },
    }));
  }

  function agregarMuestraAdhoc() {
    setMuestrasAdhoc((prev) => [...prev, nuevaMuestraAdHoc()]);
  }

  function actualizarMuestraAdhoc(key, campo, valor) {
    setMuestrasAdhoc((prev) => prev.map((m) => (m.key === key ? { ...m, [campo]: valor } : m)));
  }

  function quitarMuestraAdhoc(key) {
    setMuestrasAdhoc((prev) => prev.filter((m) => m.key !== key));
  }

  async function handleSubmit(e) {
    e.preventDefault();
    setError('');

    // Vuelve a leer lims_especificacion_muestras EN VIVO justo antes de
    // confirmar -- la carga de muestrasEspec de arriba es una sola vez al
    // montar la pantalla, así que si alguien agrega (o quita) una muestra
    // de la especificación mientras el muestreador tiene esta pantalla
    // abierta, esa carga inicial queda vieja. La confirmación (tabla,
    // lims_solicitud_muestras, y de ahí las etiquetas) tiene que reflejar
    // lo vigente en este momento, no lo que había al abrir la pantalla --
    // bug real: una 3ª muestra agregada a la especificación después de
    // crear la solicitud nunca llegaba a imprimirse. Se usan variables
    // locales (no el estado recién seteado, que no está disponible hasta
    // el próximo render) para la validación y el body de este submit;
    // igual se actualiza el estado para que la tabla en pantalla quede
    // consistente si la validación de abajo corta acá.
    let muestrasVigentes = muestrasEspec;
    let confirmacionesVigentes = muestrasConfirmadas;
    if (datos?.id_especificacion) {
      try {
        muestrasVigentes = await maestrosApi.listarMuestrasEspecificacion(datos.id_especificacion);
        confirmacionesVigentes = defaultsConfirmacion(muestrasVigentes, muestrasConfirmadas);
        setMuestrasEspec(muestrasVigentes);
        setMuestrasConfirmadas(confirmacionesVigentes);
      } catch {
        // si falla el refresco, se sigue con lo que ya había en pantalla --
        // mismo criterio tolerante que la carga inicial de arriba.
      }
    }

    for (const m of muestrasVigentes) {
      const conf = confirmacionesVigentes[m.id];
      if (conf?.confirmada && !(Number(conf.cantidad_real) > 0)) {
        setError('La cantidad real de las muestras confirmadas tiene que ser mayor a 0');
        return;
      }
    }
    for (const m of muestrasAdhoc) {
      if (!m.tipo_muestra || !m.unidad.trim() || !(Number(m.cantidad_real) > 0)) {
        setError('Completá tipo, unidad y cantidad (mayor a 0) de todas las muestras ad-hoc agregadas (o quitá la fila)');
        return;
      }
    }
    setGuardando(true);
    try {
      const muestrasBody = [
        ...muestrasVigentes.map((m) => ({
          id_espec_muestra: m.id,
          cantidad_real: Number(confirmacionesVigentes[m.id]?.cantidad_real || m.cantidad),
          confirmada: !!confirmacionesVigentes[m.id]?.confirmada,
        })),
        ...muestrasAdhoc.map((m) => ({
          id_espec_muestra: null,
          tipo_muestra: m.tipo_muestra,
          unidad: m.unidad.trim() || null,
          cantidad_real: Number(m.cantidad_real),
          confirmada: true,
        })),
      ];
      const resp = await solicitudesMuestreoApi.confirmarOrdenTrabajo(idSolicitud, {
        checklist_muestreo: checklist
          .filter((it) => it.valor_cualitativo)
          .map((it) => ({ id_espec_ensayo: it.id_espec_ensayo, valor_cualitativo: it.valor_cualitativo })),
        muestras: muestrasBody,
      });
      setResultado(resp);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'No se pudo confirmar el muestreo');
    } finally {
      setGuardando(false);
    }
  }

  function abrirImprimirDirecto() {
    setMensajeDirecto(null);
    setMostrarImprimirDirecto(true);
    if (impresoras.length === 0) {
      muestrasApi
        .listarImpresoras(true)
        .then((data) => {
          setImpresoras(data);
          if (data.length === 1) setIdImpresora(String(data[0].id_impresora));
        })
        .catch(() => setMensajeDirecto({ tipo: 'error', texto: 'No se pudo cargar el listado de impresoras' }));
    }
  }

  async function confirmarImprimirDirecto(idMuestra) {
    if (!idImpresora) return;
    setImprimiendo(true);
    setMensajeDirecto(null);
    try {
      const resp = await muestrasApi.imprimirDirecto(idMuestra, Number(idImpresora));
      setMensajeDirecto({ tipo: 'ok', texto: resp.mensaje });
    } catch (err) {
      setMensajeDirecto({ tipo: 'error', texto: err instanceof ApiError ? err.message : 'No se pudo imprimir la etiqueta' });
    } finally {
      setImprimiendo(false);
    }
  }

  async function handleDescargar(tipo, path) {
    setDescargando(tipo);
    try {
      await abrirPdfConAuth(path);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'No se pudo descargar el PDF');
    } finally {
      setDescargando('');
    }
  }

  if (loading) {
    return (
      <div className="screen" style={{ alignItems: 'center', justifyContent: 'center' }}>
        <span className="spinner" />
      </div>
    );
  }

  if (error && !datos) {
    return (
      <div className="screen">
        <TopBar titulo="Orden de Trabajo" subtitulo="Ejecutar muestreo" onBack={() => navigate(-1)} />
        <div className="screen-content">
          <div className="alert alert-danger">{error}</div>
        </div>
      </div>
    );
  }

  const codigoMuestra = resultado?.codigo_muestra || codigoMuestraReadOnly;
  const idMuestraConfirmada = resultado?.id_muestra || idMuestraReadOnly;

  if (soloLectura && codigoMuestra) {
    return (
      <div className="screen">
        <TopBar titulo={datos.nro_solicitud} subtitulo="Muestreo confirmado" onBack={() => navigate(-1)} />
        <div className="screen-content">
          <div className="card" style={{ maxWidth: 480, margin: '0 auto', textAlign: 'center' }}>
            <div style={{ fontSize: 32, marginBottom: 'var(--sp-3)' }}>✓</div>
            <h2 style={{ fontSize: 'var(--fs-lg)', marginBottom: 'var(--sp-3)' }}>
              Muestra {codigoMuestra} creada correctamente
            </h2>
            <button
              className="btn btn-primary btn-block"
              style={{ marginBottom: 'var(--sp-2)' }}
              onClick={() => handleDescargar('etiquetas', `/api/solicitudes-muestreo/${idSolicitud}/etiquetas`)}
              disabled={!!descargando}
            >
              {descargando === 'etiquetas' ? <span className="spinner" /> : 'Descargar etiquetas (PDF)'}
            </button>
            {idMuestraConfirmada && !mostrarImprimirDirecto && (
              <button
                className="btn btn-secondary btn-block"
                style={{ marginBottom: 'var(--sp-2)' }}
                onClick={abrirImprimirDirecto}
              >
                Imprimir directo (impresora SATO) →
              </button>
            )}
            {idMuestraConfirmada && mostrarImprimirDirecto && (
              <div className="card" style={{ marginBottom: 'var(--sp-3)', textAlign: 'left' }}>
                <h2 style={{ fontSize: 'var(--fs-lg)', marginBottom: 'var(--sp-3)' }}>Imprimir directo</h2>
                {impresoras.length === 0 && !mensajeDirecto ? (
                  <div className="state-block"><span className="spinner" /></div>
                ) : impresoras.length === 0 ? null : (
                  <>
                    <div className="alert alert-warn" style={{ marginBottom: 'var(--sp-3)' }}>
                      Verificá que la impresora tenga cargado el rollo de etiquetas BLANCAS antes de continuar.
                    </div>
                    <div className="field">
                      <label className="field-label" htmlFor="impresora">Impresora</label>
                      <select
                        id="impresora"
                        className="field-input"
                        value={idImpresora}
                        onChange={(e) => setIdImpresora(e.target.value)}
                        disabled={imprimiendo}
                      >
                        <option value="">Seleccioná una impresora...</option>
                        {impresoras.map((imp) => (
                          <option key={imp.id_impresora} value={imp.id_impresora}>{imp.nombre} ({imp.modelo})</option>
                        ))}
                      </select>
                    </div>
                  </>
                )}

                {mensajeDirecto && (
                  <div className={`alert ${mensajeDirecto.tipo === 'ok' ? 'alert-ok' : 'alert-danger'}`} style={{ marginBottom: 'var(--sp-3)' }}>
                    {mensajeDirecto.texto}
                  </div>
                )}

                <div style={{ display: 'flex', gap: 'var(--sp-3)' }}>
                  <button type="button" className="btn btn-ghost" onClick={() => setMostrarImprimirDirecto(false)} disabled={imprimiendo}>
                    Cancelar
                  </button>
                  <button
                    type="button"
                    className="btn btn-primary"
                    onClick={() => confirmarImprimirDirecto(idMuestraConfirmada)}
                    disabled={imprimiendo || !idImpresora}
                  >
                    {imprimiendo ? <span className="spinner" /> : 'Imprimir'}
                  </button>
                </div>
              </div>
            )}
            <button
              className="btn btn-secondary btn-block"
              style={{ marginBottom: 'var(--sp-2)' }}
              onClick={() => handleDescargar('orden', `/api/solicitudes-muestreo/${idSolicitud}/orden-trabajo`)}
              disabled={!!descargando}
            >
              {descargando === 'orden' ? <span className="spinner" /> : 'Ver Orden de Trabajo PDF'}
            </button>
            <button
              className="btn btn-secondary btn-block"
              style={{ marginBottom: 'var(--sp-3)' }}
              onClick={() => handleDescargar('planilla', `/api/solicitudes-muestreo/${idSolicitud}/planilla-muestreo`)}
              disabled={!!descargando}
            >
              {descargando === 'planilla' ? <span className="spinner" /> : 'Ver Planilla de Muestreo PDF'}
            </button>
            <button className="btn btn-ghost btn-block" onClick={() => navigate(-1)}>
              Volver
            </button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="screen">
      <TopBar
        titulo={datos.nro_solicitud}
        subtitulo={`${datos.erp_DESART} (${datos.erp_CODART.trim()})`}
        onBack={() => navigate(-1)}
      />
      <div className="screen-content">
        {soloLectura && (
          <div className="alert alert-info" style={{ marginBottom: 'var(--sp-4)' }}>
            Esta solicitud ya fue ejecutada -- el formulario queda en solo lectura.
          </div>
        )}
        <form onSubmit={handleSubmit}>
          <div className="card" style={{ marginBottom: 'var(--sp-4)' }}>
            <h2 style={{ fontSize: 'var(--fs-lg)', marginBottom: 'var(--sp-3)' }}>Checklist de muestreo</h2>
            <ChecklistMuestreo checklist={checklist} onChange={actualizarChecklist} disabled={guardando || soloLectura} />
          </div>

          <div className="card" style={{ marginBottom: 'var(--sp-4)' }}>
            <h2 style={{ fontSize: 'var(--fs-lg)', marginBottom: 'var(--sp-3)' }}>Muestras a tomar</h2>
            {muestrasEspec.length === 0 && muestrasAdhoc.length === 0 ? (
              <div className="alert alert-warn">
                Esta especificación no tiene muestras definidas. Podés agregar una muestra ad-hoc abajo.
              </div>
            ) : (
              <div className="table-scroll">
                <table className="data-table data-table-compact">
                  <thead>
                    <tr>
                      <th></th>
                      <th>Tipo</th>
                      <th>Cantidad</th>
                      <th>Unidad</th>
                      <th>Laboratorio</th>
                      <th>Cant. real</th>
                      <th></th>
                    </tr>
                  </thead>
                  <tbody>
                    {muestrasEspec.map((m) => {
                      const conf = muestrasConfirmadas[m.id] || { confirmada: false, cantidad_real: String(m.cantidad) };
                      return (
                        <tr key={m.id}>
                          <td>
                            <input
                              type="checkbox"
                              checked={conf.confirmada}
                              onChange={() => toggleMuestraConfirmada(m.id)}
                              disabled={guardando || soloLectura}
                            />
                          </td>
                          <td>
                            <span className={`badge ${BADGE_TIPO_MUESTRA[m.tipo_muestra] || 'badge-neutral'}`}>
                              {LABEL_TIPO_MUESTRA[m.tipo_muestra] || m.tipo_muestra}
                            </span>
                          </td>
                          <td className="num">{m.cantidad}</td>
                          <td>{m.unidad}</td>
                          <td>{m.laboratorio_nombre || 'Sin asignar'}</td>
                          <td>
                            <input
                              className="field-input"
                              type="number"
                              step="any"
                              style={{ maxWidth: 110 }}
                              value={conf.cantidad_real}
                              onChange={(e) => actualizarCantidadRealMuestra(m.id, e.target.value)}
                              disabled={!conf.confirmada || guardando || soloLectura}
                            />
                          </td>
                          <td></td>
                        </tr>
                      );
                    })}
                    {muestrasAdhoc.map((m) => (
                      <tr key={m.key}>
                        <td></td>
                        <td>
                          <select
                            className="field-input"
                            style={{ maxWidth: 150 }}
                            value={m.tipo_muestra}
                            onChange={(e) => actualizarMuestraAdhoc(m.key, 'tipo_muestra', e.target.value)}
                            disabled={guardando || soloLectura}
                          >
                            <option value="">Elegí un tipo...</option>
                            <option value="analisis">Análisis</option>
                            <option value="contramuestra">Contramuestra</option>
                            <option value="testigo">Testigo</option>
                          </select>
                        </td>
                        <td colSpan={2}>
                          <span className="badge badge-neutral">Ad-hoc (no está en la especificación)</span>
                        </td>
                        <td></td>
                        <td>
                          <div style={{ display: 'flex', gap: 'var(--sp-2)' }}>
                            <input
                              className="field-input"
                              type="number"
                              step="any"
                              style={{ maxWidth: 90 }}
                              placeholder="Cant."
                              value={m.cantidad_real}
                              onChange={(e) => actualizarMuestraAdhoc(m.key, 'cantidad_real', e.target.value)}
                              disabled={guardando || soloLectura}
                            />
                            <input
                              className="field-input"
                              style={{ maxWidth: 90 }}
                              placeholder="Unidad"
                              value={m.unidad}
                              onChange={(e) => actualizarMuestraAdhoc(m.key, 'unidad', e.target.value)}
                              disabled={guardando || soloLectura}
                            />
                          </div>
                        </td>
                        <td>
                          <button
                            type="button"
                            className="btn btn-ghost btn-sm"
                            onClick={() => quitarMuestraAdhoc(m.key)}
                            disabled={guardando || soloLectura}
                          >
                            Quitar
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
            {!soloLectura && (
              <button type="button" className="btn btn-secondary" style={{ marginTop: 'var(--sp-3)' }} onClick={agregarMuestraAdhoc} disabled={guardando}>
                + Agregar muestra ad-hoc
              </button>
            )}
          </div>

          {error && <div className="alert alert-danger" style={{ marginBottom: 'var(--sp-4)' }}>{error}</div>}

          {!soloLectura && (
            <button type="submit" className="btn btn-primary btn-block btn-lg" disabled={guardando}>
              {guardando ? <span className="spinner" /> : 'Confirmar muestreo'}
            </button>
          )}
        </form>
      </div>
    </div>
  );
}
