import { useEffect, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { useAuth } from '../../context/AuthContext';
import TopBar from '../../components/TopBar';
import { muestrasApi } from '../../api/muestras';
import { ApiError } from '../../api/client';

const ESTADOS_PENDIENTES = ['en_transito', 'en_carga_resultados', 'pendiente_dictamen'];

const ESTADOS = [
  { value: '', label: 'Todos los estados' },
  { value: 'pendiente_envio', label: 'Pendiente de envío' },
  { value: 'en_transito', label: 'En tránsito' },
  { value: 'en_carga_resultados', label: 'En carga de resultados' },
  { value: 'pendiente_dictamen', label: 'Pendiente de dictamen' },
  { value: 'aprobado', label: 'Aprobado' },
  { value: 'rechazado', label: 'Rechazado' },
  { value: 'cuarentena', label: 'Cuarentena' },
];

const BADGE_POR_ESTADO = {
  pendiente_envio: 'badge-neutral',
  en_transito: 'badge-info',
  en_carga_resultados: 'badge-info',
  pendiente_dictamen: 'badge-warn',
  aprobado: 'badge-ok',
  rechazado: 'badge-danger',
  cuarentena: 'badge-warn',
};

export default function MuestrasPage() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const vistaPendientes = searchParams.get('vista') === 'pendientes';
  const puedeCrear = ['muestreador', 'analista_qc', 'qa', 'admin'].includes(user?.rol);

  const [muestras, setMuestras] = useState([]);
  const [estado, setEstado] = useState('');
  const [buscar, setBuscar] = useState('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    let activo = true;
    setLoading(true);
    setError('');
    muestrasApi
      .listarMuestras({ estado, buscar })
      .then((data) => activo && setMuestras(data))
      .catch((err) => activo && setError(err instanceof ApiError ? err.message : 'No se pudo cargar el listado'))
      .finally(() => activo && setLoading(false));
    return () => {
      activo = false;
    };
  }, [estado, buscar]);

  const muestrasVisibles = vistaPendientes
    ? muestras.filter((m) => ESTADOS_PENDIENTES.includes(m.estado))
    : muestras;

  return (
    <div className="screen">
      <TopBar
        titulo={vistaPendientes ? 'Muestras pendientes' : 'Muestras'}
        subtitulo={vistaPendientes ? 'Envío, resultados y dictamen' : 'Muestreo y envío a laboratorio'}
        onBack={() => navigate('/menu')}
      />
      <div className="screen-content">
        <div style={{ display: 'flex', gap: 'var(--sp-3)', marginBottom: 'var(--sp-4)', flexWrap: 'wrap' }}>
          <input
            className="field-input"
            style={{ flex: 1, minWidth: 200 }}
            placeholder="Buscar por código, IR o material..."
            value={buscar}
            onChange={(e) => setBuscar(e.target.value)}
          />
          <select className="field-input" style={{ maxWidth: 240 }} value={estado} onChange={(e) => setEstado(e.target.value)}>
            {ESTADOS.map((e) => (
              <option key={e.value} value={e.value}>{e.label}</option>
            ))}
          </select>
          {puedeCrear && (
            <button className="btn btn-primary" onClick={() => navigate('/muestras/nueva')}>
              + Nueva muestra
            </button>
          )}
        </div>

        {error && <div className="alert alert-danger" style={{ marginBottom: 'var(--sp-4)' }}>{error}</div>}

        {loading ? (
          <div className="state-block"><span className="spinner" /></div>
        ) : muestrasVisibles.length === 0 ? (
          <div className="state-block">
            <span className="state-block-title">Sin muestras</span>
            <span>No hay muestras cargadas con estos filtros</span>
          </div>
        ) : (
          <div className="table-scroll">
          <table className="data-table">
            <thead>
              <tr>
                <th>Código</th>
                <th>IR / Lote</th>
                <th>Material</th>
                <th>Fecha muestreo</th>
                <th>Estado</th>
              </tr>
            </thead>
            <tbody>
              {muestrasVisibles.map((m) => (
                <tr key={m.id_muestra} style={{ cursor: 'pointer' }} onClick={() => navigate(`/muestras/${m.id_muestra}`)}>
                  <td style={{ fontFamily: 'var(--font-mono)' }}>{m.codigo_muestra}</td>
                  <td style={{ fontFamily: 'var(--font-mono)' }}>
                    <span className="badge badge-neutral" style={{ marginRight: 6 }}>{m.tipo_referencia === 'ir' ? 'IR' : 'Lote'}</span>
                    {m.nro_referencia}
                  </td>
                  <td>{m.erp_DESART}</td>
                  <td>{new Date(m.fecha_muestreo).toLocaleDateString()}</td>
                  <td><span className={`badge ${BADGE_POR_ESTADO[m.estado] || 'badge-neutral'}`}>{m.estado.replace(/_/g, ' ')}</span></td>
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

export { BADGE_POR_ESTADO };
