import { useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { useAuth } from '../../context/AuthContext';
import TopBar from '../../components/TopBar';
import { muestrasApi } from '../../api/muestras';
import { ApiError } from '../../api/client';

const BADGE_ESTADO_PAGO = {
  pendiente: 'badge-warn',
  pagado: 'badge-ok',
  anulado: 'badge-danger',
};

const LABEL_ESTADO_PAGO = {
  pendiente: 'Pendiente',
  pagado: 'Pagado',
  anulado: 'Anulado',
};

export default function MuestraEnviosDetallePage() {
  const { id } = useParams();
  const navigate = useNavigate();
  const { user } = useAuth();
  const puedeGestionar = ['analista_qc', 'qa', 'admin'].includes(user?.rol);

  const [muestra, setMuestra] = useState(null);
  const [envios, setEnvios] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  function recargar() {
    setLoading(true);
    setError('');
    Promise.all([muestrasApi.obtenerMuestra(id), muestrasApi.listarEnvios(id)])
      .then(([m, es]) => {
        setMuestra(m);
        setEnvios(es);
      })
      .catch((err) => setError(err instanceof ApiError ? err.message : 'No se pudo cargar la muestra'))
      .finally(() => setLoading(false));
  }

  useEffect(recargar, [id]);

  if (loading) {
    return (
      <div className="screen" style={{ alignItems: 'center', justifyContent: 'center' }}>
        <span className="spinner" />
      </div>
    );
  }

  if (error || !muestra) {
    return (
      <div className="screen">
        <TopBar titulo="Envíos" subtitulo="Envío de Muestras" onBack={() => navigate(-1)} />
        <div className="screen-content">
          <div className="alert alert-danger">{error || 'No encontrada'}</div>
        </div>
      </div>
    );
  }

  return (
    <div className="screen">
      <TopBar titulo={muestra.codigo_muestra} subtitulo="Envío de Muestras" onBack={() => navigate(-1)} />
      <div className="screen-content">
        <div className="card" style={{ marginBottom: 'var(--sp-5)' }}>
          <div style={{ fontFamily: 'var(--font-mono)', color: 'var(--ink-2)', fontSize: 'var(--fs-sm)' }}>
            {muestra.tipo_referencia === 'ir' ? 'IR' : 'Lote'} {muestra.nro_referencia}
          </div>
          <h1 style={{ fontSize: 'var(--fs-xl)' }}>{muestra.erp_DESART}</h1>
        </div>

        {puedeGestionar && (
          <button
            className="btn btn-primary"
            style={{ marginBottom: 'var(--sp-5)' }}
            onClick={() => navigate(`/muestras/${id}/envio`)}
          >
            + Nuevo envío
          </button>
        )}

        {envios.length === 0 ? (
          <div className="state-block">
            <span className="state-block-title">Sin envíos</span>
            <span>Todavía no se confirmó ningún envío para esta muestra</span>
          </div>
        ) : (
          envios.map((en) => (
            <div key={en.id_envio} className="card" style={{ marginBottom: 'var(--sp-4)' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 'var(--sp-3)' }}>
                <div>
                  <h2 style={{ fontSize: 'var(--fs-lg)' }}>{en.laboratorio_nombre}</h2>
                  <span style={{ fontSize: 'var(--fs-xs)', color: 'var(--ink-2)' }}>
                    Despachado el {new Date(en.fecha_despacho).toLocaleDateString()}
                    {en.nro_remito && ` — remito ${en.nro_remito}`}
                  </span>
                </div>
                <div style={{ display: 'flex', gap: 6 }}>
                  <span className={`badge ${en.completo ? 'badge-ok' : 'badge-warn'}`}>
                    {en.completo ? 'Completo' : 'Faltan resultados'}
                  </span>
                  <span className={`badge ${en.facturado ? 'badge-ok' : 'badge-neutral'}`}>
                    {en.facturado ? 'Facturado' : 'Sin Facturar'}
                  </span>
                </div>
              </div>

              <ul style={{ margin: '0 0 var(--sp-3)', paddingLeft: '1.2em' }}>
                {en.ensayos_solicitados.map((ens) => (
                  <li key={ens.id_espec_ensayo}>
                    {ens.nombre_ensayo}
                    {ens.valor_numerico != null || ens.valor_cualitativo
                      ? <span className="badge badge-neutral" style={{ marginLeft: 6 }}>cargado</span>
                      : null}
                  </li>
                ))}
              </ul>

              <div style={{ marginBottom: 'var(--sp-3)', fontSize: 'var(--fs-sm)' }}>
                {en.factura ? (
                  <span>
                    Factura: <span style={{ fontFamily: 'var(--font-mono)' }}>{en.factura.nro_factura}</span>{' '}
                    <span className={`badge ${BADGE_ESTADO_PAGO[en.factura.estado_pago] || 'badge-neutral'}`}>
                      {LABEL_ESTADO_PAGO[en.factura.estado_pago] || en.factura.estado_pago}
                    </span>{' '}
                    {puedeGestionar && (
                      <button
                        type="button"
                        className="btn btn-ghost"
                        style={{ padding: 0 }}
                        onClick={() => navigate(`/facturas/${en.factura.id_factura}`)}
                      >
                        Ver factura →
                      </button>
                    )}
                  </span>
                ) : (
                  <span style={{ color: 'var(--ink-2)' }}>Sin factura asociada</span>
                )}
              </div>

              <div style={{ display: 'flex', gap: 'var(--sp-3)', flexWrap: 'wrap' }}>
                <button className="btn btn-secondary" onClick={() => navigate(`/muestras/${id}/envios/${en.id_envio}/remito`)}>
                  Ver remito
                </button>
                {en.tiene_remito && (
                  <button className="btn btn-secondary" onClick={() => navigate(`/muestras/${id}/envios/${en.id_envio}/remito#constancia-recepcion`)}>
                    Constancia de Recepción →
                  </button>
                )}
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );
}
