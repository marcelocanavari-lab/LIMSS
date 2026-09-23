import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import TopBar from '../../components/TopBar';
import { muestrasApi } from '../../api/muestras';
import { ApiError } from '../../api/client';

function formatFechaHora(fechaISO) {
  return new Date(fechaISO).toLocaleString();
}

export default function MuestrasSinChecklistPage() {
  const navigate = useNavigate();

  const [muestras, setMuestras] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const [seleccionadas, setSeleccionadas] = useState(new Set());
  const [motivo, setMotivo] = useState('');
  const [procesando, setProcesando] = useState(false);
  const [errorAccion, setErrorAccion] = useState('');
  const [resultados, setResultados] = useState(null); // DestrabarSinChecklistResponse.resultados | null

  function cargar() {
    setLoading(true);
    setError('');
    muestrasApi
      .listarSinChecklist()
      .then((data) => {
        setMuestras(data);
        setSeleccionadas(new Set());
      })
      .catch((err) => setError(err instanceof ApiError ? err.message : 'No se pudo cargar el listado'))
      .finally(() => setLoading(false));
  }

  useEffect(cargar, []);

  function toggleSeleccion(idMuestra) {
    setSeleccionadas((prev) => {
      const nuevo = new Set(prev);
      if (nuevo.has(idMuestra)) nuevo.delete(idMuestra);
      else nuevo.add(idMuestra);
      return nuevo;
    });
  }

  function toggleTodas() {
    setSeleccionadas((prev) => (prev.size === muestras.length ? new Set() : new Set(muestras.map((m) => m.id_muestra))));
  }

  async function handleDestrabar() {
    if (seleccionadas.size === 0) {
      setErrorAccion('Seleccioná al menos una muestra');
      return;
    }
    if (!motivo.trim()) {
      setErrorAccion('El motivo es obligatorio');
      return;
    }
    setErrorAccion('');
    setResultados(null);
    setProcesando(true);
    try {
      const respuesta = await muestrasApi.destrabarSinChecklist([...seleccionadas], motivo.trim());
      setResultados(respuesta.resultados);
      setMotivo('');
      cargar();
    } catch (err) {
      setErrorAccion(err instanceof ApiError ? err.message : 'No se pudo destrabar el lote');
    } finally {
      setProcesando(false);
    }
  }

  return (
    <div className="screen">
      <TopBar
        titulo="Muestras sin checklist completo"
        subtitulo="Atascadas: sin ensayos de análisis y checklist de muestreo incompleto"
        onBack={() => navigate(-1)}
      />
      <div className="screen-content">
        <div className="alert alert-warn" style={{ marginBottom: 'var(--sp-4)' }}>
          Estas muestras no pueden llegar a la Bandeja de Dictamen por el flujo normal: su
          especificación no tiene ningún ensayo de análisis (no corresponde Envío/Carga de
          Resultados) y su checklist de muestreo quedó incompleto sin posibilidad de completarse
          retroactivamente. Usá "Destrabar" solo cuando confirmaste que no hay forma real de
          completar el checklist -- queda registrado en el historial de auditoría de cada muestra,
          con el ítem marcado explícitamente como "N/A - Destrabado manualmente" (no se simula
          ningún resultado).
        </div>

        {error && <div className="alert alert-danger" style={{ marginBottom: 'var(--sp-4)' }}>{error}</div>}

        {loading ? (
          <div className="state-block"><span className="spinner" /></div>
        ) : muestras.length === 0 ? (
          <div className="state-block">
            <span className="state-block-title">Sin muestras atascadas</span>
            <span>No hay ninguna muestra en esta condición ahora mismo.</span>
          </div>
        ) : (
          <>
            <div className="table-scroll" style={{ marginBottom: 'var(--sp-4)' }}>
              <table className="data-table">
                <thead>
                  <tr>
                    <th><input type="checkbox" checked={seleccionadas.size === muestras.length} onChange={toggleTodas} /></th>
                    <th>Muestra</th>
                    <th>Material</th>
                    <th>Especificación</th>
                    <th>Checklist</th>
                    <th>Fecha de muestreo</th>
                  </tr>
                </thead>
                <tbody>
                  {muestras.map((m) => (
                    <tr key={m.id_muestra} style={{ cursor: 'pointer' }} onClick={() => toggleSeleccion(m.id_muestra)}>
                      <td onClick={(e) => e.stopPropagation()}>
                        <input type="checkbox" checked={seleccionadas.has(m.id_muestra)} onChange={() => toggleSeleccion(m.id_muestra)} />
                      </td>
                      <td style={{ fontFamily: 'var(--font-mono)' }}>{m.codigo_muestra}</td>
                      <td>{m.erp_DESART} <span style={{ color: 'var(--ink-3)' }}>({m.erp_CODART.trim()})</span></td>
                      <td>#{m.id_especificacion}</td>
                      <td>
                        <span className="badge badge-warn">{m.ensayos_faltantes} de {m.ensayos_totales} sin responder</span>
                      </td>
                      <td style={{ whiteSpace: 'nowrap' }}>{formatFechaHora(m.fecha_muestreo)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <div className="card" style={{ marginBottom: 'var(--sp-4)' }}>
              <h2 style={{ fontSize: 'var(--fs-lg)', marginBottom: 'var(--sp-3)' }}>
                Destrabar seleccionadas ({seleccionadas.size})
              </h2>
              <div className="field" style={{ marginBottom: 'var(--sp-3)' }}>
                <label className="field-label" htmlFor="motivo">Motivo (obligatorio, se aplica a todo el lote)</label>
                <textarea
                  id="motivo"
                  className="field-input"
                  rows={3}
                  value={motivo}
                  onChange={(e) => setMotivo(e.target.value)}
                  disabled={procesando}
                />
              </div>
              {errorAccion && <div className="alert alert-danger" style={{ marginBottom: 'var(--sp-3)' }}>{errorAccion}</div>}
              <button type="button" className="btn btn-primary" onClick={handleDestrabar} disabled={procesando}>
                {procesando ? <span className="spinner" /> : `Destrabar ${seleccionadas.size} muestra(s)`}
              </button>
            </div>
          </>
        )}

        {resultados && (
          <div className="card">
            <h2 style={{ fontSize: 'var(--fs-lg)', marginBottom: 'var(--sp-3)' }}>Resultado</h2>
            <table className="data-table data-table-compact">
              <thead>
                <tr><th>Muestra</th><th>Resultado</th></tr>
              </thead>
              <tbody>
                {resultados.map((r) => (
                  <tr key={r.id_muestra}>
                    <td style={{ fontFamily: 'var(--font-mono)' }}>{r.codigo_muestra || `#${r.id_muestra}`}</td>
                    <td>
                      <span className={`badge ${r.ok ? 'badge-ok' : 'badge-danger'}`}>{r.ok ? 'Destrabada' : 'No aplicable'}</span>
                      {' '}{r.detalle}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
