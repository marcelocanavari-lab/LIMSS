import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../../context/AuthContext';
import TopBar from '../../components/TopBar';
import { facturasApi } from '../../api/facturas';
import { muestrasApi } from '../../api/muestras';
import { ApiError } from '../../api/client';

const ESTADOS_PAGO = [
  { value: '', label: 'Todos' },
  { value: 'pendiente', label: 'Pendiente' },
  { value: 'pagado', label: 'Pagado' },
  { value: 'anulado', label: 'Anulado' },
];

const BADGE_ESTADO = {
  pendiente: 'badge-warn',
  pagado: 'badge-ok',
  anulado: 'badge-danger',
};

function labelEstado(estado) {
  return ESTADOS_PAGO.find((e) => e.value === estado)?.label || estado;
}

function formatMonto(monto, moneda) {
  return `${moneda} ${Number(monto).toLocaleString('es-AR', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

export default function FacturasPage() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const autorizado = ['analista_qc', 'qa', 'admin'].includes(user?.rol);

  const [facturas, setFacturas] = useState([]);
  const [laboratorios, setLaboratorios] = useState([]);
  const [idLaboratorio, setIdLaboratorio] = useState('');
  const [estadoPago, setEstadoPago] = useState('');
  const [fechaDesde, setFechaDesde] = useState('');
  const [fechaHasta, setFechaHasta] = useState('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    if (!autorizado) return;
    muestrasApi.listarLaboratorios(true).then(setLaboratorios).catch(() => {});
  }, [autorizado]);

  useEffect(() => {
    if (!autorizado) return;
    let activo = true;
    setLoading(true);
    setError('');
    facturasApi
      .listarFacturas({
        idLaboratorio: idLaboratorio || undefined,
        estadoPago: estadoPago || undefined,
        fechaDesde: fechaDesde || undefined,
        fechaHasta: fechaHasta || undefined,
      })
      .then((data) => activo && setFacturas(data))
      .catch((err) => activo && setError(err instanceof ApiError ? err.message : 'No se pudo cargar el listado'))
      .finally(() => activo && setLoading(false));
    return () => {
      activo = false;
    };
  }, [autorizado, idLaboratorio, estadoPago, fechaDesde, fechaHasta]);

  if (!autorizado) {
    return (
      <div className="screen">
        <TopBar titulo="Facturación" subtitulo="Laboratorios" onBack={() => navigate(-1)} />
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
      <TopBar titulo="Facturación de Laboratorios" subtitulo="Laboratorios" onBack={() => navigate(-1)} />
      <div className="screen-content">
        <div style={{ display: 'flex', gap: 'var(--sp-3)', marginBottom: 'var(--sp-4)' }}>
          <button className="btn btn-primary" onClick={() => navigate('/facturas/nueva')}>
            + Nueva factura
          </button>
          <button className="btn btn-secondary" onClick={() => navigate('/facturas/reporte-importes')}>
            Reporte de importes
          </button>
        </div>

        <div style={{ display: 'flex', gap: 'var(--sp-3)', flexWrap: 'wrap', marginBottom: 'var(--sp-4)' }}>
          <div className="field" style={{ flex: 1, minWidth: 180, marginBottom: 0 }}>
            <label className="field-label" htmlFor="idLaboratorio">Laboratorio</label>
            <select id="idLaboratorio" className="field-input" value={idLaboratorio} onChange={(e) => setIdLaboratorio(e.target.value)}>
              <option value="">Todos los laboratorios</option>
              {laboratorios.map((l) => (
                <option key={l.id_laboratorio} value={l.id_laboratorio}>{l.nombre}</option>
              ))}
            </select>
          </div>
          <div className="field" style={{ flex: 1, minWidth: 150, marginBottom: 0 }}>
            <label className="field-label" htmlFor="estadoPago">Estado de pago</label>
            <select id="estadoPago" className="field-input" value={estadoPago} onChange={(e) => setEstadoPago(e.target.value)}>
              {ESTADOS_PAGO.map((e) => (
                <option key={e.value} value={e.value}>{e.label}</option>
              ))}
            </select>
          </div>
          <div className="field" style={{ flex: 1, minWidth: 150, marginBottom: 0 }}>
            <label className="field-label" htmlFor="fechaDesde">Desde</label>
            <input id="fechaDesde" className="field-input" type="date" value={fechaDesde} onChange={(e) => setFechaDesde(e.target.value)} />
          </div>
          <div className="field" style={{ flex: 1, minWidth: 150, marginBottom: 0 }}>
            <label className="field-label" htmlFor="fechaHasta">Hasta</label>
            <input id="fechaHasta" className="field-input" type="date" value={fechaHasta} onChange={(e) => setFechaHasta(e.target.value)} />
          </div>
        </div>

        {error && <div className="alert alert-danger" style={{ marginBottom: 'var(--sp-4)' }}>{error}</div>}

        {loading ? (
          <div className="state-block"><span className="spinner" /></div>
        ) : facturas.length === 0 ? (
          <div className="state-block">
            <span className="state-block-title">Sin facturas</span>
            <span>No hay facturas cargadas con estos filtros</span>
          </div>
        ) : (
          <div className="table-scroll">
            <table className="data-table">
              <thead>
                <tr>
                  <th>N° Factura</th>
                  <th>Laboratorio</th>
                  <th>Fecha</th>
                  <th>Monto</th>
                  <th>Envíos</th>
                  <th>Estado</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {facturas.map((f) => (
                  <tr key={f.id_factura} style={{ cursor: 'pointer' }} onClick={() => navigate(`/facturas/${f.id_factura}`)}>
                    <td style={{ fontFamily: 'var(--font-mono)' }}>{f.nro_factura}</td>
                    <td>{f.laboratorio_nombre}</td>
                    <td>{new Date(f.fecha_factura).toLocaleDateString()}</td>
                    <td className="num">{formatMonto(f.monto, f.moneda)}</td>
                    <td className="num">
                      {f.cantidad_envios > 0 ? (
                        <span
                          title={f.envios.map((en) => en.codigo_muestra).filter(Boolean).join(', ')}
                          style={{ textDecoration: 'underline dotted', cursor: 'help' }}
                        >
                          {f.cantidad_envios}
                        </span>
                      ) : (
                        f.cantidad_envios
                      )}
                    </td>
                    <td><span className={`badge ${BADGE_ESTADO[f.estado_pago] || 'badge-neutral'}`}>{labelEstado(f.estado_pago)}</span></td>
                    <td>
                      <button
                        type="button"
                        className="btn btn-ghost"
                        onClick={(e) => { e.stopPropagation(); navigate(`/facturas/${f.id_factura}`); }}
                      >
                        Ver →
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
