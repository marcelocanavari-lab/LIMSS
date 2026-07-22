import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../../context/AuthContext';
import TopBar from '../../components/TopBar';
import { maestrosApi } from '../../api/maestros';
import { ApiError } from '../../api/client';

const BADGE_COMPACTO = { padding: '2px var(--sp-2)' };

function badgesEstado(t) {
  const badges = [];
  if (t.vencido) badges.push(<span key="v" className="badge badge-danger" style={BADGE_COMPACTO}>Vencido</span>);
  else if (t.por_vencer) badges.push(<span key="pv" className="badge badge-warn" style={BADGE_COMPACTO}>Por vencer</span>);
  if (t.stock_bajo) badges.push(<span key="sb" className="badge badge-warn" style={BADGE_COMPACTO}>Stock bajo</span>);
  if (!t.activo) badges.push(<span key="ia" className="badge badge-neutral" style={BADGE_COMPACTO}>Inactivo</span>);
  if (badges.length === 0) badges.push(<span key="ok" className="badge badge-ok" style={BADGE_COMPACTO}>Normal</span>);
  return badges;
}

function formatFecha(iso) {
  if (!iso) return '—';
  const [y, m, d] = iso.split('-');
  return `${d}/${m}/${y}`;
}

export default function TestigosPage() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const puedeGestionar = ['analista_qc', 'qa', 'admin'].includes(user?.rol);
  const puedeVerReporte = ['qa', 'admin'].includes(user?.rol);

  const [testigos, setTestigos] = useState([]);
  const [buscar, setBuscar] = useState('');
  const [soloAlertas, setSoloAlertas] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  async function verCertificado(e, idTestigo) {
    e.stopPropagation();
    try {
      const blob = await maestrosApi.descargarCertificado(idTestigo);
      const url = URL.createObjectURL(blob);
      window.open(url, '_blank');
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'No se pudo descargar el certificado');
    }
  }

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
          {puedeVerReporte && (
            <button className="btn btn-secondary" onClick={() => navigate('/maestros/testigos/reporte')}>
              Reporte
            </button>
          )}
          {puedeGestionar && (
            <button className="btn btn-secondary" onClick={() => navigate('/maestros/testigos/remitos')}>
              Remitos
            </button>
          )}
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
          <div className="table-scroll">
          <table className="data-table" style={{ tableLayout: 'fixed' }}>
            <colgroup>
              <col style={{ width: 90 }} />
              <col style={{ width: '25%' }} />
              <col style={{ width: '18%' }} />
              <col style={{ width: 90 }} />
              <col style={{ width: 100 }} />
              <col style={{ width: 90 }} />
              <col style={{ width: 110 }} />
              <col style={{ width: 110 }} />
            </colgroup>
            <thead>
              <tr>
                <th>Código</th>
                <th>Nombre</th>
                <th>Lote</th>
                <th>N° IR</th>
                <th>Vencimiento</th>
                <th>Stock</th>
                <th>Estado</th>
                <th>Certificado</th>
              </tr>
            </thead>
            <tbody>
              {testigos.map((t) => (
                <tr
                  key={t.id_testigo}
                  style={{ cursor: 'pointer' }}
                  onClick={() => navigate(`/maestros/testigos/${t.id_testigo}`)}
                >
                  <td style={{ fontFamily: 'var(--font-mono)', whiteSpace: 'nowrap' }}>{t.codigo}</td>
                  <td>{t.nombre}</td>
                  <td>{t.nro_lote}</td>
                  <td style={{ whiteSpace: 'nowrap' }}>{t.nro_ir || '—'}</td>
                  <td className="num" style={{ whiteSpace: 'nowrap' }}>{formatFecha(t.fecha_vencimiento)}</td>
                  <td className="num" style={{ whiteSpace: 'nowrap' }}>{t.stock_actual} {t.unidad_medida || ''}</td>
                  <td>
                    <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap' }}>{badgesEstado(t)}</div>
                  </td>
                  <td>
                    {t.pdf_certificado ? (
                      <button
                        type="button"
                        className="btn btn-ghost"
                        style={{ color: 'var(--ok)', padding: 0 }}
                        onClick={(e) => verCertificado(e, t.id_testigo)}
                      >
                        ✓ Ver
                      </button>
                    ) : (
                      <span style={{ color: 'var(--ink-2)' }}>Sin cert.</span>
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
