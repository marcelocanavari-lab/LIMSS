import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import TopBar from '../components/TopBar';
import { dashboardApi } from '../api/dashboard';
import { solicitudesMuestreoApi } from '../api/solicitudesMuestreo';
import { ApiError } from '../api/client';

const GESTION = ['analista_qc', 'qa', 'admin'];
const QA_ADMIN = ['qa', 'admin'];
const TODOS = ['muestreador', 'analista_qc', 'qa', 'admin'];

const QUICK_LINKS = [
  { label: 'Solicitudes de Muestreo', ruta: '/solicitudes-muestreo', roles: GESTION },
  { label: 'Mis Solicitudes', ruta: '/mis-solicitudes-muestreo', roles: ['muestreador'] },
  { label: 'Nueva Muestra', ruta: '/muestras/nueva', roles: TODOS },
  { label: 'Mis Muestras', ruta: '/muestras', roles: ['muestreador'] },
  { label: 'Consulta de Muestras', ruta: '/consulta-muestras', roles: GESTION },
  { label: 'Recorrido de Muestra', ruta: '/consulta-muestras', roles: GESTION },
  { label: 'Envío de Muestras', ruta: '/envios', roles: GESTION },
  { label: 'Carga de Resultados', ruta: '/carga-resultados', roles: GESTION },
  { label: 'Especificaciones', ruta: '/maestros/especificaciones', roles: GESTION },
  { label: 'Catálogo de Ensayos', ruta: '/maestros/ensayos', roles: GESTION },
  { label: 'Testigos y Estándares', ruta: '/maestros/testigos', roles: GESTION },
  { label: 'Laboratorios', ruta: '/muestras/laboratorios', roles: GESTION },
  { label: 'Reporte de Testigos', ruta: '/maestros/testigos/reporte', roles: QA_ADMIN },
  { label: 'Dictamen QA', ruta: '/dictamenes', roles: QA_ADMIN },
  { label: 'Facturación', ruta: '/facturas', roles: GESTION },
  { label: 'Administración', ruta: '/admin', roles: ['admin'] },
];

const ESTADOS_TESTIGO = [
  { value: 'vencido', label: 'Vencido' },
  { value: 'por_vencer', label: 'Por vencer' },
  { value: 'normal', label: 'Normal' },
  { value: 'sin_vencimiento', label: 'Sin vencimiento' },
  { value: 'stock_bajo', label: 'Stock bajo' },
];

const ORDENES_TESTIGO = [
  { value: 'vencimiento_asc', label: 'Vencimiento ASC' },
  { value: 'vencimiento_desc', label: 'Vencimiento DESC' },
  { value: 'nombre_asc', label: 'Nombre ASC' },
  { value: 'codigo_asc', label: 'Código ASC' },
];

function formatFecha(iso) {
  if (!iso) return '—';
  const [y, m, d] = iso.split('-');
  return `${d}/${m}/${y}`;
}

function hoyISO() {
  return new Date().toISOString().slice(0, 10);
}

function StatCard({ titulo, valor, icono, tono, grisEnCero, onClick }) {
  const clase = grisEnCero && valor === 0 ? 'stat-card' : `stat-card stat-card-${tono}`;
  return (
    <button type="button" className={clase} onClick={onClick}>
      <span className="stat-card-icon">{icono}</span>
      <div>
        <div className="stat-card-value">{valor}</div>
        <div className="stat-card-label">{titulo}</div>
      </div>
    </button>
  );
}

