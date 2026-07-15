import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../../context/AuthContext';
import TopBar from '../../components/TopBar';
import { maestrosApi } from '../../api/maestros';
import { ApiError } from '../../api/client';

function badgesEstado(t) {
  const badges = [];
  if (t.vencido) badges.push(<span key="v" className="badge badge-danger">Vencido</span>);
  else if (t.por_vencer) badges.push(<span key="pv" className="badge badge-warn">Por vencer</span>);
  if (t.stock_bajo) badges.push(<span key="sb" className="badge badge-warn">Stock bajo</span>);
  if (!t.activo) badges.push(<span key="ia" className="badge badge-neutral">Inactivo</span>);
  if (badges.length === 0) badges.push(<span key="ok" className="badge badge-ok">Normal</span>);
  return badges;
}

export default function TestigosPage() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const puedeGestionar = ['admin', 'qa'].includes(user?.rol);

  const [testigos, setTestigos] = useState([]);
  const [buscar, setBuscar] = useState('');
  const [soloAlertas, setSoloAlertas] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    let activo = true;
    setLoading(true);
    setError('');
    maestrosApi
      .listarTestigos({ buscar, soloAlertas })
      .then((data) => activo && setTestigos(data))
      .catch((err) => activo && setError(err instanceof ApiError ? err.message : 'No se pudo cargar el listado'))
      .finally(() => activo && setLoading(false));
    return () => {
      activo = false;
    };
  }, [buscar, soloAlertas]);

  return (
    <div className="screen">
      <TopBar titulo="Testigos y Estándares" subtitulo="Datos Maestros" onBack={() => navigate('/menu')} />
      <div className="screen-content">
        <div style={{ display: 'flex', gap: 'var(--sp-3)', marginBottom: 'var(--sp-4)', flexWrap: 'wrap' }}>
          <input
            className="field-input"
            style={{ flex: 1, minWidth: 200 }}
            placeholder="Buscar por código o nombre..."
            value={buscar}
            onChange={(e) => setBuscar(e.target.value)}
          />
          <button
            className={soloAlertas ? 'btn btn-primary' : 'btn btn-secondary'}
            onClick={() => setSoloAlertas((v) => !v)}
          >
            {soloAlertas ? 'Con alertas' : 'Todos'}
          </button>
          {puedeGestionar && (
            <button className="btn btn-primary" onClick={() => navigate('/maestros/testigos/nuevo')}>
              + Nuevo testigo
            </button>
          )}
        </div>

        {error && <div className="alert alert-danger" style={{ marginBottom: 'var(--sp-4)' }}>{error}</div>}

        {loading ? (
          <div className="state-block"><span className="spinner" /></div>
        ) : testigos.length === 0 ? (
          <div className="state-block">
            <span className="state-block-title">Sin testigos</span>
            <span>No hay testigos cargados con estos filtros</span>
          </div>
        ) : (
          <table className="data-table">
            <thead>
              <tr>
                <th>Código</th>
                <th>Nombre</th>
                <th>Lote</th>
                <th>Vencimiento</th>
                <th>Stock</th>
                <th>Estado</th>
              </tr>
            </thead>
            <tbody>
              {testigos.map((t) => (
                <tr
                  key={t.id_testigo}
                  style={{ cursor: 'pointer' }}
                  onClick={() => navigate(`/maestros/testigos/${t.id_testigo}`)}
                >
                  <td style={{ fontFamily: 'var(--font-mono)' }}>{t.codigo}</td>
                  <td>{t.nombre}</td>
                  <td>{t.nro_lote}</td>
                  <td className="num">{t.fecha_vencimiento}</td>
                  <td className="num">{t.stock_actual} {t.unidad_medida || ''}</td>
                  <td style={{ display: 'flex', gap: 4, flexWrap: 'wrap' }}>{badgesEstado(t)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
