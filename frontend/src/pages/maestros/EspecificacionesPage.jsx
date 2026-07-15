import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../../context/AuthContext';
import TopBar from '../../components/TopBar';
import { maestrosApi } from '../../api/maestros';
import { ApiError } from '../../api/client';

export default function EspecificacionesPage() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const puedeGestionar = ['admin', 'qa'].includes(user?.rol);

  const [especificaciones, setEspecificaciones] = useState([]);
  const [buscar, setBuscar] = useState('');
  const [soloVigentes, setSoloVigentes] = useState(true);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    let activo = true;
    setLoading(true);
    setError('');
    maestrosApi
      .listarEspecificaciones({ vigente: soloVigentes ? true : null, buscar })
      .then((data) => activo && setEspecificaciones(data))
      .catch((err) => activo && setError(err instanceof ApiError ? err.message : 'No se pudo cargar el listado'))
      .finally(() => activo && setLoading(false));
    return () => {
      activo = false;
    };
  }, [buscar, soloVigentes]);

  return (
    <div className="screen">
      <TopBar titulo="Especificaciones" subtitulo="Datos Maestros" onBack={() => navigate('/menu')} />
      <div className="screen-content">
        <div style={{ display: 'flex', gap: 'var(--sp-3)', marginBottom: 'var(--sp-4)', flexWrap: 'wrap' }}>
          <input
            className="field-input"
            style={{ flex: 1, minWidth: 200 }}
            placeholder="Buscar por código o descripción..."
            value={buscar}
            onChange={(e) => setBuscar(e.target.value)}
          />
          <button
            className={soloVigentes ? 'btn btn-primary' : 'btn btn-secondary'}
            onClick={() => setSoloVigentes((v) => !v)}
          >
            {soloVigentes ? 'Solo vigentes' : 'Todas las versiones'}
          </button>
          {puedeGestionar && (
            <button className="btn btn-primary" onClick={() => navigate('/maestros/especificaciones/nueva')}>
              + Nueva especificación
            </button>
          )}
        </div>

        {error && <div className="alert alert-danger" style={{ marginBottom: 'var(--sp-4)' }}>{error}</div>}

        {loading ? (
          <div className="state-block"><span className="spinner" /></div>
        ) : especificaciones.length === 0 ? (
          <div className="state-block">
            <span className="state-block-title">Sin especificaciones</span>
            <span>No hay fichas cargadas con estos filtros</span>
          </div>
        ) : (
          <table className="data-table">
            <thead>
              <tr>
                <th>Código</th>
                <th>Descripción</th>
                <th>Tipo</th>
                <th>Versión</th>
                <th>Estado</th>
              </tr>
            </thead>
            <tbody>
              {especificaciones.map((e) => (
                <tr
                  key={e.id_especificacion}
                  style={{ cursor: 'pointer' }}
                  onClick={() => navigate(`/maestros/especificaciones/${e.id_especificacion}`)}
                >
                  <td className="num" style={{ textAlign: 'left', fontFamily: 'var(--font-mono)' }}>{e.erp_CODART}</td>
                  <td>{e.erp_DESART}</td>
                  <td>{e.tipo_material.replace('_', ' ')}</td>
                  <td className="num">{e.version}</td>
                  <td>
                    {e.vigente ? (
                      <span className="badge badge-ok">Vigente</span>
                    ) : (
                      <span className="badge badge-neutral">Obsoleta</span>
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
