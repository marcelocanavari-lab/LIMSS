import { useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import TopBar from '../../components/TopBar';
import { muestrasApi } from '../../api/muestras';
import { resultadosApi } from '../../api/resultados';
import { dictamenesApi } from '../../api/dictamenes';
import { ApiError } from '../../api/client';

const ESTADOS = [
  { value: 'aprobado', label: 'Aprobado', className: 'btn-primary' },
  { value: 'rechazado', label: 'Rechazado', className: 'btn-secondary' },
  { value: 'cuarentena', label: 'Cuarentena', className: 'btn-secondary' },
];

export default function DictamenDetallePage() {
  const { id } = useParams();
  const navigate = useNavigate();

  const [muestra, setMuestra] = useState(null);
  const [paraCarga, setParaCarga] = useState(null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);

  const [estadoDictamen, setEstadoDictamen] = useState('');
  const [justificacion, setJustificacion] = useState('');
  const [observaciones, setObservaciones] = useState('');
  const [pin, setPin] = useState('');
  const [guardando, setGuardando] = useState(false);

  useEffect(() => {
    Promise.all([muestrasApi.obtenerMuestra(id), resultadosApi.obtenerParaCarga(id)])
      .then(([m, pc]) => {
        setMuestra(m);
        setParaCarga(pc);
      })
      .catch((err) => setError(err instanceof ApiError ? err.message : 'No se pudo cargar la muestra'))
      .finally(() => setLoading(false));
  }, [id]);

  async function verProtocolo() {
    try {
      const blob = await resultadosApi.descargarProtocolo(id);
      window.open(URL.createObjectURL(blob), '_blank');
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'No se pudo descargar el protocolo');
    }
  }

  const hayOos = paraCarga?.ensayos.some((e) => e.dentro_especificacion === false) || false;

  async function handleSubmit(e) {
    e.preventDefault();
    setError('');

    if (!estadoDictamen) {
      setError('Seleccioná un estado de dictamen');
      return;
    }
    if (hayOos && !justificacion.trim()) {
      setError('Hay resultados OOS: la justificación es obligatoria');
      return;
    }
    if (!pin.trim()) {
      setError('Ingresá tu PIN para firmar el dictamen');
      return;
    }

    setGuardando(true);
    try {
      await dictamenesApi.emitirDictamen(id, {
        estado_dictamen: estadoDictamen,
        justificacion_oos: justificacion.trim() || null,
        observaciones: observaciones.trim() || null,
        pin: pin.trim(),
      });
      navigate('/dictamenes', { replace: true });
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'No se pudo emitir el dictamen');
    } finally {
      setGuardando(false);
      setPin('');
    }
  }

  if (loading) {
    return (
      <div className="screen" style={{ alignItems: 'center', justifyContent: 'center' }}>
        <span className="spinner" />
      </div>
    );
  }

  if (error && !muestra) {
    return (
      <div className="screen">
        <TopBar titulo="Dictamen" subtitulo="Dictamen QA" onBack={() => navigate('/dictamenes')} />
        <div className="screen-content">
          <div className="alert alert-danger">{error}</div>
        </div>
      </div>
    );
  }

  return (
    <div className="screen">
      <TopBar titulo={muestra.codigo_muestra} subtitulo={muestra.erp_DESART} onBack={() => navigate('/dictamenes')} />
      <div className="screen-content">
        <div className="card" style={{ marginBottom: 'var(--sp-5)' }}>
          <table className="data-table">
            <tbody>
              <tr><td>{muestra.tipo_referencia === 'ir' ? 'IR' : 'Lote'}</td><td style={{ textAlign: 'left', fontFamily: 'var(--font-mono)' }}>{muestra.nro_referencia}</td></tr>
              <tr><td>Material</td><td style={{ textAlign: 'left' }}>{muestra.erp_CODART} — {muestra.erp_DESART}</td></tr>
              <tr><td>Proveedor</td><td style={{ textAlign: 'left' }}>{muestra.erp_proveedor || '—'}</td></tr>
            </tbody>
          </table>
          <button className="btn btn-secondary" style={{ marginTop: 'var(--sp-3)' }} onClick={verProtocolo}>
            Ver protocolo (PDF)
          </button>
        </div>

        <div className="card" style={{ marginBottom: 'var(--sp-5)' }}>
          <h2 style={{ fontSize: 'var(--fs-lg)', marginBottom: 'var(--sp-3)' }}>Resultados</h2>
          <table className="data-table">
            <thead>
              <tr>
                <th>Ensayo</th>
                <th>Especificación</th>
                <th>Resultado</th>
                <th>Estado</th>
              </tr>
            </thead>
            <tbody>
              {paraCarga.ensayos.map((en) => {
                const oos = en.dentro_especificacion === false;
                return (
                  <tr key={en.id_ensayo} style={oos ? { background: 'var(--danger-soft)' } : undefined}>
                    <td>{en.nombre_ensayo}</td>
                    <td>
                      {en.tipo_dato === 'numerico'
                        ? `${en.limite_inferior ?? '—'} a ${en.limite_superior ?? '—'} ${en.unidad_medida || ''}`
                        : en.valor_requerido}
                    </td>
                    <td>{en.tipo_dato === 'numerico' ? en.valor_numerico ?? '—' : en.valor_cualitativo ?? '—'}</td>
                    <td>
                      {en.dentro_especificacion === null ? (
                        <span className="badge badge-neutral">Sin resultado</span>
                      ) : oos ? (
                        <span className="badge badge-danger">OOS</span>
                      ) : (
                        <span className="badge badge-ok">OK</span>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>

        <form onSubmit={handleSubmit}>
          <div className="card" style={{ marginBottom: 'var(--sp-5)' }}>
            <h2 style={{ fontSize: 'var(--fs-lg)', marginBottom: 'var(--sp-3)' }}>Dictamen</h2>

            {hayOos && (
              <div className="alert alert-danger" style={{ marginBottom: 'var(--sp-4)' }}>
                Hay resultados fuera de especificación (OOS). Ingresá una justificación técnica o de
                reprocesamiento antes de poder dictaminar.
              </div>
            )}

            <div style={{ display: 'flex', gap: 'var(--sp-3)', marginBottom: 'var(--sp-4)', flexWrap: 'wrap' }}>
              {ESTADOS.map((e) => (
                <button
                  key={e.value}
                  type="button"
                  className={`btn ${estadoDictamen === e.value ? 'btn-primary' : 'btn-secondary'}`}
                  onClick={() => setEstadoDictamen(e.value)}
                  disabled={guardando}
                >
                  {e.label}
                </button>
              ))}
            </div>

            {(hayOos || estadoDictamen === 'rechazado' || estadoDictamen === 'cuarentena') && (
              <div className="field">
                <label className="field-label" htmlFor="justificacion">
                  Justificación {hayOos && '(obligatoria por resultados OOS)'}
                </label>
                <textarea
                  id="justificacion"
                  className="field-input"
                  style={{ height: 96, paddingTop: 'var(--sp-2)' }}
                  value={justificacion}
                  onChange={(e) => setJustificacion(e.target.value)}
                  disabled={guardando}
                />
              </div>
            )}

            <div className="field">
              <label className="field-label" htmlFor="observaciones">Observaciones (opcional)</label>
              <input
                id="observaciones"
                className="field-input"
                value={observaciones}
                onChange={(e) => setObservaciones(e.target.value)}
                disabled={guardando}
              />
            </div>

            <div className="field">
              <label className="field-label" htmlFor="pin">PIN (firma electrónica)</label>
              <input
                id="pin"
                className="field-input field-input-lg"
                type="password"
                inputMode="numeric"
                value={pin}
                onChange={(e) => setPin(e.target.value.replace(/\D/g, '').slice(0, 6))}
                disabled={guardando}
              />
            </div>
          </div>

          {error && <div className="alert alert-danger" style={{ marginBottom: 'var(--sp-4)' }}>{error}</div>}

          <button type="submit" className="btn btn-primary btn-block btn-lg" disabled={guardando}>
            {guardando ? <span className="spinner" /> : 'Firmar dictamen'}
          </button>
        </form>
      </div>
    </div>
  );
}
