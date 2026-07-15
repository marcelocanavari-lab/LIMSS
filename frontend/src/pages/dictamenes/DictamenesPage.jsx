import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import TopBar from '../../components/TopBar';
import { muestrasApi } from '../../api/muestras';
import { ApiError } from '../../api/client';

export default function DictamenesPage() {
  const navigate = useNavigate();

  const [muestras, setMuestras] = useState([]);
  const [buscar, setBuscar] = useState('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    let activo = true;
    setLoading(true);
    setError('');
    muestrasApi
      .listarMuestras({ estado: 'pendiente_dictamen', buscar })
      .then((data) => activo && setMuestras(data))
      .catch((err) => activo && setError(err instanceof ApiError ? err.message : 'No se pudo cargar el listado'))
      .finally(() => activo && setLoading(false));
    return () => {
      activo = false;
    };
  }, [buscar]);

  return (
    <div className="screen">
      <TopBar titulo="Dictamen QA" subtitulo="Pendientes de liberación" onBack={() => navigate('/menu')} />
      <div className="screen-content">
        <input
          className="field-input"
          style={{ width: '100%', marginBottom: 'var(--sp-4)' }}
          placeholder="Buscar por código, IR o material..."
          value={buscar}
          onChange={(e) => setBuscar(e.target.value)}
        />

        {error && <div className="alert alert-danger" style={{ marginBottom: 'var(--sp-4)' }}>{error}</div>}

        {loading ? (
          <div className="state-block"><span className="spinner" /></div>
        ) : muestras.length === 0 ? (
          <div className="state-block">
            <span className="state-block-title">Sin pendientes</span>
            <span>No hay muestras esperando dictamen</span>
          </div>
        ) : (
          <table className="data-table">
            <thead>
              <tr>
                <th>Código</th>
                <th>IR / Lote</th>
                <th>Material</th>
                <th>Fecha muestreo</th>
              </tr>
            </thead>
            <tbody>
              {muestras.map((m) => (
                <tr key={m.id_muestra} style={{ cursor: 'pointer' }} onClick={() => navigate(`/dictamenes/muestras/${m.id_muestra}`)}>
                  <td style={{ fontFamily: 'var(--font-mono)' }}>{m.codigo_muestra}</td>
                  <td style={{ fontFamily: 'var(--font-mono)' }}>{m.tipo_referencia === 'ir' ? 'IR' : 'Lote'} {m.nro_referencia}</td>
                  <td>{m.erp_DESART}</td>
                  <td>{new Date(m.fecha_muestreo).toLocaleDateString()}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
