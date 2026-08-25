import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../../context/AuthContext';
import TopBar from '../../components/TopBar';
import { muestrasApi } from '../../api/muestras';
import { ApiError } from '../../api/client';

const ESTADOS = [
  { value: '', label: 'Todos los estados' },
  { value: 'pendiente_envio', label: 'Pendiente de envío' },
  { value: 'en_análisis', label: 'En análisis' },
  { value: 'aprobado_sin_dictamen', label: 'Aprobado sin Dictamen' },
  { value: 'aprobado', label: 'Aprobado' },
  { value: 'rechazado', label: 'Rechazado' },
  { value: 'cuarentena', label: 'Cuarentena' },
];

const BADGE_POR_ESTADO = {
  pendiente_envio: 'badge-neutral',
  en_análisis: 'badge-info',
  // Mismo verde que 'aprobado' (ya puede salir de cuarentena), pero es un
  // estado distinto -- se distingue por el texto ("aprobado sin dictamen"
  // vs "aprobado"), no por el color, ya que el color acá comunica
  // "resultado favorable", que en ambos casos es cierto.
  aprobado_sin_dictamen: 'badge-ok',
  aprobado: 'badge-ok',
  rechazado: 'badge-danger',
  cuarentena: 'badge-warn',
};

export default function MuestrasPage() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const puedeCrear = ['muestreador', 'analista_qc', 'qa', 'admin'].includes(user?.rol);

  const [muestras, setMuestras] = useState([]);
  const [buscar, setBuscar] = useState('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    let activo = true;
    setLoading(true);
    setError('');
    muestrasApi
      .listarMuestras({ mio: true, buscar })
      .then((data) => activo && setMuestras(data))
      .catch((err) => activo && setError(err instanceof ApiError ? err.message : 'No se pudo cargar el listado'))
      .finally(() => activo && setLoading(false));
    return () => {
      activo = false;
    };
  }, [buscar]);

  return (
    <div className="screen">
      <TopBar titulo="Muestras" subtitulo="Muestreo y generación de etiquetas" onBack={() => navigate(-1)} />
      <div className="screen-content">
        <div style={{ display: 'flex', gap: 'var(--sp-3)', marginBottom: 'var(--sp-4)', flexWrap: 'wrap' }}>
          <input
            className="field-input"
            style={{ flex: 1, minWidth: 200 }}
            placeholder="Buscar por código, IR o material..."
            value={buscar}
            onChange={(e) => setBuscar(e.target.value)}
          />
          {puedeCrear && (
            <button className="btn btn-primary btn-lg" onClick={() => navigate('/muestras/nueva')}>
              + Nueva muestra
            </button>
          )}
        </div>

        {error && <div className="alert alert-danger" style={{ marginBottom: 'var(--sp-4)' }}>{error}</div>}

        {loading ? (
          <div className="state-block"><span className="spinner" /></div>
        ) : muestras.length === 0 ? (
          <div className="state-block">
            <span className="state-block-title">Sin muestras</span>
            <span>Todavía no registraste ninguna muestra</span>
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
                <th>Muestreador</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {muestras.map((m) => (
                <tr key={m.id_muestra} style={{ cursor: 'pointer' }} onClick={() => navigate(`/muestras/${m.id_muestra}`)}>
                  <td style={{ fontFamily: 'var(--font-mono)' }}>{m.codigo_muestra}</td>
                  <td style={{ fontFamily: 'var(--font-mono)' }}>
                    <span className="badge badge-neutral" style={{ marginRight: 6 }}>{m.tipo_referencia === 'ir' ? 'IR' : 'Lote'}</span>
                    {m.nro_referencia}
                  </td>
                  <td>{m.erp_DESART}</td>
                  <td>{new Date(m.fecha_muestreo).toLocaleDateString()}</td>
                  <td>{m.usuario_muestreo_nombre}</td>
                  <td>
                    {m.datos_muestreo_pendientes && (
                      <span className="badge badge-warn" title="El envío se generó por adelantado -- todavía falta completar el registro físico del muestreo">
                        Datos pendientes
                      </span>
                    )}
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

export { BADGE_POR_ESTADO, ESTADOS };
