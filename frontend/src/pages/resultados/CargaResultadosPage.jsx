import { useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import TopBar from '../../components/TopBar';
import { resultadosApi } from '../../api/resultados';
import { empaqueIaApi } from '../../api/empaqueIa';
import { muestrasApi } from '../../api/muestras';
import { ApiError } from '../../api/client';

function tieneResultado(en) {
  if (en.tipo_dato === 'numerico') return en.valor_numerico !== null && en.valor_numerico !== undefined;
  return !!(en.valor_cualitativo && en.valor_cualitativo.trim());
}

// Color de rollo físico que el operador debe tener cargado en la SATO --
// el sistema no imprime en color, lo determina el papel (amarillo/verde/
// rojo para Cuarentena/Aprobado/Rechazado). Mismo mapeo que usa el modal de
// Cuarentena en SolicitudesMuestreoPage.jsx.
const COLOR_PAPEL_POR_ESTADO = { aprobado: 'VERDES', rechazado: 'ROJAS' };

// Estados de lims_muestras.estado que habilitan cada etiqueta -- mismo
// criterio que el backend (_imprimir_etiqueta_estado_muestra en
// muestras.py). APROBADO ya no exige dictamen formal emitido: alcanza con
// que todos los resultados hayan dado dentro de especificación
// ('aprobado_sin_dictamen', ver guardar_resultados en resultados.py) -- el
// material tiene que poder salir de cuarentena apenas los resultados dan
// bien, sin esperar el papeleo formal. RECHAZADO sigue exigiendo el
// dictamen formal (no hay estado "sin dictamen" equivalente para el caso
// de rechazo -- eso sí necesita la revisión y justificación de QA).
const ESTADOS_PERMITIDOS_POR_ETIQUETA = {
  aprobado: ['aprobado', 'aprobado_sin_dictamen'],
  rechazado: ['rechazado'],
};

// Tarjeta de impresión de etiqueta APROBADO/RECHAZADO -- misma UI para las
// dos (solo cambia el estado esperado, el título y qué endpoint llama), con
// cantidad de copias + aviso de color de papel + confirmación explícita
// antes de imprimir.
function TarjetaImprimirEstado({ estado, titulo, estadoMuestra, idMuestra, imprimirFn }) {
  const [impresoras, setImpresoras] = useState([]);
  const [idImpresora, setIdImpresora] = useState('');
  const [cantidad, setCantidad] = useState(1);
  const [desdeBulto, setDesdeBulto] = useState('');
  const [hastaBulto, setHastaBulto] = useState('');
  const [imprimiendo, setImprimiendo] = useState(false);
  const [mensaje, setMensaje] = useState(null);

  function abrir() {
    setMensaje(null);
    if (impresoras.length === 0) {
      muestrasApi
        .listarImpresoras(true)
        .then((data) => {
          setImpresoras(data);
          if (data.length === 1) setIdImpresora(String(data[0].id_impresora));
        })
        .catch(() => setMensaje({ tipo: 'error', texto: 'No se pudo cargar el listado de impresoras' }));
    }
  }

  async function confirmar() {
    if (!idImpresora || !idMuestra) return;
    setImprimiendo(true);
    setMensaje(null);
    try {
      const resp = await imprimirFn(
        idMuestra, Number(idImpresora), cantidad,
        desdeBulto ? Number(desdeBulto) : undefined, hastaBulto ? Number(hastaBulto) : undefined,
      );
      setMensaje({ tipo: 'ok', texto: resp.mensaje });
    } catch (err) {
      setMensaje({ tipo: 'error', texto: err instanceof ApiError ? err.message : 'No se pudo imprimir la etiqueta' });
    } finally {
      setImprimiendo(false);
    }
  }

  const permitido = ESTADOS_PERMITIDOS_POR_ETIQUETA[estado].includes(estadoMuestra);

  return (
    <div className="card" style={{ marginTop: 'var(--sp-5)' }}>
      <h2 style={{ fontSize: 'var(--fs-lg)', marginBottom: 'var(--sp-2)' }}>Etiqueta {titulo}</h2>
      <p style={{ fontSize: 'var(--fs-sm)', color: 'var(--ink-2)', marginBottom: 'var(--sp-3)' }}>
        {titulo === 'APROBADO'
          ? 'Se puede imprimir apenas todos los resultados dan dentro de especificación, sin esperar el dictamen formal.'
          : 'Solo se puede imprimir cuando el dictamen de esta muestra está Rechazado.'}
      </p>

      {!permitido && (
        <div className="alert alert-warn" style={{ marginBottom: 'var(--sp-3)' }}>
          {estadoMuestra === 'en_análisis'
            ? 'Esta muestra todavía está en análisis -- faltan resultados por cargar.'
            : `El estado actual de la muestra ('${estadoMuestra}') no corresponde a esta etiqueta.`}
        </div>
      )}

      {impresoras.length > 0 && (
        <>
          <div className="alert alert-warn" style={{ marginBottom: 'var(--sp-3)' }}>
            Verificá que la impresora tenga cargado el rollo de etiquetas {COLOR_PAPEL_POR_ESTADO[estado]} antes de continuar.
          </div>
          <div className="field">
            <label className="field-label" htmlFor={`impresora-${estado}`}>Impresora</label>
            <select
              id={`impresora-${estado}`}
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
          <div className="field">
            <label className="field-label" htmlFor={`cantidad-${estado}`}>Cantidad de copias</label>
            <input
              id={`cantidad-${estado}`}
              className="field-input"
              type="number"
              min="1"
              max="99"
              style={{ maxWidth: 120 }}
              value={cantidad}
              onChange={(e) => setCantidad(Math.min(99, Math.max(1, Number(e.target.value) || 1)))}
              disabled={imprimiendo}
            />
          </div>
          <div className="field">
            <label className="field-label">Rango de bultos (opcional -- reimpresión parcial)</label>
            <div style={{ display: 'flex', gap: 'var(--sp-3)' }}>
              <input
                className="field-input" type="number" min="1" placeholder="Desde" style={{ maxWidth: 120 }}
                value={desdeBulto} onChange={(e) => setDesdeBulto(e.target.value)} disabled={imprimiendo}
              />
              <input
                className="field-input" type="number" min="1" placeholder="Hasta" style={{ maxWidth: 120 }}
                value={hastaBulto} onChange={(e) => setHastaBulto(e.target.value)} disabled={imprimiendo}
              />
            </div>
            <span style={{ fontSize: 'var(--fs-xs)', color: 'var(--ink-2)' }}>
              Vacío = todos los bultos. Cada etiqueta sigue mostrando su número real (ej. "3/10").
            </span>
          </div>
        </>
      )}

      {mensaje && (
        <div className={`alert ${mensaje.tipo === 'ok' ? 'alert-ok' : 'alert-danger'}`} style={{ marginBottom: 'var(--sp-3)' }}>
          {mensaje.texto}
        </div>
      )}

      {impresoras.length === 0 ? (
        <button type="button" className="btn btn-secondary btn-block" onClick={abrir}>
          Imprimir etiqueta {titulo} →
        </button>
      ) : (
        <button
          type="button"
          className="btn btn-primary btn-block"
          onClick={confirmar}
          disabled={imprimiendo || !idImpresora}
        >
          {imprimiendo ? <span className="spinner" /> : `Confirmar e imprimir ${cantidad} copia${cantidad === 1 ? '' : 's'}`}
        </button>
      )}
    </div>
  );
}

export default function CargaResultadosPage() {
  const { idEnvio } = useParams();
  const navigate = useNavigate();

  const [envio, setEnvio] = useState(null);
  const [valores, setValores] = useState({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  // Comparación de etiquetas con IA (solo Material de Empaque) -- ayuda
  // visual para quien inspecciona, nunca decide ni pre-carga el resultado.
  // Una sola por ENVÍO (no por ensayo): varios ensayos del mismo envío se
  // verifican todos contra la misma foto de etiqueta recibida.
  //
  // Provisoria hasta guardar: comparar-etiqueta ya no persiste en el
  // backend (ver comparar_etiqueta en resultados.py) -- el resultado vive
  // solo acá, en memoria, hasta que se manda junto con "Guardar resultados".
  // Si se corre de nuevo antes de guardar, este objeto se reemplaza entero
  // (no se acumula), así que solo la última corrida es la que se guarda.
  const [comparacion, setComparacion] = useState({ observacion: null, iaDisponible: null, imagenComparacionPath: null, comparando: false, error: '' });

  const [nroProtocolo, setNroProtocolo] = useState('');
  const [fechaEmision, setFechaEmision] = useState('');
  const [archivo, setArchivo] = useState(null);
  const [guardandoResultados, setGuardandoResultados] = useState(false);
  const [guardandoProtocolo, setGuardandoProtocolo] = useState(false);
  const [errorProtocolo, setErrorProtocolo] = useState('');
  const [mensajeOk, setMensajeOk] = useState('');

  function cargar() {
    return resultadosApi
      .obtenerParaCarga(idEnvio)
      .then((data) => {
        setEnvio(data);
        const iniciales = {};
        data.ensayos.forEach((e) => {
          iniciales[e.id_espec_ensayo] = {
            valor_numerico: e.valor_numerico ?? '',
            valor_cualitativo: e.valor_cualitativo ?? '',
          };
        });
        setValores(iniciales);
        if (data.observacion_ia || data.tiene_imagen_comparacion) {
          // Ya persistido de un guardado anterior -- se muestra, pero
          // imagenComparacionPath queda en null: si se resguarda sin correr
          // una comparación nueva, no se reenvía nada (ver handleGuardarResultados)
          // y el backend deja lo ya persistido tal cual, sin tocarlo.
          setComparacion({ observacion: data.observacion_ia, iaDisponible: data.observacion_ia != null, imagenComparacionPath: null, comparando: false, error: '' });
        }
        if (data.protocolo) {
          setNroProtocolo(data.protocolo.nro_protocolo_ext);
          setFechaEmision(data.protocolo.fecha_emision);
        }
      })
      .catch((err) => setError(err instanceof ApiError ? err.message : 'No se pudo cargar el envío'));
  }

  useEffect(() => {
    cargar().finally(() => setLoading(false));
  }, [idEnvio]);

  function actualizarValor(idEnsayo, campo, valor) {
    setValores((prev) => ({ ...prev, [idEnsayo]: { ...prev[idEnsayo], [campo]: valor } }));
  }

  async function handleCompararEtiqueta(archivo) {
    setComparacion((prev) => ({ ...prev, comparando: true, error: '' }));
    try {
      const resp = await empaqueIaApi.compararEtiqueta(idEnvio, archivo);
      setComparacion({
        observacion: resp.observacion_ia,
        iaDisponible: resp.ia_disponible,
        imagenComparacionPath: resp.imagen_comparacion_path,
        comparando: false,
        error: '',
      });
    } catch (err) {
      setComparacion((prev) => ({ ...prev, comparando: false, error: err instanceof ApiError ? err.message : 'No se pudo comparar la etiqueta' }));
    }
  }

  // Guardado parcial: se manda lo que haya en cada campo (algunos pueden
  // quedar vacíos) y el backend guarda ensayo por ensayo -- no hace falta
  // completar todo el envío en esta misma operación. El protocolo NO viaja
  // acá: es independiente, se carga aparte (ver handleGuardarProtocolo).
  async function handleGuardarResultados(e) {
    e.preventDefault();
    setError('');
    setMensajeOk('');

    const resultados = envio.ensayos.map((en) => {
      const v = valores[en.id_espec_ensayo] || {};
      return {
        id_espec_ensayo: en.id_espec_ensayo,
        valor_numerico: en.tipo_dato === 'numerico' && v.valor_numerico !== '' ? Number(v.valor_numerico) : null,
        valor_cualitativo: en.tipo_dato === 'cualitativo' ? (v.valor_cualitativo || null) : null,
      };
    });

    setGuardandoResultados(true);
    try {
      await resultadosApi.guardarResultados(idEnvio, {
        resultados,
        imagenComparacionPath: comparacion.imagenComparacionPath,
        observacionIa: comparacion.observacion,
      });
      await cargar();
      setMensajeOk('Resultados guardados.');
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'No se pudo guardar los resultados');
    } finally {
      setGuardandoResultados(false);
    }
  }

  async function handleGuardarProtocolo(e) {
    e.preventDefault();
    setErrorProtocolo('');
    setMensajeOk('');

    if (!nroProtocolo.trim() || !fechaEmision) {
      setErrorProtocolo('El número de protocolo y la fecha de emisión son obligatorios');
      return;
    }
    if (!archivo) {
      setErrorProtocolo(
        envio.protocolo
          ? 'Para reemplazar el protocolo ya cargado, adjuntá el PDF nuevo -- no alcanza con cambiar el número/fecha.'
          : 'Adjuntá el protocolo en PDF',
      );
      return;
    }
    if (archivo.type !== 'application/pdf') {
      setErrorProtocolo('El archivo debe ser un PDF');
      return;
    }

    setGuardandoProtocolo(true);
    try {
      await resultadosApi.guardarProtocolo(idEnvio, {
        nroProtocoloExt: nroProtocolo.trim(),
        fechaEmision,
        protocoloPdf: archivo,
      });
      await cargar();
      setArchivo(null);
      setMensajeOk('Protocolo guardado.');
    } catch (err) {
      setErrorProtocolo(err instanceof ApiError ? err.message : 'No se pudo guardar el protocolo');
    } finally {
      setGuardandoProtocolo(false);
    }
  }

  if (loading) {
    return (
      <div className="screen" style={{ alignItems: 'center', justifyContent: 'center' }}>
        <span className="spinner" />
      </div>
    );
  }

  if (error && !envio) {
    return (
      <div className="screen">
        <TopBar titulo="Cargar resultados" subtitulo="Carga de Resultados" onBack={() => navigate(-1)} />
        <div className="screen-content">
          <div className="alert alert-danger">{error}</div>
        </div>
      </div>
    );
  }

  const totalEnsayos = envio.ensayos.length;
  const ensayosCargados = envio.ensayos.filter(tieneResultado).length;
  const estadoCarga =
    totalEnsayos === 0 ? null : ensayosCargados === 0 ? 'sin_cargar' : ensayosCargados === totalEnsayos ? 'completo' : 'parcial';
  const BADGE_ESTADO_CARGA = {
    sin_cargar: { texto: 'Sin cargar', clase: 'badge-neutral' },
    parcial: { texto: 'Parcial', clase: 'badge-warn' },
    completo: { texto: 'Completo', clase: 'badge-ok' },
  };

  return (
    <div className="screen">
      <TopBar
        titulo={envio.codigo_muestra}
        subtitulo={`${envio.erp_DESART} — ${envio.laboratorio_nombre}`}
        onBack={() => navigate(-1)}
      />
      <div className="screen-content">
        {mensajeOk && <div className="alert alert-ok" style={{ marginBottom: 'var(--sp-4)' }}>{mensajeOk}</div>}

        <form onSubmit={handleGuardarResultados}>
          {envio.tipo_material === 'material_empaque' && (
            <div className="card" style={{ marginBottom: 'var(--sp-5)' }}>
              <h2 style={{ fontSize: 'var(--fs-lg)', marginBottom: 'var(--sp-2)' }}>Comparación de etiqueta con IA</h2>
              <p style={{ fontSize: 'var(--fs-sm)', color: 'var(--ink-2)', marginBottom: 'var(--sp-3)' }}>
                Subí una foto de la etiqueta recibida en esta inspección -- se compara contra la imagen de referencia del
                artículo. Es una ayuda visual para los ensayos de abajo (texto legal, colores, código de barras, etc.), no
                reemplaza tu criterio: el Cumple/No cumple de cada uno lo completás vos.
              </p>

              <label
                className="btn btn-secondary"
                style={{ cursor: comparacion.comparando ? 'default' : 'pointer' }}
              >
                {comparacion.comparando ? <span className="spinner" /> : 'Subir foto y comparar'}
                <input
                  type="file"
                  accept="image/jpeg,image/png"
                  style={{ display: 'none' }}
                  disabled={comparacion.comparando}
                  onChange={(e) => {
                    const f = e.target.files?.[0];
                    e.target.value = '';
                    if (f) handleCompararEtiqueta(f);
                  }}
                />
              </label>

              {comparacion.error && (
                <div className="alert alert-danger" style={{ marginTop: 'var(--sp-3)' }}>{comparacion.error}</div>
              )}
              {comparacion.observacion != null && (
                <div className="alert alert-info" style={{ marginTop: 'var(--sp-3)' }}>
                  <strong>Sugerencia IA:</strong> {comparacion.observacion}
                </div>
              )}
              {!comparacion.comparando && comparacion.observacion == null && comparacion.iaDisponible === false && (
                <div className="alert alert-warn" style={{ marginTop: 'var(--sp-3)' }}>
                  No se pudo generar la comparación con IA -- podés seguir cargando los resultados igual.
                </div>
              )}
            </div>
          )}

          <div className="card" style={{ marginBottom: 'var(--sp-5)' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 'var(--sp-3)', flexWrap: 'wrap', gap: 'var(--sp-2)' }}>
              <h2 style={{ fontSize: 'var(--fs-lg)', margin: 0 }}>Resultados de análisis solicitados</h2>
              {estadoCarga && (
                <span style={{ display: 'flex', alignItems: 'center', gap: 'var(--sp-2)', fontSize: 'var(--fs-sm)' }}>
                  {ensayosCargados} de {totalEnsayos} ensayos cargados
                  <span className={`badge ${BADGE_ESTADO_CARGA[estadoCarga].clase}`}>{BADGE_ESTADO_CARGA[estadoCarga].texto}</span>
                </span>
              )}
            </div>
            <p style={{ fontSize: 'var(--fs-sm)', color: 'var(--ink-2)', marginBottom: 'var(--sp-3)' }}>
              No hace falta completar todos los ensayos para guardar: podés cargar los que ya tengas y volver más tarde a
              completar el resto.
            </p>
            {envio.ensayos.length === 0 ? (
              <div className="alert alert-info">No hay ensayos solicitados para el envío de esta muestra.</div>
            ) : (
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Ensayo</th>
                    <th>Metodología</th>
                    <th>Especificación</th>
                    <th>Resultado</th>
                    <th>Estado</th>
                  </tr>
                </thead>
                <tbody>
                  {envio.ensayos.map((en) => {
                    const v = valores[en.id_espec_ensayo] || {};
                    const cargado = tieneResultado(en);
                    return (
                      <tr key={en.id_espec_ensayo}>
                        <td>
                          {en.nombre_ensayo}{en.obligatorio && ' *'}
                          {en.especificacion_texto && (
                            <div style={{ fontSize: 'var(--fs-xs)', color: 'var(--ink-2)', marginTop: 2 }}>
                              {en.especificacion_texto}
                            </div>
                          )}
                        </td>
                        <td>{en.metodologia || '—'}</td>
                        <td>
                          {en.tipo_dato === 'numerico'
                            ? `${en.limite_inferior ?? '—'} a ${en.limite_superior ?? '—'} ${en.unidad_medida || ''}`
                            : en.valor_requerido}
                        </td>
                        <td>
                          {en.tipo_dato === 'numerico' ? (
                            <input
                              className="field-input"
                              type="number"
                              step="any"
                              value={v.valor_numerico}
                              onChange={(e) => actualizarValor(en.id_espec_ensayo, 'valor_numerico', e.target.value)}
                              disabled={guardandoResultados}
                            />
                          ) : (
                            <select
                              className="field-input"
                              value={v.valor_cualitativo}
                              onChange={(e) => actualizarValor(en.id_espec_ensayo, 'valor_cualitativo', e.target.value)}
                              disabled={guardandoResultados}
                            >
                              <option value="">Seleccioná...</option>
                              <option value="Cumple">Cumple</option>
                              <option value="No cumple">No cumple</option>
                            </select>
                          )}
                        </td>
                        <td>
                          {cargado
                            ? <span className="badge badge-ok">Cargado</span>
                            : <span className="badge badge-neutral">Pendiente</span>}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            )}
          </div>

          {error && <div className="alert alert-danger" style={{ marginBottom: 'var(--sp-4)' }}>{error}</div>}

          <button type="submit" className="btn btn-primary btn-block btn-lg" disabled={guardandoResultados}>
            {guardandoResultados ? <span className="spinner" /> : 'Guardar resultados'}
          </button>
        </form>

        <div className="card" style={{ marginTop: 'var(--sp-5)' }}>
          <h2 style={{ fontSize: 'var(--fs-lg)', marginBottom: 'var(--sp-2)' }}>Protocolo del laboratorio</h2>
          <p style={{ fontSize: 'var(--fs-sm)', color: 'var(--ink-2)', marginBottom: 'var(--sp-3)' }}>
            Es independiente de los resultados: se puede cargar antes, después, o nunca en la misma visita a esta pantalla.
          </p>
          {envio.protocolo && (
            <div className="alert alert-info" style={{ marginBottom: 'var(--sp-3)' }}>
              Ya hay un protocolo cargado ({envio.protocolo.pdf_nombre_original}, {envio.protocolo.fecha_emision}). Para
              reemplazarlo, completá el formulario de abajo adjuntando el PDF nuevo -- es obligatorio volver a
              seleccionar un archivo cada vez, aunque solo quieras corregir el número o la fecha.
            </div>
          )}
          <form onSubmit={handleGuardarProtocolo}>
            <div className="field">
              <label className="field-label" htmlFor="nroProtocolo">Número de protocolo externo</label>
              <input
                id="nroProtocolo"
                className="field-input"
                value={nroProtocolo}
                onChange={(e) => setNroProtocolo(e.target.value)}
                disabled={guardandoProtocolo}
              />
            </div>
            <div className="field">
              <label className="field-label" htmlFor="fechaEmision">Fecha de emisión</label>
              <input
                id="fechaEmision"
                className="field-input"
                type="date"
                value={fechaEmision}
                onChange={(e) => setFechaEmision(e.target.value)}
                disabled={guardandoProtocolo}
              />
            </div>
            <div className="field">
              <label className="field-label" htmlFor="pdf">Protocolo (PDF){envio.protocolo ? ' -- nuevo, para reemplazar el actual' : ''}</label>
              <input
                id="pdf"
                className="field-input"
                type="file"
                accept="application/pdf"
                onChange={(e) => setArchivo(e.target.files?.[0] || null)}
                disabled={guardandoProtocolo}
              />
              {archivo && (
                <p style={{ fontSize: 'var(--fs-xs)', color: 'var(--ink-2)', marginTop: 'var(--sp-1)' }}>
                  Seleccionado: {archivo.name}
                </p>
              )}
            </div>

            {errorProtocolo && <div className="alert alert-danger" style={{ marginBottom: 'var(--sp-4)' }}>{errorProtocolo}</div>}

            <button type="submit" className="btn btn-secondary btn-block" disabled={guardandoProtocolo}>
              {guardandoProtocolo ? <span className="spinner" /> : 'Guardar protocolo'}
            </button>
          </form>
        </div>

        <TarjetaImprimirEstado
          estado="aprobado" titulo="APROBADO" estadoMuestra={envio.estado_muestra} idMuestra={envio.id_muestra}
          imprimirFn={muestrasApi.imprimirAprobado}
        />
        <TarjetaImprimirEstado
          estado="rechazado" titulo="RECHAZADO" estadoMuestra={envio.estado_muestra} idMuestra={envio.id_muestra}
          imprimirFn={muestrasApi.imprimirRechazado}
        />
      </div>
    </div>
  );
}
