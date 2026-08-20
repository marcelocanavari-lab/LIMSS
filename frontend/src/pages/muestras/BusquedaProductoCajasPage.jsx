import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../../context/AuthContext';
import TopBar from '../../components/TopBar';
import { cajasApi } from '../../api/cajas';
import { ApiError } from '../../api/client';

function formatFechaHora(iso) {
  if (!iso) return '—';
  return new Date(iso).toLocaleString('es-AR', { day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit' });
}

export default function BusquedaProductoCajasPage() {
  const navigate = useNavigate();
  const { user } = useAuth();
  const [buscar, setBuscar] = useState('');
  const [buscarUsado, setBuscarUsado] = useState('');
  const [resultados, setResultados] = useState(null);
  const [fechaGeneracion, setFechaGeneracion] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  async function handleBuscar(e) {
    e.preventDefault();
    if (!buscar.trim()) return;
    setLoading(true);
    setError('');
    try {
      const data = await cajasApi.buscarPorProducto(buscar.trim());
      setResultados(data);
      setBuscarUsado(buscar.trim());
      setFechaGeneracion(new Date());
    } catch (err) {
      setResultados(null);
      setError(err instanceof ApiError ? err.message : 'No se pudo buscar');
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="screen">
      <TopBar titulo="Buscar producto en cajas" subtitulo="Archivo de Contramuestras" onBack={() => navigate('/cajas')} />
      <div className="screen-content">
        <form onSubmit={handleBuscar} className="card no-print" style={{ marginBottom: 'var(--sp-5)', display: 'flex', gap: 'var(--sp-2)' }}>
          <input
            className="field-input"
            placeholder="Código de material (CODART) o nombre"
            value={buscar}
            onChange={(e) => setBuscar(e.target.value)}
            autoFocus
          />
          <button type="submit" className="btn btn-primary" disabled={loading}>
            {loading ? <span className="spinner" /> : 'Buscar'}
          </button>
        </form>

        {error && <div className="alert alert-danger no-print" style={{ marginBottom: 'var(--sp-4)' }}>{error}</div>}

        {resultados && (
          <div className="printable">
            <div className="no-print" style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: 'var(--sp-3)' }}>
              <button className="btn btn-secondary" onClick={() => window.print()}>Imprimir / Exportar PDF</button>
            </div>

            <h1 style={{ fontSize: 'var(--fs-lg)', marginBottom: 'var(--sp-2)' }}>Un producto — en qué cajas está</h1>
            <p style={{ color: 'var(--ink-2)', marginBottom: 'var(--sp-4)' }}>
              <b>Búsqueda:</b> "{buscarUsado}" — Generado el {fechaGeneracion?.toLocaleString()} por {user?.nombre} {user?.apellido} ({user?.codigo}) —{' '}
              {resultados.length} resultado{resultados.length === 1 ? '' : 's'}
            </p>

            {resultados.length === 0 ? (
              <div className="state-block"><span className="state-block-title">No hay contramuestras archivadas para esa búsqueda</span></div>
            ) : (
              <div className="reporte-tabla-scroll">
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>Material</th>
                      <th>Código de muestra</th>
                      <th>Caja</th>
                      <th>Estado de la caja</th>
                      <th>Ingreso a la caja</th>
                    </tr>
                  </thead>
                  <tbody>
                    {resultados.map((r) => (
                      <tr key={`${r.id_caja}-${r.id_muestra}`}>
                        <td>{r.erp_DESART} <span style={{ color: 'var(--ink-3)' }}>({r.erp_CODART.trim()})</span></td>
                        <td style={{ fontFamily: 'var(--font-mono)' }}>{r.codigo_muestra}</td>
                        <td style={{ fontFamily: 'var(--font-mono)', cursor: 'pointer' }} onClick={() => navigate(`/cajas/${r.id_caja}`)}>
                          {r.codigo_caja}
                        </td>
                        <td><span className={r.estado_caja === 'activa' ? 'badge badge-ok' : 'badge badge-neutral'}>{r.estado_caja === 'activa' ? 'Activa' : 'Cerrada'}</span></td>
                        <td style={{ whiteSpace: 'nowrap' }}>{formatFechaHora(r.fecha_ingreso)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
