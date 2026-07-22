import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../../context/AuthContext';
import TopBar from '../../components/TopBar';
import { testigosRemitosApi } from '../../api/testigosRemitos';
import { ApiError } from '../../api/client';

export default function RemitosTestigosPage() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const autorizado = ['analista_qc', 'qa', 'admin'].includes(user?.rol);

  const [remitos, setRemitos] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    if (!autorizado) return;
    testigosRemitosApi
      .listarRemitos()
      .then(setRemitos)
      .catch((err) => setError(err instanceof ApiError ? err.message : 'No se pudo cargar el listado'))
      .finally(() => setLoading(false));
  }, [autorizado]);

  async function verPdf(id) {
    try {
      const blob = await testigosRemitosApi.descargarPdf(id);
      const url = URL.createObjectURL(blob);
      window.open(url, '_blank');
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'No se pudo descargar el PDF');
    }
  }

  if (!autorizado) {
    return (
      <div className="screen">
        <TopBar titulo="Remitos de Testigos" subtitulo="Datos Maestros" onBack={() => navigate('/maestros/testigos')} />
        <div className="screen-content">
          <div className="state-block">
            <span className="state-block-title">Acceso restringido</span>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="screen">
      <TopBar titulo="Remitos de Testigos" subtitulo="Datos Maestros" onBack={() => navigate('/maestros/testigos')} />
      <div className="screen-content">
        <button className="btn btn-primary" style={{ marginBottom: 'var(--sp-4)' }} onClick={() => navigate('/maestros/testigos/remitos/nuevo')}>
          + Nuevo remito
        </button>

        {error && <div className="alert alert-danger" style={{ marginBottom: 'var(--sp-4)' }}>{error}</div>}

        {loading ? (
          <div className="state-block"><span className="spinner" /></div>
        ) : remitos.length === 0 ? (
          <div className="state-block">
            <span className="state-block-title">Sin remitos</span>
            <span>Todavía no se generó ningún remito de testigos</span>
          </div>
        ) : (
          <div className="table-scroll">
            <table className="data-table">
              <thead>
                <tr>
                  <th>N° Remito</th>
                  <th>Laboratorio</th>
                  <th>Fecha</th>
                  <th>Cant. Testigos</th>
                  <th>Recepción</th>
                  <th>PDF</th>
                </tr>
              </thead>
              <tbody>
                {remitos.map((r) => (
                  <tr key={r.id_remito} style={{ cursor: 'pointer' }} onClick={() => navigate(`/maestros/testigos/remitos/${r.id_remito}`)}>
                    <td style={{ fontFamily: 'var(--font-mono)' }}>{r.nro_remito}</td>
                    <td>{r.laboratorio_nombre}</td>
                    <td>{new Date(r.fecha_envio).toLocaleDateString()}</td>
                    <td className="num">{r.cantidad_testigos}</td>
                    <td>
                      {r.tiene_copia_firmada ? (
                        <span className="badge badge-ok">✓ {new Date(r.fecha_recepcion).toLocaleDateString()}</span>
                      ) : (
                        <span className="badge badge-neutral">Pendiente</span>
                      )}
                    </td>
                    <td>
                      <button type="button" className="btn btn-ghost" onClick={(e) => { e.stopPropagation(); verPdf(r.id_remito); }}>
                        Ver PDF
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
