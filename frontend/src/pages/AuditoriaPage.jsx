import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import TopBar from '../components/TopBar';
import { auditoriaApi } from '../api/auditoria';
import { ApiError } from '../api/client';

const POR_PAGINA = 100;

function formatFechaHora(iso) {
  const d = new Date(iso);
  const pad = (n) => String(n).padStart(2, '0');
  return `${pad(d.getDate())}/${pad(d.getMonth() + 1)}/${d.getFullYear()} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

export default function AuditoriaPage() {
  const navigate = useNavigate();

  const [usuarios, setUsuarios] = useState([]);
  const [fechaDesde, setFechaDesde] = useState('');
  const [fechaHasta, setFechaHasta] = useState('');
  const [idUsuario, setIdUsuario] = useState('');
  const [accion, setAccion] = useState('');

  const [filtrosAplicados, setFiltrosAplicados] = useState({});
  const [pagina, setPagina] = useState(0);

  const [registros, setRegistros] = useState([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    auditoriaApi.listarUsuarios().then(setUsuarios).catch(() => {});
  }, []);

  useEffect(() => {
    let activo = true;
    setLoading(true);
    setError('');
    auditoriaApi
      .listar({ ...filtrosAplicados, limite: POR_PAGINA, offset: pagina * POR_PAGINA })
      .then((data) => {
        if (!activo) return;
        setRegistros(data.registros);
        setTotal(data.total);
      })
      .catch((err) => activo && setError(err instanceof ApiError ? err.message : 'No se pudo cargar la auditoría'))
      .finally(() => activo && setLoading(false));
    return () => {
      activo = false;
    };
  }, [filtrosAplicados, pagina]);

  function aplicarFiltros() {
    setPagina(0);
    setFiltrosAplicados({
      fechaDesde: fechaDesde || undefined,
      fechaHasta: fechaHasta || undefined,
      idUsuario: idUsuario || undefined,
      accion: accion || undefined,
    });
  }

  function limpiarFiltros() {
    setFechaDesde('');
    setFechaHasta('');
    setIdUsuario('');
    setAccion('');
    setPagina(0);
    setFiltrosAplicados({});
  }

  const totalPaginas = Math.max(1, Math.ceil(total / POR_PAGINA));

  return (
    <div className="screen">
      <TopBar titulo="Auditoría" subtitulo="Administración" onBack={() => navigate(-1)} />
      <div className="screen-content">
        <div style={{ display: 'flex', gap: 'var(--sp-3)', marginBottom: 'var(--sp-4)', flexWrap: 'wrap', alignItems: 'center' }}>
          <input
            className="field-input"
            type="date"
            style={{ maxWidth: 160 }}
            value={fechaDesde}
            onChange={(e) => setFechaDesde(e.target.value)}
            title="Fecha desde"
          />
          <input
            className="field-input"
            type="date"
            style={{ maxWidth: 160 }}
            value={fechaHasta}
            onChange={(e) => setFechaHasta(e.target.value)}
            title="Fecha hasta"
          />
          <select className="field-input" style={{ maxWidth: 220 }} value={idUsuario} onChange={(e) => setIdUsuario(e.target.value)}>
            <option value="">Todos los usuarios</option>
            {usuarios.map((u) => (
              <option key={u.id_usuario} value={u.id_usuario}>{u.nombre_completo}</option>
            ))}
          </select>
          <input
            className="field-input"
            style={{ flex: 1, minWidth: 180 }}
            placeholder="Buscar por acción..."
            value={accion}
            onChange={(e) => setAccion(e.target.value)}
          />
          <button className="btn btn-primary" onClick={aplicarFiltros}>Filtrar</button>
          <button className="btn btn-ghost" onClick={limpiarFiltros}>Limpiar filtros</button>
        </div>

        {error && <div className="alert alert-danger" style={{ marginBottom: 'var(--sp-4)' }}>{error}</div>}

        {loading ? (
          <div className="state-block"><span className="spinner" /></div>
        ) : registros.length === 0 ? (
          <div className="state-block">
            <span className="state-block-title">Sin resultados</span>
            <span>No se encontraron registros para los filtros aplicados</span>
          </div>
        ) : (
          <>
            <div className="table-scroll">
              <table className="data-table data-table-compact">
                <thead>
                  <tr>
                    <th>Fecha y hora</th>
                    <th>Usuario</th>
                    <th>Acción</th>
                    <th>Detalle</th>
                    <th>Valor anterior</th>
                    <th>Valor nuevo</th>
                  </tr>
                </thead>
                <tbody>
                  {registros.map((r) => (
                    <tr key={r.id_audit}>
                      <td style={{ whiteSpace: 'nowrap', fontFamily: 'var(--font-mono)' }}>{formatFechaHora(r.fecha_hora)}</td>
                      <td>{r.usuario_nombre || '—'}</td>
                      <td>{r.accion}</td>
                      <td>{r.detalle}</td>
                      <td style={{ color: 'var(--ink-3)', textDecoration: r.valor_anterior ? 'line-through' : 'none' }}>
                        {r.valor_anterior || '—'}
                      </td>
                      <td style={{ color: 'var(--accent)' }}>{r.valor_nuevo || '—'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', gap: 'var(--sp-3)', marginTop: 'var(--sp-4)' }}>
              <button
                className="btn btn-ghost"
                disabled={pagina === 0}
                onClick={() => setPagina((p) => Math.max(0, p - 1))}
              >
                Anterior
              </button>
              <span style={{ color: 'var(--ink-2)', fontSize: 'var(--fs-sm)' }}>
                Página {pagina + 1} de {totalPaginas}
              </span>
              <button
                className="btn btn-ghost"
                disabled={pagina + 1 >= totalPaginas}
                onClick={() => setPagina((p) => p + 1)}
              >
                Siguiente
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
