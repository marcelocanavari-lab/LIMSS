import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import TopBar from '../components/TopBar';
import { solicitudesMuestreoApi } from '../api/solicitudesMuestreo';
import { ApiError } from '../api/client';

function formatFecha(iso) {
  return new Date(iso).toLocaleDateString();
}

export default function MisSolicitudesPage() {
  const navigate = useNavigate();
  const [solicitudes, setSolicitudes] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    solicitudesMuestreoApi
      .misSolicitudes()
      .then(setSolicitudes)
      .catch((err) => setError(err instanceof ApiError ? err.message : 'No se pudo cargar el listado'))
      .finally(() => setLoading(false));
  }, []);

  return (
    <div className="screen">
      <TopBar titulo="Mis Solicitudes" subtitulo="Muestreo pendiente de ejecutar" onBack={() => navigate(-1)} />
      <div className="screen-content">
        {error && <div className="alert alert-danger" style={{ marginBottom: 'var(--sp-4)' }}>{error}</div>}

        {loading ? (
          <div className="state-block"><span className="spinner" /></div>
        ) : solicitudes.length === 0 ? (
          <div className="state-block">
            <span className="state-block-title">Sin solicitudes pendientes</span>
            <span>No tenés muestreos asignados por ejecutar</span>
          </div>
        ) : (
          <div className="table-scroll">
            <table className="data-table data-table-compact">
              <thead>
                <tr>
                  <th>N° Solicitud</th>
                  <th>IR</th>
                  <th>Material</th>
                  <th>Fecha</th>
                  <th>Acciones</th>
                </tr>
              </thead>
              <tbody>
                {solicitudes.map((s) => (
                  <tr key={s.id_solicitud}>
                    <td style={{ fontFamily: 'var(--font-mono)' }}>{s.nro_solicitud}</td>
                    <td style={{ fontFamily: 'var(--font-mono)' }}>{s.erp_nro_ir}</td>
                    <td>{s.erp_DESART} <span style={{ color: 'var(--ink-3)' }}>({s.erp_CODART.trim()})</span></td>
                    <td>{formatFecha(s.fecha_solicitud)}</td>
                    <td>
                      <button
                        className="btn btn-primary"
                        onClick={() => navigate(`/solicitudes-muestreo/${s.id_solicitud}/orden-trabajo-digital`)}
                      >
                        Ejecutar muestreo
                      </button>
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