function VistaMuestreador({ links, navigate }) {
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
    <>
      <div className="dashboard-scroll">
        <h1 style={{ fontSize: 'var(--fs-lg)', marginBottom: 'var(--sp-3)' }}>Mis solicitudes pendientes de ejecutar</h1>

        {error && <div className="alert alert-danger" style={{ marginBottom: 'var(--sp-4)' }}>{error}</div>}

        {loading ? (
          <div className="state-block"><span className="spinner" /></div>
        ) : solicitudes.length === 0 ? (
          <div className="state-block">
            <span className="state-block-title">Sin solicitudes pendientes</span>
            <span>No tenés muestreos asignados por ejecutar</span>
          </div>
        ) : (
          <table className="data-table">
            <thead>
              <tr>
                <th>N° Solicitud</th>
                <th>Material</th>
                <th>IR</th>
                <th>Fecha</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {solicitudes.map((s) => (
                <tr key={s.id_solicitud}>
                  <td style={{ fontFamily: 'var(--font-mono)' }}>{s.nro_solicitud}</td>
                  <td>{s.erp_DESART} <span style={{ color: 'var(--ink-3)' }}>({s.erp_CODART.trim()})</span></td>
                  <td style={{ fontFamily: 'var(--font-mono)' }}>{s.erp_nro_ir}</td>
                  <td>{new Date(s.fecha_solicitud).toLocaleDateString()}</td>
                  <td>
                    <button
                      className="btn btn-primary"
                      onClick={() => navigate(`/solicitudes-muestreo/${s.id_solicitud}/orden-trabajo-digital`)}
                    >
                      Ejecutar
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      <div className="dashboard-quick-fijo">
        <div className="quick-grid">
          {links.map((l) => (
            <button key={l.ruta} type="button" className="quick-btn" onClick={() => navigate(l.ruta)}>
              <span className="quick-btn-label">{l.label}</span>
            </button>
          ))}
        </div>
      </div>
    </>
  );
}

function SeccionTestigosPorVencer({ navigate }) {
  const [estados, setEstados] = useState([]);
  const [orden, setOrden] = useState('vencimiento_asc');
  const [fechaRef, setFechaRef] = useState(hoyISO());
  const [diasAnticipacion, setDiasAnticipacion] = useState('30');
  const [testigos, setTestigos] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    setLoading(true);
    setError('');
    dashboardApi
      .obtenerTestigos({ estados, orden, limite: 100, fechaRef, diasAnticipacion: Number(diasAnticipacion) || 0 })
      .then(setTestigos)
      .catch((err) => {
        setTestigos([]);
        setError(err instanceof ApiError ? err.message : 'No se pudo cargar la lista de testigos');
      })
      .finally(() => setLoading(false));
  }, [estados, orden, fechaRef, diasAnticipacion]);

  function toggleEstado(value) {
    setEstados((prev) => (prev.includes(value) ? prev.filter((e) => e !== value) : [...prev, value]));
  }

  return (
    <div className="card" style={{ overflow: 'hidden' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 'var(--sp-3)' }}>
        <h2 style={{ fontSize: 'var(--fs-base)' }}>Testigos por vencer</h2>
        <button type="button" className="btn btn-ghost" style={{ padding: 0, minHeight: 'auto' }} onClick={() => navigate('/maestros/testigos')}>
          Ver todos →
        </button>
      </div>

      <div style={{ display: 'flex', alignItems: 'center', gap: 16, marginBottom: 'var(--sp-3)' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          <label className="field-label" style={{ fontSize: 'var(--fs-xs)', whiteSpace: 'nowrap' }}>Fecha ref.:</label>
          <input
            type="date"
            className="field-input"
            style={{ height: 32, fontSize: 'var(--fs-xs)' }}
            value={fechaRef}
            onChange={(e) => setFechaRef(e.target.value)}
          />
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          <label className="field-label" style={{ fontSize: 'var(--fs-xs)', whiteSpace: 'nowrap' }}>Días anticip.:</label>
          <input
            type="number"
            min="0"
            className="field-input"
            style={{ height: 32, width: 90, fontSize: 'var(--fs-xs)' }}
            value={diasAnticipacion}
            onChange={(e) => setDiasAnticipacion(e.target.value)}
          />
        </div>
      </div>

      <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap', alignItems: 'center', marginBottom: 'var(--sp-3)' }}>
        {ESTADOS_TESTIGO.map((e) => (
          <button
            key={e.value}
            type="button"
            className={estados.includes(e.value) ? 'btn btn-primary' : 'btn btn-secondary'}
            style={{ padding: '0 var(--sp-3)', minHeight: 32, fontSize: 'var(--fs-xs)' }}
            onClick={() => toggleEstado(e.value)}
          >
            {e.label}
          </button>
        ))}
        <div style={{ width: 1, height: 24, background: 'var(--border)', margin: '0 var(--sp-1)' }} />
        <select
          className="field-input"
          style={{ height: 32, width: 'auto', fontSize: 'var(--fs-xs)' }}
          value={orden}
          onChange={(e) => setOrden(e.target.value)}
        >
          {ORDENES_TESTIGO.map((o) => (
            <option key={o.value} value={o.value}>{o.label}</option>
          ))}
        </select>
      </div>

      {error && <div className="alert alert-danger" style={{ marginBottom: 'var(--sp-3)' }}>{error}</div>}

      {loading ? (
        <div className="state-block"><span className="spinner" /></div>
      ) : error ? null : testigos.length === 0 ? (
        <p style={{ color: 'var(--ink-2)', fontSize: 'var(--fs-sm)' }}>Sin testigos para estos filtros</p>
      ) : (
        <div className="dashboard-tabla-scroll" style={{ maxHeight: 280 }}>
          <table className="data-table">
            <thead>
              <tr>
                <th>Código</th>
                <th>Nombre</th>
                <th>Vencimiento</th>
                <th>Estado</th>
              </tr>
            </thead>
            <tbody>
              {testigos.map((t) => (
                <tr key={t.id_testigo} style={{ cursor: 'pointer' }} onClick={() => navigate(`/maestros/testigos/${t.id_testigo}`)}>
                  <td style={{ fontFamily: 'var(--font-mono)', whiteSpace: 'nowrap' }}>{t.codigo}</td>
                  <td>{t.nombre}</td>
                  <td className="num" style={{ whiteSpace: 'nowrap' }}>{formatFecha(t.fecha_vencimiento)}</td>
                  <td>
                    <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap' }}>
                      {t.vencido ? (
                        <span className="badge badge-danger">Vencido</span>
                      ) : t.por_vencer ? (
                        <span className="badge badge-warn">Por vencer</span>
                      ) : t.fecha_vencimiento ? (
                        <span className="badge badge-ok">Normal</span>
                      ) : (
                        <span className="badge badge-neutral">Sin vencimiento</span>
                      )}
                      {t.stock_bajo && <span className="badge badge-danger">Stock bajo</span>}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function SeccionSolicitudesSinEjecutar({ navigate }) {
  const [muestreadores, setMuestreadores] = useState([]);
  const [idMuestreador, setIdMuestreador] = useState(0);
  const [solicitudes, setSolicitudes] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    dashboardApi
      .obtenerMuestreadoresActivos()
      .then((data) => {
        setMuestreadores(data);
        if (data.length === 1) setIdMuestreador(data[0].id_usuario);
      })
      .catch(() => {});
  }, []);

  useEffect(() => {
    setLoading(true);
    setError('');
    dashboardApi
      .obtenerSolicitudesPendientes(idMuestreador)
      .then(setSolicitudes)
      .catch((err) => {
        setSolicitudes([]);
        setError(err instanceof ApiError ? err.message : 'No se pudo cargar la lista de solicitudes');
      })
      .finally(() => setLoading(false));
  }, [idMuestreador]);

  return (
    <div className="card">
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 'var(--sp-3)' }}>
        <h2 style={{ fontSize: 'var(--fs-base)' }}>Solicitudes sin ejecutar</h2>
        <button type="button" className="btn btn-ghost" style={{ padding: 0, minHeight: 'auto' }} onClick={() => navigate('/solicitudes-muestreo')}>
          Ver todas →
        </button>
      </div>

      <div className="field" style={{ flexDirection: 'row', alignItems: 'center', gap: 'var(--sp-2)', marginBottom: 'var(--sp-3)' }}>
        <label className="field-label" style={{ margin: 0 }}>Muestreador:</label>
        <select
          className="field-input"
          style={{ maxWidth: 220, height: 36 }}
          value={idMuestreador}
          onChange={(e) => setIdMuestreador(Number(e.target.value))}
        >
          <option value={0}>Todos</option>
          {muestreadores.map((m) => (
            <option key={m.id_usuario} value={m.id_usuario}>{m.nombre_completo}</option>
          ))}
        </select>
      </div>

      {error && <div className="alert alert-danger" style={{ marginBottom: 'var(--sp-3)' }}>{error}</div>}

      {loading ? (
        <div className="state-block"><span className="spinner" /></div>
      ) : error ? null : solicitudes.length === 0 ? (
        <p style={{ color: 'var(--ink-2)', fontSize: 'var(--fs-sm)' }}>Sin solicitudes pendientes</p>
      ) : (
        <div className="dashboard-tabla-scroll" style={{ maxHeight: 312 }}>
          <table className="data-table">
            <thead>
              <tr>
                <th>N° Solicitud</th>
                <th>Material</th>
                <th>Muestreador</th>
                <th>Hace</th>
              </tr>
            </thead>
            <tbody>
              {solicitudes.map((s) => (
                <tr key={s.id_solicitud} style={{ cursor: 'pointer' }} onClick={() => navigate('/solicitudes-muestreo')}>
                  <td style={{ fontFamily: 'var(--font-mono)', whiteSpace: 'nowrap' }}>{s.nro_solicitud}</td>
                  <td>{s.erp_DESART}</td>
                  <td>{s.muestreador_nombre || '—'}</td>
                  <td className="num" style={{ whiteSpace: 'nowrap' }}>{s.dias_pendiente} días</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

export default function DashboardPage() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const puedeVerDictamenes = QA_ADMIN.includes(user?.rol);
  const esMuestreador = user?.rol === 'muestreador';

  const [resumen, setResumen] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  function cargar() {
    if (esMuestreador) return;
    setLoading(true);
    setError('');
    dashboardApi
      .obtenerResumen()
      .then(setResumen)
      .catch((err) => setError(err instanceof ApiError ? err.message : 'No se pudo cargar el dashboard'))
      .finally(() => setLoading(false));
  }

  useEffect(cargar, [esMuestreador]);

  const links = QUICK_LINKS.filter((l) => l.roles.includes(user?.rol));

  return (
    <div className="screen">
      <TopBar titulo="LIMSS Laboratorio Lamar" subtitulo="Dashboard" />
      <div className="dashboard-content">
        {esMuestreador ? (
          <VistaMuestreador links={links} navigate={navigate} />
        ) : (
          <>
            <div className="dashboard-scroll">
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 'var(--sp-4)' }}>
                <div>
                  <h1 style={{ fontSize: 'var(--fs-lg)', marginBottom: 2 }}>Estado del sistema</h1>
                  <p style={{ color: 'var(--ink-2)', fontSize: 'var(--fs-sm)', margin: 0 }}>
                    Resumen de pendientes y alertas
                  </p>
                </div>
                <button type="button" className="btn btn-secondary" onClick={cargar} disabled={loading}>
                  {loading ? <span className="spinner" /> : 'Actualizar'}
                </button>
              </div>

              {error && <div className="alert alert-danger" style={{ marginBottom: 'var(--sp-4)' }}>{error}</div>}

              {loading && !resumen ? (
                <div className="state-block"><span className="spinner" /></div>
              ) : resumen && (
                <>
                  <div className="stat-grid" style={{ marginBottom: 'var(--sp-5)' }}>
                    <StatCard
                      titulo="Solicitudes pendientes"
                      valor={resumen.solicitudes_pendientes}
                      icono="▤"
                      tono="warn"
                      grisEnCero
                      onClick={() => navigate('/solicitudes-muestreo?estado=pendiente')}
                    />
                    <StatCard
                      titulo="Muestras en proceso"
                      valor={resumen.muestras_en_proceso}
                      icono="◆"
                      tono="info"
                      grisEnCero={false}
                      onClick={() => navigate('/consulta-muestras')}
                    />
                    <StatCard
                      titulo="Resultados pendientes"
                      valor={resumen.resultados_pendientes}
                      icono="☑"
                      tono="warn"
                      grisEnCero
                      onClick={() => navigate('/carga-resultados')}
                    />
                    {puedeVerDictamenes && (
                      <StatCard
                        titulo="Dictámenes pendientes"
                        valor={resumen.dictamenes_pendientes}
                        icono="⚖"
                        tono="danger"
                        grisEnCero
                        onClick={() => navigate('/dictamenes')}
                      />
                    )}
                  </div>

                  <div className="alerta-grid">
                    <SeccionTestigosPorVencer navigate={navigate} />
                    <SeccionSolicitudesSinEjecutar navigate={navigate} />
                  </div>
                </>
              )}
            </div>

            <div className="dashboard-quick-fijo">
              <div className="quick-grid">
                {links.map((l) => (
                  <button key={l.ruta} type="button" className="quick-btn" onClick={() => navigate(l.ruta)}>
                    <span className="quick-btn-label">{l.label}</span>
                  </button>
                ))}
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
