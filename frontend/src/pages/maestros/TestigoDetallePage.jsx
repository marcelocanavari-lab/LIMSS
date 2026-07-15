import { useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { useAuth } from '../../context/AuthContext';
import TopBar from '../../components/TopBar';
import { maestrosApi } from '../../api/maestros';
import { ApiError } from '../../api/client';

export default function TestigoDetallePage() {
  const { id } = useParams();
  const navigate = useNavigate();
  const { user } = useAuth();
  const puedeGestionar = ['admin', 'qa'].includes(user?.rol);

  const [testigo, setTestigo] = useState(null);
  const [movimientos, setMovimientos] = useState([]);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);

  const [ajusteCantidad, setAjusteCantidad] = useState('');
  const [ajusteObs, setAjusteObs] = useState('');
  const [ajustando, setAjustando] = useState(false);
  const [ajusteError, setAjusteError] = useState('');

  function cargar() {
    setLoading(true);
    Promise.all([maestrosApi.obtenerTestigo(id), maestrosApi.historialMovimientos(id)])
      .then(([t, m]) => {
        setTestigo(t);
        setMovimientos(m);
      })
      .catch((err) => setError(err instanceof ApiError ? err.message : 'No se pudo cargar el testigo'))
      .finally(() => setLoading(false));
  }

  useEffect(cargar, [id]);

  async function verCertificado() {
    try {
      const blob = await maestrosApi.descargarCertificado(id);
      const url = URL.createObjectURL(blob);
      window.open(url, '_blank');
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'No se pudo descargar el certificado');
    }
  }

  async function toggleEstado() {
    try {
      await maestrosApi.cambiarEstadoTestigo(id, !testigo.activo);
      cargar();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'No se pudo cambiar el estado');
    }
  }

  async function handleAjuste(e) {
    e.preventDefault();
    setAjusteError('');
    const cantidad = Number(ajusteCantidad);
    if (!ajusteCantidad || Number.isNaN(cantidad) || cantidad === 0) {
      setAjusteError('Ingresá una cantidad distinta de cero');
      return;
    }
    setAjustando(true);
    try {
      await maestrosApi.ajustarStockTestigo(id, cantidad, ajusteObs.trim() || undefined);
      setAjusteCantidad('');
      setAjusteObs('');
      cargar();
    } catch (err) {
      setAjusteError(err instanceof ApiError ? err.message : 'No se pudo ajustar el stock');
    } finally {
      setAjustando(false);
    }
  }

  if (loading) {
    return (
      <div className="screen" style={{ alignItems: 'center', justifyContent: 'center' }}>
        <span className="spinner" />
      </div>
    );
  }

  if (error && !testigo) {
    return (
      <div className="screen">
        <TopBar titulo="Testigo" subtitulo="Datos Maestros" onBack={() => navigate('/maestros/testigos')} />
        <div className="screen-content">
          <div className="alert alert-danger">{error}</div>
        </div>
      </div>
    );
  }

  return (
    <div className="screen">
      <TopBar titulo={testigo.nombre} subtitulo={testigo.codigo} onBack={() => navigate('/maestros/testigos')} />
      <div className="screen-content">
        {error && <div className="alert alert-danger" style={{ marginBottom: 'var(--sp-4)' }}>{error}</div>}

        <div className="card" style={{ marginBottom: 'var(--sp-5)' }}>
          <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap', marginBottom: 'var(--sp-4)' }}>
            {testigo.vencido && <span className="badge badge-danger">Vencido</span>}
            {!testigo.vencido && testigo.por_vencer && <span className="badge badge-warn">Vence en menos de 30 días</span>}
            {testigo.stock_bajo && <span className="badge badge-warn">Stock bajo</span>}
            <span className={testigo.activo ? 'badge badge-ok' : 'badge badge-neutral'}>
              {testigo.activo ? 'Activo' : 'Inactivo'}
            </span>
          </div>

          <table className="data-table">
            <tbody>
              <tr><td>Lote</td><td className="num" style={{ textAlign: 'left' }}>{testigo.nro_lote}</td></tr>
              <tr><td>Vencimiento</td><td className="num" style={{ textAlign: 'left' }}>{testigo.fecha_vencimiento}</td></tr>
              <tr><td>Stock actual</td><td className="num" style={{ textAlign: 'left' }}>{testigo.stock_actual} {testigo.unidad_medida || ''}</td></tr>
              <tr><td>Stock mínimo</td><td className="num" style={{ textAlign: 'left' }}>{testigo.stock_minimo} {testigo.unidad_medida || ''}</td></tr>
              <tr><td>Observaciones</td><td style={{ textAlign: 'left' }}>{testigo.observaciones || '—'}</td></tr>
            </tbody>
          </table>

          <div style={{ display: 'flex', gap: 'var(--sp-3)', marginTop: 'var(--sp-4)', flexWrap: 'wrap' }}>
            <button className="btn btn-secondary" onClick={verCertificado}>Ver certificado (PDF)</button>
            {puedeGestionar && (
              <button className="btn btn-secondary" onClick={() => navigate(`/maestros/testigos/${id}/editar`)}>
                Editar
              </button>
            )}
            {puedeGestionar && (
              <button className="btn btn-secondary" onClick={toggleEstado}>
                {testigo.activo ? 'Desactivar' : 'Activar'}
              </button>
            )}
          </div>
        </div>

        {puedeGestionar && (
          <div className="card" style={{ marginBottom: 'var(--sp-5)' }}>
            <h2 style={{ fontSize: 'var(--fs-lg)', marginBottom: 'var(--sp-3)' }}>Ajustar stock</h2>
            <form onSubmit={handleAjuste}>
              <div style={{ display: 'flex', gap: 'var(--sp-3)', alignItems: 'flex-end', flexWrap: 'wrap' }}>
                <div className="field" style={{ flex: '0 0 160px' }}>
                  <label className="field-label">Cantidad (+/-)</label>
                  <input
                    className="field-input"
                    type="number"
                    step="any"
                    value={ajusteCantidad}
                    onChange={(e) => setAjusteCantidad(e.target.value)}
                    disabled={ajustando}
                  />
                </div>
                <div className="field" style={{ flex: 1, minWidth: 200 }}>
                  <label className="field-label">Motivo</label>
                  <input
                    className="field-input"
                    value={ajusteObs}
                    onChange={(e) => setAjusteObs(e.target.value)}
                    disabled={ajustando}
                  />
                </div>
                <button type="submit" className="btn btn-primary" disabled={ajustando} style={{ marginBottom: 'var(--sp-4)' }}>
                  {ajustando ? <span className="spinner" /> : 'Aplicar'}
                </button>
              </div>
              {ajusteError && <div className="alert alert-danger">{ajusteError}</div>}
            </form>
          </div>
        )}

        <h2 style={{ fontSize: 'var(--fs-lg)', marginBottom: 'var(--sp-3)' }}>Historial de movimientos</h2>
        {movimientos.length === 0 ? (
          <div className="state-block"><span>Sin movimientos registrados</span></div>
        ) : (
          <table className="data-table">
            <thead>
              <tr>
                <th>Fecha</th>
                <th>Tipo</th>
                <th>Cantidad</th>
                <th>Stock resultante</th>
                <th>Observaciones</th>
              </tr>
            </thead>
            <tbody>
              {movimientos.map((m) => (
                <tr key={m.id_movimiento}>
                  <td>{new Date(m.fecha_hora).toLocaleString()}</td>
                  <td>{m.tipo}</td>
                  <td className="num">{m.cantidad}</td>
                  <td className="num">{m.stock_resultante}</td>
                  <td>{m.observaciones || '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
