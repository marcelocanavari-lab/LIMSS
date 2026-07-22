import { useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { dictamenesApi } from '../../api/dictamenes';
import { resultadosApi } from '../../api/resultados';
import TopBar from '../../components/TopBar';
import { ApiError } from '../../api/client';

const ESTADOS = [
  { value: 'aprobado', label: 'Aprobado' },
  { value: 'rechazado', label: 'Rechazado' },
  { value: 'cuarentena', label: 'Cuarentena' },
];

function labelEstado(valor) {
  return ESTADOS.find((e) => e.value === valor)?.label || valor;
}

export default function DictamenDetallePage() {
  const { id } = useParams();
  const navigate = useNavigate();

  const [detalle, setDetalle] = useState(null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);

  const [estadoDictamen, setEstadoDictamen] = useState('');
  const [justificacion, setJustificacion] = useState('');
  const [observaciones, setObservaciones] = useState('');
  const [pin, setPin] = useState('');
  const [guardando, setGuardando] = useState(false);

  function cargar() {
    setLoading(true);
    dictamenesApi
      .obtenerDetalle(id)
      .then(setDetalle)
      .catch((err) => setError(err instanceof ApiError ? err.message : 'No se pudo cargar la muestra'))
      .finally(() => setLoading(false));
  }

  useEffect(cargar, [id]);

  async function verProtocolo() {
    try {
      const blob = await resultadosApi.descargarProtocolo(id);
      window.open(URL.createObjectURL(blob), '_blank');
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'No se pudo descargar el protocolo');
    }
  }

  const hayOos = detalle?.hay_oos || false;
  const justificacionOk = !hayOos || justificacion.trim().length > 0;
  const puedeConfirmar =
    !!estadoDictamen && justificacionOk && pin.trim().length >= 4 && !guardando;

  async function handleSubmit(e) {
    e.preventDefault();
    setError('');

    if (!puedeConfirmar) return;

    setGuardando(true);
    try {
      await dictamenesApi.emitirDictamen(id, {
        estado_dictamen: estadoDictamen,
        justificacion_oos: justificacion.trim() || null,
        observaciones: observaciones.trim() || null,
        pin_confirmacion: pin.trim(),
      });
      navigate('/dictamenes', { replace: true });
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'No se pudo emitir el dictamen');
      setPin('');
    } finally {
      setGuardando(false);
    }
  }

  if (loading) {
    return (
      <div className="screen" style={{ alignItems: 'center', justifyContent: 'center' }}>
        <span className="spinner" />
      </div>
    );
  }

  if (error && !detalle) {
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
      <TopBar titulo={detalle.codigo_muestra} subtitulo={detalle.erp_DESART} onBack={() => navigate('/dictamenes')} />
      <div className="screen-content">
        <div className="card" style={{ marginBottom: 'var(--sp-5)' }}>
          <table className="data-table">
            <tbody>
              <tr><td>{detalle.tipo_referencia === 'ir' ? 'IR' : 'Lote'}</td><td style={{ textAlign: 'left', fontFamily: 'var(--font-mono)' }}>{detalle.nro_referencia}</td></tr>
              <tr><td>Material</td><td style={{ textAlign: 'left' }}>{detalle.erp_CODART} — {detalle.erp_DESART}</td></tr>
              <tr><td>Fecha de muestreo</td><td style={{ textAlign: 'left' }}>{new Date(detalle.fecha_muestreo).toLocaleString()}</td></tr>
              <tr><td>Muestreador</td><td style={{ textAlign: 'left' }}>{detalle.usuario_muestreo_nombre}</td></tr>
            </tbody>
          </table>
        </div>

        {detalle.envio && (
          <div className="card" style={{ marginBottom: 'var(--sp-5)' }}>
            <h2 style={{ fontSize: 'var(--fs-lg)', marginBottom: 'var(--sp-3)' }}>Envío</h2>
            <table className="data-table">
              <tbody>
                <tr><td>Laboratorio</td><td style={{ textAlign: 'left' }}>{detalle.envio.laboratorio_nombre}</td></tr>
                <tr><td>Fecha de despacho</td><td style={{ textAlign: 'left' }}>{new Date(detalle.envio.fecha_despacho).toLocaleString()}</td></tr>
                {detalle.envio.testigo_codigo && (
                  <tr><td>Testigo</td><td style={{ textAlign: 'left' }}>{detalle.envio.testigo_codigo} — {detalle.envio.testigo_nombre}</td></tr>
                )}
              </tbody>
            </table>
          </div>
        )}

        {detalle.protocolo && (
          <div className="card" style={{ marginBottom: 'var(--sp-5)' }}>
            <h2 style={{ fontSize: 'var(--fs-lg)', marginBottom: 'var(--sp-3)' }}>Protocolo</h2>
            <table className="data-table">
              <tbody>
                <tr><td>N° protocolo externo</td><td style={{ textAlign: 'left' }}>{detalle.protocolo.nro_protocolo_ext}</td></tr>
                <tr><td>Fecha de emisión</td><td style={{ textAlign: 'left' }}>{detalle.protocolo.fecha_emision}</td></tr>
              </tbody>
            </table>
            <button className="btn btn-secondary" style={{ marginTop: 'var(--sp-3)' }} onClick={verProtocolo}>
              Ver protocolo (PDF)
            </button>
          </div>
        )}

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
              {detalle.ensayos.map((en) => {
                const oos = en.dentro_especificacion === false;
                return (
                  <tr key={en.id_espec_ensayo} style={oos ? { background: 'var(--danger-soft)' } : undefined}>
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
                        <span className="badge badge-danger">● OOS</span>
                      ) : (
                        <span className="badge badge-ok">● OK</span>
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
          </div>

          {estadoDictamen && (
            <div className="card" style={{ marginBottom: 'var(--sp-5)', background: 'var(--surf-2)' }}>
              <h2 style={{ fontSize: 'var(--fs-lg)', marginBottom: 'var(--sp-3)' }}>Previsualización</h2>
              <table className="data-table">
                <tbody>
                  <tr><td>Muestra</td><td style={{ textAlign: 'left' }}>{detalle.codigo_muestra}</td></tr>
                  <tr><td>Dictamen</td><td style={{ textAlign: 'left' }}><b>{labelEstado(estadoDictamen)}</b></td></tr>
                  {justificacion.trim() && <tr><td>Justificación</td><td style={{ textAlign: 'left' }}>{justificacion.trim()}</td></tr>}
                  {observaciones.trim() && <tr><td>Observaciones</td><td style={{ textAlign: 'left' }}>{observaciones.trim()}</td></tr>}
                </tbody>
              </table>
            </div>
          )}

          <div className="card" style={{ marginBottom: 'var(--sp-5)' }}>
            <h2 style={{ fontSize: 'var(--fs-lg)', marginBottom: 'var(--sp-3)' }}>Firma electrónica</h2>
            <div className="field">
              <label className="field-label" htmlFor="pin">PIN de confirmación</label>
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

          <button type="submit" className="btn btn-primary btn-block btn-lg" disabled={!puedeConfirmar}>
            {guardando ? <span className="spinner" /> : 'Firmar y dictaminar'}
          </button>
        </form>
      </div>
    </div>
  );
}
