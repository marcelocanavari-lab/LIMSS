import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import TopBar from '../../components/TopBar';
import { resultadosApi } from '../../api/resultados';
import { ApiError } from '../../api/client';

// Esta bandeja solo lista envíos con AL MENOS UN ensayo pendiente (ver
// WHERE en listar_pendientes_resultados) -- "Completo" nunca aparece acá,
// solo distingue si ya se cargó algo (Parcial) o nada todavía (Sin cargar).
function badgeEstadoCarga(ensayosPendientes, totalEnsayos) {
  if (ensayosPendientes === totalEnsayos) return { texto: 'Sin cargar', clase: 'badge-neutral' };
  return { texto: 'Parcial', clase: 'badge-warn' };
}

export default function CargaResultadosBandejaPage() {
  const navigate = useNavigate();

  const [envios, setEnvios] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    resultadosApi
      .listarPendientes()
      .then(setEnvios)
      .catch((err) => setError(err instanceof ApiError ? err.message : 'No se pudo cargar el listado'))
      .finally(() => setLoading(false));
  }, []);

  return (
    <div className="screen">
      <TopBar titulo="Carga de Resultados" subtitulo="Envíos con ensayos pendientes de resultado" onBack={() => navigate(-1)} />
      <div className="screen-content">
        {error && <div className="alert alert-danger" style={{ marginBottom: 'var(--sp-4)' }}>{error}</div>}

        {loading ? (
          <div className="state-block"><span className="spinner" /></div>
        ) : envios.length === 0 ? (
          <div className="state-block">
            <span className="state-block-title">Sin pendientes</span>
            <span>No hay envíos con ensayos pendientes de resultado</span>
          </div>
        ) : (
          <div className="table-scroll">
            <table className="data-table">
              <thead>
                <tr>
                  <th>N° Remito</th>
                  <th>Muestra</th>
                  <th>Material</th>
                  <th>Laboratorio</th>
                  <th>Estado</th>
                  <th>Ensayos pendientes</th>
                  <th>Fecha envío</th>
                </tr>
              </thead>
              <tbody>
                {envios.map((e) => {
                  const badge = badgeEstadoCarga(e.ensayos_pendientes, e.total_ensayos);
                  return (
                    <tr key={e.id_envio} style={{ cursor: 'pointer' }} onClick={() => navigate(`/envios/${e.id_envio}/resultados`)}>
                      <td style={{ fontFamily: 'var(--font-mono)' }}>{e.nro_remito_interno || '—'}</td>
                      <td style={{ fontFamily: 'var(--font-mono)' }}>{e.codigo_muestra}</td>
                      <td>{e.erp_DESART}</td>
                      <td>{e.laboratorio_nombre}</td>
                      <td><span className={`badge ${badge.clase}`}>{badge.texto}</span></td>
                      <td><span className="badge badge-warn">{e.ensayos_pendientes} de {e.total_ensayos}</span></td>
                      <td>{new Date(e.fecha_despacho).toLocaleDateString()}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
