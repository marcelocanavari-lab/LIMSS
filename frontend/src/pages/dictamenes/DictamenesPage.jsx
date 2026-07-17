import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import TopBar from '../../components/TopBar';
import { dictamenesApi } from '../../api/dictamenes';
import { ApiError } from '../../api/client';

export default function DictamenesPage() {
  const navigate = useNavigate();

  const [pendientes, setPendientes] = useState([]);
  const [buscar, setBuscar] = useState('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    dictamenesApi
      .listarPendientes()
      .then(setPendientes)
      .catch((err) => setError(err instanceof ApiError ? err.message : 'No se pudo cargar el listado'))
      .finally(() => setLoading(false));
  }, []);

  const filtrados = pendientes.filter((p) => {
    const q = buscar.trim().toLowerCase();
    if (!q) return true;
    return p.codigo_muestra.toLowerCase().includes(q) || p.erp_DESART.toLowerCase().includes(q);
  });

  return (
    <div className="screen">
      <TopBar titulo="Dictamen QA" subtitulo="Bandeja de dictámenes pendientes" onBack={() => navigate('/menu')} />
      <div className="screen-content">
        <input
          className="field-input"
          style={{ width: '100%', marginBottom: 'var(--sp-4)' }}
          placeholder="Buscar por código o material..."
          value={buscar}
          onChange={(e) => setBuscar(e.target.value)}
        />

        {error && <div className="alert alert-danger" style={{ marginBottom: 'var(--sp-4)' }}>{error}</div>}

        {loading ? (
          <div className="state-block"><span className="spinner" /></div>
        ) : filtrados.length === 0 ? (
          <div className="state-block">
            <span className="state-block-title">Sin pendientes</span>
            <span>No hay muestras esperando dictamen</span>
          </div>
        ) : (
          <table className="data-table">
            <thead>
              <tr>
                <th>Código</th>
                <th>Material</th>
                <th>Laboratorio</th>
                <th>Fecha muestreo</th>
                <th>Resultados</th>
              </tr>
            </thead>
            <tbody>
              {filtrados.map((p) => (
                <tr key={p.id_muestra} style={{ cursor: 'pointer' }} onClick={() => navigate(`/dictamenes/muestras/${p.id_muestra}`)}>
                  <td style={{ fontFamily: 'var(--font-mono)' }}>{p.codigo_muestra}</td>
                  <td>{p.erp_CODART} — {p.erp_DESART}</td>
                  <td>{p.laboratorio_nombre}</td>
                  <td>{new Date(p.fecha_muestreo).toLocaleDateString()}</td>
                  <td>
                    {p.cantidad_oos > 0 ? (
                      <span className="badge badge-danger">{p.cantidad_oos} OOS</span>
                    ) : (
                      <span className="badge badge-ok">OK</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
