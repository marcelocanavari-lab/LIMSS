import { useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { useAuth } from '../../context/AuthContext';
import TopBar from '../../components/TopBar';
import { facturasApi } from '../../api/facturas';
import { ApiError } from '../../api/client';

const BADGE_ESTADO = {
  pendiente: 'badge-warn',
  pagado: 'badge-ok',
  anulado: 'badge-danger',
};

const LABEL_ESTADO = {
  pendiente: 'Pendiente',
  pagado: 'Pagado',
  anulado: 'Anulado',
};

function formatMonto(monto, moneda) {
  return `${moneda} ${Number(monto).toLocaleString('es-AR', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

export default function FacturaDetallePage() {
  const { id } = useParams();
  const navigate = useNavigate();
  const { user } = useAuth();
  const puedeGestionar = ['analista_qc', 'qa', 'admin'].includes(user?.rol);
  const puedeGestionarPago = ['qa', 'admin'].includes(user?.rol);

  const [factura, setFactura] = useState(null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);

  const [mostrarPago, setMostrarPago] = useState(false);
  const [fechaPago, setFechaPago] = useState('');
  const [nroComprobante, setNroComprobante] = useState('');
  const [obsPago, setObsPago] = useState('');
  const [guardandoPago, setGuardandoPago] = useState(false);
  const [errorPago, setErrorPago] = useState('');

  const [mostrarAnular, setMostrarAnular] = useState(false);
  const [obsAnular, setObsAnular] = useState('');
  const [anulando, setAnulando] = useState(false);
  const [errorAnular, setErrorAnular] = useState('');

  function cargar() {
    setLoading(true);
    facturasApi
      .obtenerFactura(id)
      .then(setFactura)
      .catch((err) => setError(err instanceof ApiError ? err.message : 'No se pudo cargar la factura'))
      .finally(() => setLoading(false));
  }

  useEffect(cargar, [id]);

  function abrirPago() {
    setFechaPago('');
    setNroComprobante('');
    setObsPago('');
    setErrorPago('');
    setMostrarPago(true);
  }

  async function handleRegistrarPago(e) {
    e.preventDefault();
    if (!fechaPago) {
      setErrorPago('Ingresá la fecha de pago');
      return;
    }
    setErrorPago('');
    setGuardandoPago(true);
    try {
      await facturasApi.registrarPago(id, {
        fecha_pago: fechaPago,
        nro_comprobante_pago: nroComprobante.trim() || null,
        observaciones: obsPago.trim() || null,
      });
      setMostrarPago(false);
      cargar();
    } catch (err) {
      setErrorPago(err instanceof ApiError ? err.message : 'No se pudo registrar el pago');
    } finally {
      setGuardandoPago(false);
    }
  }

  function abrirAnular() {
    setObsAnular('');
    setErrorAnular('');
    setMostrarAnular(true);
  }

  async function handleAnular(e) {
    e.preventDefault();
    setErrorAnular('');
    setAnulando(true);
    try {
      await facturasApi.anularFactura(id, { observaciones: obsAnular.trim() || null });
      setMostrarAnular(false);
      cargar();
    } catch (err) {
      setErrorAnular(err instanceof ApiError ? err.message : 'No se pudo anular la factura');
    } finally {
      setAnulando(false);
    }
  }

  if (loading) {
    return (
      <div className="screen" style={{ alignItems: 'center', justifyContent: 'center' }}>
        <span className="spinner" />
      </div>
    );
  }

  if (error && !factura) {
    return (
      <div className="screen">
        <TopBar titulo="Factura" subtitulo="Facturación de Laboratorios" onBack={() => navigate(-1)} />
        <div className="screen-content">
          <div className="alert alert-danger">{error}</div>
        </div>
      </div>
    );
  }

  return (
    <div className="screen">
      <TopBar titulo={factura.nro_factura} subtitulo={factura.laboratorio_nombre} onBack={() => navigate(-1)} />
      <div className="screen-content">
        {error && <div className="alert alert-danger" style={{ marginBottom: 'var(--sp-4)' }}>{error}</div>}

        <div className="card" style={{ marginBottom: 'var(--sp-5)' }}>
          <div style={{ display: 'flex', gap: 4, marginBottom: 'var(--sp-4)' }}>
            <span className={`badge ${BADGE_ESTADO[factura.estado_pago] || 'badge-neutral'}`}>
              {LABEL_ESTADO[factura.estado_pago] || factura.estado_pago}
            </span>
          </div>

          <table className="data-table">
            <tbody>
              <tr><td>Laboratorio</td><td style={{ textAlign: 'left' }}>{factura.laboratorio_nombre}</td></tr>
              <tr><td>Fecha de factura</td><td className="num" style={{ textAlign: 'left' }}>{new Date(factura.fecha_factura).toLocaleDateString()}</td></tr>
              <tr><td>Fecha de recepción</td><td className="num" style={{ textAlign: 'left' }}>{factura.fecha_recepcion ? new Date(factura.fecha_recepcion).toLocaleDateString() : '—'}</td></tr>
              <tr><td>Monto</td><td className="num" style={{ textAlign: 'left' }}>{formatMonto(factura.monto, factura.moneda)}</td></tr>
              <tr><td>Descripción</td><td style={{ textAlign: 'left' }}>{factura.descripcion || '—'}</td></tr>
              {factura.estado_pago === 'pagado' && (
                <>
                  <tr><td>Fecha de pago</td><td className="num" style={{ textAlign: 'left' }}>{factura.fecha_pago ? new Date(factura.fecha_pago).toLocaleDateString() : '—'}</td></tr>
                  <tr><td>N° comprobante de pago</td><td style={{ textAlign: 'left' }}>{factura.nro_comprobante_pago || '—'}</td></tr>
                </>
              )}
              {factura.observaciones && (
                <tr><td>Observaciones</td><td style={{ textAlign: 'left' }}>{factura.observaciones}</td></tr>
              )}
            </tbody>
          </table>

          <div style={{ display: 'flex', gap: 'var(--sp-3)', marginTop: 'var(--sp-4)', flexWrap: 'wrap' }}>
            {puedeGestionar && factura.estado_pago !== 'anulado' && (
              <button className="btn btn-secondary" onClick={() => navigate(`/facturas/${id}/editar`)}>
                Editar
              </button>
            )}
            {puedeGestionarPago && factura.estado_pago === 'pendiente' && (
              <button className="btn btn-primary" onClick={abrirPago}>
                Registrar pago
              </button>
            )}
            {puedeGestionarPago && factura.estado_pago === 'pendiente' && (
              <button className="btn btn-secondary" style={{ color: 'var(--danger)' }} onClick={abrirAnular}>
                Anular
              </button>
            )}
          </div>
        </div>

        <h2 style={{ fontSize: 'var(--fs-lg)', marginBottom: 'var(--sp-3)' }}>Envíos vinculados</h2>
        {factura.envios.length === 0 ? (
          <div className="state-block"><span>Esta factura no tiene envíos vinculados</span></div>
        ) : (
          <table className="data-table">
            <thead>
              <tr>
                <th>N° Remito</th>
                <th>Muestra</th>
                <th>IR</th>
                <th>Material</th>
                <th>Fecha</th>
                <th>Ensayos</th>
              </tr>
            </thead>
            <tbody>
              {factura.envios.map((en) => (
                <tr key={en.id_envio}>
                  <td style={{ fontFamily: 'var(--font-mono)' }}>{en.nro_remito || '—'}</td>
                  <td>{en.codigo_muestra || '—'}</td>
                  <td>{en.erp_nro_ir || '—'}</td>
                  <td>{en.erp_DESART ? `${en.erp_DESART}${en.erp_CODART ? ` (${en.erp_CODART})` : ''}` : '—'}</td>
                  <td>{new Date(en.fecha_despacho).toLocaleDateString()}</td>
                  <td className="num">{en.cantidad_ensayos}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {mostrarPago && (
        <div
          style={{
            position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.5)',
            display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 100, padding: 'var(--sp-4)',
          }}
          onClick={() => setMostrarPago(false)}
        >
          <form
            onSubmit={handleRegistrarPago}
            className="card"
            style={{ width: '90%', maxWidth: 420 }}
            onClick={(e) => e.stopPropagation()}
          >
            <h2 style={{ fontSize: 'var(--fs-lg)', marginBottom: 'var(--sp-3)' }}>Registrar pago</h2>

            <div className="field">
              <label className="field-label" htmlFor="fechaPago">Fecha de pago</label>
              <input
                id="fechaPago"
                className="field-input"
                type="date"
                value={fechaPago}
                onChange={(e) => setFechaPago(e.target.value)}
                disabled={guardandoPago}
                autoFocus
              />
            </div>

            <div className="field">
              <label className="field-label" htmlFor="nroComprobante">N° de comprobante (opcional)</label>
              <input
                id="nroComprobante"
                className="field-input"
                value={nroComprobante}
                onChange={(e) => setNroComprobante(e.target.value)}
                disabled={guardandoPago}
              />
            </div>

            <div className="field" style={{ marginBottom: 0 }}>
              <label className="field-label" htmlFor="obsPago">Observaciones (opcional)</label>
              <input
                id="obsPago"
                className="field-input"
                value={obsPago}
                onChange={(e) => setObsPago(e.target.value)}
                disabled={guardandoPago}
              />
            </div>

            {errorPago && <div className="alert alert-danger" style={{ marginTop: 'var(--sp-3)' }}>{errorPago}</div>}

            <div style={{ display: 'flex', gap: 'var(--sp-3)', marginTop: 'var(--sp-4)' }}>
              <button type="button" className="btn btn-ghost" onClick={() => setMostrarPago(false)} disabled={guardandoPago}>Cancelar</button>
              <button type="submit" className="btn btn-primary" disabled={guardandoPago}>
                {guardandoPago ? <span className="spinner" /> : 'Confirmar pago'}
              </button>
            </div>
          </form>
        </div>
      )}

      {mostrarAnular && (
        <div
          style={{
            position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.5)',
            display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 100, padding: 'var(--sp-4)',
          }}
          onClick={() => setMostrarAnular(false)}
        >
          <form
            onSubmit={handleAnular}
            className="card"
            style={{ width: '90%', maxWidth: 420 }}
            onClick={(e) => e.stopPropagation()}
          >
            <h2 style={{ fontSize: 'var(--fs-lg)', marginBottom: 'var(--sp-3)' }}>Anular factura</h2>
            <p style={{ marginBottom: 'var(--sp-3)' }}>Esta acción no se puede deshacer.</p>

            <div className="field" style={{ marginBottom: 0 }}>
              <label className="field-label" htmlFor="obsAnular">Motivo (opcional)</label>
              <input
                id="obsAnular"
                className="field-input"
                value={obsAnular}
                onChange={(e) => setObsAnular(e.target.value)}
                disabled={anulando}
                autoFocus
              />
            </div>

            {errorAnular && <div className="alert alert-danger" style={{ marginTop: 'var(--sp-3)' }}>{errorAnular}</div>}

            <div style={{ display: 'flex', gap: 'var(--sp-3)', marginTop: 'var(--sp-4)' }}>
              <button type="button" className="btn btn-ghost" onClick={() => setMostrarAnular(false)} disabled={anulando}>Cancelar</button>
              <button type="submit" className="btn btn-primary" disabled={anulando}>
                {anulando ? <span className="spinner" /> : 'Confirmar anulación'}
              </button>
            </div>
          </form>
        </div>
      )}
    </div>
  );
}
