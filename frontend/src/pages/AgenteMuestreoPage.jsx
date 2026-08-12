import { Fragment, useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import TopBar from '../components/TopBar';
import { agenteMuestreoApi } from '../api/agenteMuestreo';
import { ApiError } from '../api/client';

const FILTROS_RESULTADO = [
  { value: '', label: 'Todos' },
  { value: 'solicitud_generada', label: 'Solicitud generada' },
  { value: 'no_requiere_muestreo', label: 'No requiere muestreo' },
  { value: 'subarticulo_no_configurado', label: 'Subartículo no configurado' },
  { value: 'error', label: 'Error' },
];

const BADGE_RESULTADO = {
  solicitud_generada: 'badge-ok',
  no_requiere_muestreo: 'badge-neutral',
  subarticulo_no_configurado: 'badge-warn',
  error: 'badge-danger',
};

function labelResultado(resultado) {
  return FILTROS_RESULTADO.find((f) => f.value === resultado)?.label || resultado;
}

function formatFechaHora(iso) {
  return new Date(iso).toLocaleString();
}

export default function AgenteMuestreoPage() {
  const navigate = useNavigate();

  const [resultado, setResultado] = useState('');
  const [idComprobante, setIdComprobante] = useState('');
  const [evaluaciones, setEvaluaciones] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [expandidas, setExpandidas] = useState({});
  const [reprocesandoId, setReprocesandoId] = useState(null);
  const [ejecutandoAhora, setEjecutandoAhora] = useState(false);
  const [mensajeCiclo, setMensajeCiclo] = useState('');

  function cargar() {
    setLoading(true);
    setError('');
    agenteMuestreoApi
      .listarEvaluaciones({
        resultado: resultado || undefined,
        idComprobanteErp: idComprobante || undefined,
      })
      .then(setEvaluaciones)
      .catch((err) => setError(err instanceof ApiError ? err.message : 'No se pudo cargar el listado'))
      .finally(() => setLoading(false));
  }

  useEffect(cargar, [resultado]);

  function buscarPorComprobante(e) {
    e.preventDefault();
    cargar();
  }

  function toggleExpandida(id) {
    setExpandidas((prev) => ({ ...prev, [id]: !prev[id] }));
  }

  async function reprocesar(idComprobanteErp) {
    setError('');
    setReprocesandoId(idComprobanteErp);
    try {
      await agenteMuestreoApi.reprocesar(idComprobanteErp);
      cargar();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'No se pudo reprocesar el comprobante');
    } finally {
      setReprocesandoId(null);
    }
  }

  async function ejecutarAhora() {
    setError('');
    setMensajeCiclo('');
    setEjecutandoAhora(true);
    try {
      const resp = await agenteMuestreoApi.ejecutarAhora();
      setMensajeCiclo(
        `Ciclo ejecutado: ${resp.comprobantes_nuevos} IR nuevo(s) encontrado(s), ${resp.comprobantes_procesados} evaluado(s) (último N01Id: ${resp.ultimo_n01id}).`
      );
      cargar();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'No se pudo ejecutar el ciclo del agente');
    } finally {
      setEjecutandoAhora(false);
    }
  }

  return (
    <div className="screen">
      <TopBar titulo="Agente de Muestreo" subtitulo="Evaluaciones automáticas de IR" onBack={() => navigate(-1)} />
      <div className="screen-content">
        <p style={{ color: 'var(--ink-2)', marginBottom: 'var(--sp-4)' }}>
          Historial de evaluaciones del agente que detecta Informes de Recepción (IR) nuevos en el ERP y
          genera la Solicitud de Muestreo automáticamente cuando corresponde. Los subartículos que
          requieren muestreo se configuran en{' '}
          <a href="/subarticulos-config" style={{ color: 'inherit', textDecoration: 'underline' }}>Subartículos y Muestreo</a>.
        </p>

        <div style={{ display: 'flex', gap: 'var(--sp-3)', marginBottom: 'var(--sp-4)', alignItems: 'center', flexWrap: 'wrap' }}>
          <select className="field-input" style={{ maxWidth: 240 }} value={resultado} onChange={(e) => setResultado(e.target.value)}>
            {FILTROS_RESULTADO.map((f) => (
              <option key={f.value} value={f.value}>{f.label}</option>
            ))}
          </select>
          <form onSubmit={buscarPorComprobante} style={{ display: 'flex', gap: 'var(--sp-2)' }}>
            <input
              className="field-input"
              style={{ maxWidth: 180 }}
              placeholder="N01Id del comprobante"
              value={idComprobante}
              onChange={(e) => setIdComprobante(e.target.value)}
            />
            <button type="submit" className="btn btn-secondary">Buscar</button>
          </form>
          <div style={{ flex: 1 }} />
          <button className="btn btn-primary" onClick={ejecutarAhora} disabled={ejecutandoAhora}>
            {ejecutandoAhora ? <span className="spinner" /> : 'Ejecutar ciclo ahora'}
          </button>
        </div>

        {mensajeCiclo && <div className="alert alert-ok" style={{ marginBottom: 'var(--sp-4)' }}>{mensajeCiclo}</div>}
        {error && <div className="alert alert-danger" style={{ marginBottom: 'var(--sp-4)' }}>{error}</div>}

        {loading ? (
          <div className="state-block"><span className="spinner" /></div>
        ) : evaluaciones.length === 0 ? (
          <div className="state-block">
            <span className="state-block-title">Sin evaluaciones</span>
            <span>Todavía no hay comprobantes evaluados por el agente con estos filtros</span>
          </div>
        ) : (
          <div className="table-scroll">
            <table className="data-table data-table-compact">
              <thead>
                <tr>
                  <th>N01Id</th>
                  <th>Material</th>
                  <th>Resultado</th>
                  <th>Solicitud</th>
                  <th>Fecha</th>
                  <th>Reintentos</th>
                  <th>Acciones</th>
                </tr>
              </thead>
              <tbody>
                {evaluaciones.map((ev) => (
                  <Fragment key={ev.id}>
                    <tr>
                      <td style={{ fontFamily: 'var(--font-mono)' }}>{ev.id_comprobante_erp}</td>
                      <td>{ev.erp_codart?.trim() || '—'} <span style={{ color: 'var(--ink-3)' }}>({ev.erp_codsar || '—'})</span></td>
                      <td><span className={`badge ${BADGE_RESULTADO[ev.resultado] || 'badge-neutral'}`}>{labelResultado(ev.resultado)}</span></td>
                      <td style={{ fontFamily: 'var(--font-mono)' }}>{ev.nro_solicitud_generada || '—'}</td>
                      <td>{formatFechaHora(ev.fecha_evaluacion)}</td>
                      <td>{ev.reintentos}</td>
                      <td className="acciones-compactas">
                        <button className="btn btn-ghost" onClick={() => toggleExpandida(ev.id)}>
                          {expandidas[ev.id] ? 'Ocultar log' : 'Ver log'}
                        </button>
                        <button
                          className="btn btn-ghost"
                          onClick={() => reprocesar(ev.id_comprobante_erp)}
                          disabled={reprocesandoId === ev.id_comprobante_erp}
                        >
                          {reprocesandoId === ev.id_comprobante_erp ? <span className="spinner" /> : 'Reprocesar'}
                        </button>
                      </td>
                    </tr>
                    {expandidas[ev.id] && (
                      <tr key={`${ev.id}-log`}>
                        <td colSpan={7} style={{ background: 'var(--surf-2)' }}>
                          {ev.logs.length === 0 ? (
                            <span style={{ color: 'var(--ink-3)' }}>Sin entradas de log</span>
                          ) : (
                            <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--sp-2)' }}>
                              {ev.logs.map((log) => (
                                <div key={log.id} style={{ fontSize: 'var(--fs-sm)' }}>
                                  <strong>{formatFechaHora(log.fecha_hora)}</strong> — {log.decision || '—'}
                                  {log.justificacion && <div>{log.justificacion}</div>}
                                  {log.error_detalle && (
                                    <div style={{ color: 'var(--danger)' }}>{log.error_detalle}</div>
                                  )}
                                </div>
                              ))}
                            </div>
                          )}
                        </td>
                      </tr>
                    )}
                  </Fragment>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
