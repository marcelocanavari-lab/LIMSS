import { useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import TopBar from '../../components/TopBar';
import { muestrasApi } from '../../api/muestras';
import { ApiError } from '../../api/client';
import { BADGE_POR_ESTADO } from './MuestrasPage';

function resultadoTexto(en) {
  if (en.tipo_dato === 'numerico') {
    return en.valor_numerico ?? '—';
  }
  return en.valor_cualitativo || '—';
}

function badgeCumple(en) {
  if (en.dentro_especificacion === null || en.dentro_especificacion === undefined) {
    return <span className="badge badge-neutral">Sin resultado</span>;
  }
  return en.dentro_especificacion
    ? <span className="badge badge-ok">Cumple</span>
    : <span className="badge badge-danger">No cumple</span>;
}

export default function ConsultaMuestraDetallePage() {
  const { id } = useParams();
  const navigate = useNavigate();

  const [recorrido, setRecorrido] = useState(null);
  const [error, setError] = useState('');

  useEffect(() => {
    muestrasApi
      .obtenerRecorrido(id)
      .then(setRecorrido)
      .catch((err) => setError(err instanceof ApiError ? err.message : 'No se pudo cargar el recorrido de la muestra'));
  }, [id]);

  if (error) {
    return (
      <div className="screen">
        <TopBar titulo="Consulta de Muestras" subtitulo="Recorrido" onBack={() => navigate('/consulta-muestras')} />
        <div className="screen-content">
          <div className="alert alert-danger">{error}</div>
        </div>
      </div>
    );
  }

  if (!recorrido) {
    return (
      <div className="screen" style={{ alignItems: 'center', justifyContent: 'center' }}>
        <span className="spinner" />
      </div>
    );
  }

  return (
    <div className="screen">
      <TopBar titulo={recorrido.codigo_muestra} subtitulo="Consulta de Muestras" onBack={() => navigate('/consulta-muestras')} />
      <div className="screen-content">
        <button className="btn btn-primary no-print" style={{ marginBottom: 'var(--sp-4)' }} onClick={() => window.print()}>
          Imprimir reporte →
        </button>

        <div className="printable">
          <div className="card" style={{ marginBottom: 'var(--sp-4)' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 'var(--sp-3)' }}>
              <div>
                <div style={{ fontFamily: 'var(--font-mono)', color: 'var(--ink-2)', fontSize: 'var(--fs-sm)' }}>
                  {recorrido.tipo_referencia === 'ir' ? 'IR' : 'Lote'} {recorrido.nro_referencia}
                </div>
                <h1 style={{ fontSize: 'var(--fs-xl)' }}>{recorrido.erp_DESART}</h1>
              </div>
              <span className={`badge ${BADGE_POR_ESTADO[recorrido.estado] || 'badge-neutral'}`}>
                {recorrido.estado.replace(/_/g, ' ')}
              </span>
            </div>
            <table className="data-table">
              <tbody>
                <tr><td>Código</td><td style={{ textAlign: 'left' }}>{recorrido.erp_CODART}</td></tr>
                <tr><td>Fecha de muestreo</td><td style={{ textAlign: 'left' }}>{new Date(recorrido.fecha_muestreo).toLocaleString()}</td></tr>
                <tr><td>Muestreador</td><td style={{ textAlign: 'left' }}>{recorrido.usuario_muestreo_nombre}</td></tr>
              </tbody>
            </table>
          </div>

          {recorrido.envios.length === 0 ? (
            <div className="alert alert-info" style={{ marginBottom: 'var(--sp-4)' }}>Esta muestra todavía no tiene envíos registrados.</div>
          ) : (
            recorrido.envios.map((en) => (
              <div key={en.id_envio} className="card" style={{ marginBottom: 'var(--sp-4)' }}>
                <h2 style={{ fontSize: 'var(--fs-lg)', marginBottom: 'var(--sp-2)' }}>{en.laboratorio_nombre}</h2>
                <table className="data-table" style={{ marginBottom: 'var(--sp-3)' }}>
                  <tbody>
                    <tr><td>Fecha de despacho</td><td style={{ textAlign: 'left' }}>{new Date(en.fecha_despacho).toLocaleString()}</td></tr>
                    <tr><td>N° remito</td><td style={{ textAlign: 'left' }}>{en.nro_remito || '—'}</td></tr>
                    <tr>
                      <td>Testigo(s)</td>
                      <td style={{ textAlign: 'left' }}>
                        {en.testigos.length > 0 ? en.testigos.map((t) => `${t.codigo} — ${t.nombre}`).join(', ') : '—'}
                      </td>
                    </tr>
                    {en.protocolo && (
                      <tr><td>Protocolo externo</td><td style={{ textAlign: 'left' }}>{en.protocolo.nro_protocolo_ext}</td></tr>
                    )}
                  </tbody>
                </table>

                <table className="data-table">
                  <thead>
                    <tr>
                      <th>Ensayo</th>
                      <th>Resultado</th>
                      <th>Cumple/No cumple</th>
                    </tr>
                  </thead>
                  <tbody>
                    {en.ensayos.map((ens) => (
                      <tr key={ens.id_espec_ensayo}>
                        <td>{ens.nombre_ensayo}</td>
                        <td>{resultadoTexto(ens)}</td>
                        <td>{badgeCumple(ens)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ))
          )}

          <div className="card" style={{ marginBottom: 'var(--sp-4)' }}>
            <h2 style={{ fontSize: 'var(--fs-lg)', marginBottom: 'var(--sp-2)' }}>Dictamen final</h2>
            {recorrido.dictamen ? (
              <table className="data-table">
                <tbody>
                  <tr><td>Estado</td><td style={{ textAlign: 'left' }}>{recorrido.dictamen.estado_dictamen}</td></tr>
                  <tr><td>QA firmante</td><td style={{ textAlign: 'left' }}>{recorrido.dictamen.usuario_qa_nombre}</td></tr>
                  <tr><td>Fecha</td><td style={{ textAlign: 'left' }}>{new Date(recorrido.dictamen.fecha_dictamen).toLocaleString()}</td></tr>
                  {recorrido.dictamen.justificacion_oos && (
                    <tr><td>Justificación OOS</td><td style={{ textAlign: 'left' }}>{recorrido.dictamen.justificacion_oos}</td></tr>
                  )}
                  {recorrido.dictamen.observaciones && (
                    <tr><td>Observaciones</td><td style={{ textAlign: 'left' }}>{recorrido.dictamen.observaciones}</td></tr>
                  )}
                </tbody>
              </table>
            ) : (
              <p style={{ color: 'var(--ink-2)' }}>Todavía no se emitió el dictamen final para esta muestra.</p>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
