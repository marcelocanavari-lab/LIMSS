import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import TopBar from '../components/TopBar';
import { solicitudesMuestreoApi } from '../api/solicitudesMuestreo';
import { ApiError, abrirPdfConAuth } from '../api/client';

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

  async function verProtocoloProveedor(s) {
    try {
      await abrirPdfConAuth(`/api/solicitudes-muestreo/${s.id_solicitud}/protocolo-proveedor`);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'No se pudo abrir el protocolo del proveedor');
    }
  }

  async function verDocumentacionProveedor(s) {
    try {
      await abrirPdfConAuth(`/api/solicitudes-muestreo/${s.id_solicitud}/documentacion-proveedor`);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'No se pudo abrir la documentación del proveedor');
    }
  }

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
                  <th></th>
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
                      {s.id_muestra && (
                        <span
                          className="badge badge-info"
                          title="El envío ya se generó por adelantado -- completá el muestreo físico para cerrar el registro"
                        >
                          Envío ya generado
                        </span>
                      )}
                    </td>
                    <td style={{ display: 'flex', gap: 'var(--sp-2)', flexWrap: 'wrap' }}>
                      {s.protocolo_proveedor_nombre_original && (
                        <button className="btn btn-ghost" onClick={() => verProtocoloProveedor(s)}>Protocolo proveedor</button>
                      )}
                      {s.documentacion_proveedor_nombre_original && (
                        <button className="btn btn-ghost" onClick={() => verDocumentacionProveedor(s)}>Documentación proveedor</button>
                      )}
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
