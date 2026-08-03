import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../../context/AuthContext';
import TopBar from '../../components/TopBar';
import { maestrosApi } from '../../api/maestros';
import { ApiError, abrirPdfConAuth } from '../../api/client';

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
  const puedeEliminar = ['qa', 'admin'].includes(user?.rol);

  const [testigos, setTestigos] = useState([]);
  const [buscar, setBuscar] = useState('');
  const [soloAlertas, setSoloAlertas] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const [testigoAEliminar, setTestigoAEliminar] = useState(null);
  const [eliminando, setEliminando] = useState(false);
  const [errorEliminar, setErrorEliminar] = useState('');
  const [ofrecerDesactivar, setOfrecerDesactivar] = useState(false);

  function pedirEliminar(e, testigo) {
    e.stopPropagation();
    setTestigoAEliminar(testigo);
    setErrorEliminar('');
    setOfrecerDesactivar(false);
  }

  function cerrarModalEliminar() {
    setTestigoAEliminar(null);
    setErrorEliminar('');
    setOfrecerDesactivar(false);
  }

  async function confirmarEliminar() {
    if (!testigoAEliminar) return;
    setEliminando(true);
    setErrorEliminar('');
    try {
      await maestrosApi.eliminarTestigo(testigoAEliminar.id_testigo);
      cerrarModalEliminar();
      setTestigos((prev) => prev.filter((t) => t.id_testigo !== testigoAEliminar.id_testigo));
    } catch (err) {
      if (err instanceof ApiError && err.status === 400) {
        setErrorEliminar(err.message);
        setOfrecerDesactivar(true);
      } else {
        setErrorEliminar(err instanceof ApiError ? err.message : 'No se pudo eliminar el testigo');
      }
    } finally {
      setEliminando(false);
    }
  }

  async function desactivarEnLugarDeEliminar() {
    if (!testigoAEliminar) return;
    setEliminando(true);
    try {
      await maestrosApi.cambiarEstadoTestigo(testigoAEliminar.id_testigo, false);
      cerrarModalEliminar();
      setTestigos((prev) =>
        prev.map((t) => (t.id_testigo === testigoAEliminar.id_testigo ? { ...t, activo: false } : t))
      );
    } catch (err) {
      setErrorEliminar(err instanceof ApiError ? err.message : 'No se pudo desactivar el testigo');
    } finally {
      setEliminando(false);
    }
  }

  async function verCertificado(e, idTestigo) {
    e.stopPropagation();
    try {
      await abrirPdfConAuth(`/api/maestros/testigos/${idTestigo}/certificado`);
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
      <TopBar titulo="Testigos y Estándares" subtitulo="Datos Maestros" onBack={() => navigate(-1)} />
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
              <col style={{ width: '20%' }} />
              <col style={{ width: '14%' }} />
              <col style={{ width: 90 }} />
              <col style={{ width: 100 }} />
              <col style={{ width: 90 }} />
              <col style={{ width: '14%' }} />
              <col style={{ width: 110 }} />
              <col style={{ width: 110 }} />
              {puedeEliminar && <col style={{ width: 100 }} />}
            </colgroup>
            <thead>
              <tr>
                <th>Código</th>
                <th>Nombre</th>
                <th>Lote</th>
                <th>N° IR</th>
                <th>Vencimiento</th>
                <th>Stock</th>
                <th>Laboratorio</th>
                <th>Estado</th>
                <th>Certificado</th>
                {puedeEliminar && <th></th>}
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
                  <td>{t.laboratorio_nombre || <span style={{ color: 'var(--ink-2)' }}>Sin asignar</span>}</td>
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
                  {puedeEliminar && (
                    <td>
                      <button
                        type="button"
                        className="btn btn-ghost"
                        style={{ color: 'var(--danger)', padding: 0 }}
                        onClick={(e) => pedirEliminar(e, t)}
                      >
                        Eliminar
                      </button>
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
          </div>
        )}
      </div>

      {testigoAEliminar && (
        <div
          style={{
            position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.5)',
            display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 100, padding: 'var(--sp-4)',
          }}
          onClick={cerrarModalEliminar}
        >
          <div className="card" style={{ width: '90%', maxWidth: 420 }} onClick={(e) => e.stopPropagation()}>
            <h2 style={{ fontSize: 'var(--fs-lg)', marginBottom: 'var(--sp-3)' }}>Eliminar testigo</h2>
            <p>
              ¿Confirmar eliminación del testigo{' '}
              <strong>{testigoAEliminar.codigo} - {testigoAEliminar.nombre}</strong>? Esta acción no se puede deshacer.
            </p>

            {errorEliminar && (
              <div className="alert alert-danger" style={{ marginTop: 'var(--sp-3)' }}>
                {errorEliminar}
                {ofrecerDesactivar && (
                  <div style={{ marginTop: 'var(--sp-2)' }}>
                    <button
                      type="button"
                      className="btn btn-secondary"
                      onClick={desactivarEnLugarDeEliminar}
                      disabled={eliminando}
                    >
                      {eliminando ? <span className="spinner" /> : 'Desactivar en su lugar'}
                    </button>
                  </div>
                )}
              </div>
            )}

            <div style={{ display: 'flex', gap: 'var(--sp-3)', marginTop: 'var(--sp-4)' }}>
              <button type="button" className="btn btn-ghost" onClick={cerrarModalEliminar} disabled={eliminando}>
                Cancelar
              </button>
              <button type="button" className="btn btn-primary" onClick={confirmarEliminar} disabled={eliminando}>
                {eliminando ? <span className="spinner" /> : 'Confirmar eliminación'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
