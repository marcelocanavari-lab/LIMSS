import { useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { useAuth } from '../../context/AuthContext';
import TopBar from '../../components/TopBar';
import { maestrosApi } from '../../api/maestros';
import { ApiError } from '../../api/client';

export default function EspecificacionDetallePage() {
  const { id } = useParams();
  const navigate = useNavigate();
  const { user } = useAuth();
  const puedeGestionar = ['admin', 'qa'].includes(user?.rol);

  const [especificacion, setEspecificacion] = useState(null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    maestrosApi
      .obtenerEspecificacion(id)
      .then(setEspecificacion)
      .catch((err) => setError(err instanceof ApiError ? err.message : 'No se pudo cargar la especificación'))
      .finally(() => setLoading(false));
  }, [id]);

  if (loading) {
    return (
      <div className="screen" style={{ alignItems: 'center', justifyContent: 'center' }}>
        <span className="spinner" />
      </div>
    );
  }

  if (error || !especificacion) {
    return (
      <div className="screen">
        <TopBar titulo="Especificación" subtitulo="Datos Maestros" onBack={() => navigate('/maestros/especificaciones')} />
        <div className="screen-content">
          <div className="alert alert-danger">{error || 'No encontrada'}</div>
        </div>
      </div>
    );
  }

  return (
    <div className="screen">
      <TopBar titulo={especificacion.erp_DESART} subtitulo="Ficha de especificación" onBack={() => navigate('/maestros/especificaciones')} />
      <div className="screen-content">
        <div className="card" style={{ marginBottom: 'var(--sp-5)' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 'var(--sp-3)' }}>
            <div>
              <div style={{ fontFamily: 'var(--font-mono)', color: 'var(--ink-2)', fontSize: 'var(--fs-sm)' }}>
                {especificacion.erp_CODART}
              </div>
              <h1 style={{ fontSize: 'var(--fs-xl)' }}>{especificacion.erp_DESART}</h1>
            </div>
            {especificacion.vigente ? (
              <span className="badge badge-ok">Vigente</span>
            ) : (
              <span className="badge badge-neutral">Obsoleta</span>
            )}
          </div>

          <div style={{ display: 'flex', gap: 'var(--sp-5)', fontSize: 'var(--fs-sm)', color: 'var(--ink-2)' }}>
            <span>Tipo: <strong style={{ color: 'var(--ink-1)' }}>{especificacion.tipo_material.replace('_', ' ')}</strong></span>
            <span>Versión: <strong style={{ color: 'var(--ink-1)' }}>{especificacion.version}</strong></span>
          </div>

          {especificacion.vigente && puedeGestionar && (
            <button
              className="btn btn-secondary"
              style={{ marginTop: 'var(--sp-4)' }}
              onClick={() => navigate(`/maestros/especificaciones/${id}/revisar`)}
            >
              Revisar (crear nueva versión) →
            </button>
          )}
        </div>

        <h2 style={{ fontSize: 'var(--fs-lg)', marginBottom: 'var(--sp-3)' }}>Ensayos ({especificacion.ensayos.length})</h2>
        <table className="data-table">
          <thead>
            <tr>
              <th>#</th>
              <th>Ensayo</th>
              <th>Metodología</th>
              <th>Tipo</th>
              <th>Límites / Valor requerido</th>
              <th>Obligatorio</th>
              <th>Observaciones</th>
            </tr>
          </thead>
          <tbody>
            {especificacion.ensayos.map((en) => (
              <tr key={en.id_ensayo}>
                <td className="num">{en.orden}</td>
                <td>{en.nombre_ensayo}</td>
                <td>{en.metodologia || '—'}</td>
                <td>{en.tipo_dato}</td>
                <td>
                  {en.tipo_dato === 'numerico'
                    ? `${en.limite_inferior ?? '—'} a ${en.limite_superior ?? '—'} ${en.unidad_medida || ''}`
                    : en.valor_requerido || '—'}
                </td>
                <td>{en.obligatorio ? 'Sí' : 'No'}</td>
                <td>{en.observaciones || '—'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
