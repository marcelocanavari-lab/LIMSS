import { useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { useAuth } from '../../context/AuthContext';
import TopBar from '../../components/TopBar';
import { muestrasApi } from '../../api/muestras';
import { ApiError } from '../../api/client';
import { BADGE_POR_ESTADO } from './MuestrasPage';

export default function MuestraDetallePage() {
  const { id } = useParams();
  const navigate = useNavigate();
  const { user } = useAuth();
  const puedeGestionar = ['muestreador', 'qa', 'admin'].includes(user?.rol);

  const [muestra, setMuestra] = useState(null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    muestrasApi
      .obtenerMuestra(id)
      .then(setMuestra)
      .catch((err) => setError(err instanceof ApiError ? err.message : 'No se pudo cargar la muestra'))
      .finally(() => setLoading(false));
  }, [id]);

  if (loading) {
    return (
      <div className="screen" style={{ alignItems: 'center', justifyContent: 'center' }}>
        <span className="spinner" />
      </div>
    );
  }

  if (error || !muestra) {
    return (
      <div className="screen">
        <TopBar titulo="Muestra" subtitulo="Muestras" onBack={() => navigate('/muestras')} />
        <div className="screen-content">
          <div className="alert alert-danger">{error || 'No encontrada'}</div>
        </div>
      </div>
    );
  }

  const tieneEnvio = muestra.estado !== 'pendiente_envio';

  return (
    <div className="screen">
      <TopBar titulo={muestra.codigo_muestra} subtitulo="Muestras" onBack={() => navigate('/muestras')} />
      <div className="screen-content">
        <div className="card" style={{ marginBottom: 'var(--sp-5)' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 'var(--sp-3)' }}>
            <div>
              <div style={{ fontFamily: 'var(--font-mono)', color: 'var(--ink-2)', fontSize: 'var(--fs-sm)' }}>
                {muestra.tipo_referencia === 'ir' ? 'IR' : 'Lote'} {muestra.nro_referencia}
              </div>
              <h1 style={{ fontSize: 'var(--fs-xl)' }}>{muestra.erp_DESART}</h1>
            </div>
            <span className={`badge ${BADGE_POR_ESTADO[muestra.estado] || 'badge-neutral'}`}>{muestra.estado.replace(/_/g, ' ')}</span>
          </div>

          <table className="data-table">
            <tbody>
              <tr><td>Código</td><td style={{ textAlign: 'left', fontFamily: 'var(--font-mono)' }}>{muestra.erp_CODART}</td></tr>
              <tr><td>Cantidad de lote</td><td className="num" style={{ textAlign: 'left' }}>{muestra.erp_cantidad_lote ?? '—'}</td></tr>
              <tr><td>Proveedor</td><td style={{ textAlign: 'left' }}>{muestra.erp_proveedor || '—'}</td></tr>
              <tr><td>Especificación</td><td style={{ textAlign: 'left' }}>{muestra.id_especificacion ? `#${muestra.id_especificacion}` : 'Sin especificación vigente asignada'}</td></tr>
              <tr><td>Fecha de muestreo</td><td style={{ textAlign: 'left' }}>{new Date(muestra.fecha_muestreo).toLocaleString()}</td></tr>
              <tr><td>Observaciones</td><td style={{ textAlign: 'left' }}>{muestra.observaciones || '—'}</td></tr>
            </tbody>
          </table>

          <div style={{ display: 'flex', gap: 'var(--sp-3)', marginTop: 'var(--sp-4)', flexWrap: 'wrap' }}>
            <button className="btn btn-secondary" onClick={() => navigate(`/muestras/${id}/etiqueta`)}>
              Imprimir etiqueta
            </button>
            {!tieneEnvio && puedeGestionar && (
              <button className="btn btn-primary" onClick={() => navigate(`/muestras/${id}/envio`)}>
                Confirmar envío →
              </button>
            )}
            {tieneEnvio && (
              <button className="btn btn-secondary" onClick={() => navigate(`/muestras/${id}/remito`)}>
                Ver remito
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
