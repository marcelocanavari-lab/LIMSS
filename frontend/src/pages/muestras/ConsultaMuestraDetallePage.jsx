import { useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import TopBar from '../../components/TopBar';
import { muestrasApi } from '../../api/muestras';
import { ApiError } from '../../api/client';
import { BADGE_POR_ESTADO } from './MuestrasPage';

const BADGE_DICTAMEN = {
  aprobado: 'badge-ok',
  rechazado: 'badge-danger',
  cuarentena: 'badge-warn',
};

function resultadoTexto(en) {
  if (en.tipo_dato === 'numerico') {
    return en.valor_numerico ?? '—';
  }
  return en.valor_cualitativo || '—';
}

function especificacionTexto(en) {
  if (en.tipo_dato === 'numerico') {
    return `${en.limite_inferior ?? '—'} a ${en.limite_superior ?? '—'} ${en.unidad_medida || ''}`;
  }
  return en.valor_requerido || '—';
}

function badgeCumple(en) {
  if (en.dentro_especificacion === null || en.dentro_especificacion === undefined) {
    return <span className="badge badge-neutral">Sin resultado</span>;
  }
  return en.dentro_especificacion
    ? <span className="badge badge-ok">Cumple</span>
    : <span className="badge badge-danger">No cumple</span>;
}

function estadoSimbolo(en) {
  if (en.dentro_especificacion === null || en.dentro_especificacion === undefined) {
    return <span style={{ color: 'var(--ink-2)' }}>— Sin resultado</span>;
  }
  return en.dentro_especificacion
    ? <span style={{ color: 'var(--ok)' }}>✓ Cumple</span>
    : <span style={{ color: 'var(--danger)' }}>✗ No cumple</span>;
}

function formatFechaSimple(fechaISO) {
  if (!fechaISO) return null;
  const [anio, mes, dia] = fechaISO.split('-');
  return `${dia}/${mes}/${anio}`;
}

function Seccion({ titulo, defaultOpen = true, children }) {
  const [abierto, setAbierto] = useState(defaultOpen);
  return (
    <div className="card" style={{ marginBottom: 'var(--sp-4)' }}>
      <div className="acordeon-header" onClick={() => setAbierto((v) => !v)}>
        <h2 style={{ fontSize: 'var(--fs-lg)', margin: 0 }}>{titulo}</h2>
        <span className="acordeon-toggle no-print">{abierto ? '▾' : '▸'}</span>
      </div>
      <div className={`acordeon-body${abierto ? '' : ' cerrado'}`}>{children}</div>
    </div>
  );
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
        <TopBar titulo="Consulta de Muestras" subtitulo="Recorrido" onBack={() => navigate(-1)} />
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

  const s = recorrido.solicitud;
  const datosContenedor = s
    ? [
        ['Identificación de contenedor', s.datos_fisicos.identificacion_contenedor],
        ['Aspecto externo', s.datos_fisicos.aspecto_externo],
        ['Cierre', s.datos_fisicos.cierre],
        ['Aspecto interno', s.datos_fisicos.aspecto_interno],
        ['Precintos', s.datos_fisicos.precintos],
        ['Materias extrañas', s.datos_fisicos.materias_extranas],
        ['Olor', s.datos_fisicos.olor],
        ['Color', s.datos_fisicos.color],
        ['N° de bultos muestreados', s.datos_fisicos.nro_bultos_muestreados],
        ['Fecha de vencimiento real', formatFechaSimple(s.datos_fisicos.fecha_vencimiento_real)],
        ['Fecha de reanálisis real', formatFechaSimple(s.datos_fisicos.fecha_reanalisis_real)],
        ['Observaciones del muestreo', s.datos_fisicos.observaciones_muestreo],
      ].filter(([, valor]) => valor !== null && valor !== undefined && valor !== '')
    : [];

  return (
    <div className="screen">
      <TopBar titulo={recorrido.codigo_muestra} subtitulo="Consulta de Muestras" onBack={() => navigate(-1)} />
      <div className="screen-content">
        <div style={{ display: 'flex', gap: 'var(--sp-3)', marginBottom: 'var(--sp-4)' }}>
          <button className="btn btn-primary no-print" onClick={() => window.print()}>
            Imprimir reporte →
          </button>
          <button className="btn btn-ghost no-print" onClick={() => navigate(-1)}>
            Volver
          </button>
        </div>

        <div className="printable">
          {/* Sección 1 — Datos de la muestra */}
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
                <tr><td>Tipo de material</td><td style={{ textAlign: 'left' }}>{recorrido.tipo_material || '—'}</td></tr>
                {recorrido.erp_proveedor && (
                  <tr><td>Proveedor</td><td style={{ textAlign: 'left' }}>{recorrido.erp_proveedor}</td></tr>
                )}
                <tr><td>Fecha de muestreo</td><td style={{ textAlign: 'left' }}>{new Date(recorrido.fecha_muestreo).toLocaleString()}</td></tr>
                <tr><td>Muestreador</td><td style={{ textAlign: 'left' }}>{recorrido.usuario_muestreo_nombre}</td></tr>
              </tbody>
            </table>
          </div>

          {/* Sección 2 — Solicitud de muestreo */}
          {s && (
            <Seccion titulo="Solicitud de muestreo">
              <table className="data-table" style={{ marginBottom: 'var(--sp-3)' }}>
                <tbody>
                  <tr><td>N° Solicitud</td><td style={{ textAlign: 'left' }}>{s.nro_solicitud}</td></tr>
                  <tr><td>Generada por</td><td style={{ textAlign: 'left' }}>{s.usuario_qa_nombre}</td></tr>
                  <tr><td>Fecha de solicitud</td><td style={{ textAlign: 'left' }}>{new Date(s.fecha_solicitud).toLocaleString()}</td></tr>
                  {s.proveedor_nombre && (
                    <tr>
                      <td>Proveedor</td>
                      <td style={{ textAlign: 'left' }}>
                        {s.proveedor_codigo ? `${s.proveedor_codigo} - ${s.proveedor_nombre}` : s.proveedor_nombre}
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>

              {datosContenedor.length > 0 && (
                <>
                  <h3 style={{ fontSize: 'var(--fs-base)', marginBottom: 'var(--sp-2)' }}>Datos del contenedor</h3>
                  <table className="data-table" style={{ marginBottom: 'var(--sp-3)' }}>
                    <tbody>
                      {datosContenedor.map(([label, valor]) => (
                        <tr key={label}><td>{label}</td><td style={{ textAlign: 'left' }}>{valor}</td></tr>
                      ))}
                    </tbody>
                  </table>
                </>
              )}

              <h3 style={{ fontSize: 'var(--fs-base)', marginBottom: 'var(--sp-2)' }}>Resultados internos</h3>
              {recorrido.resultados_orden_trabajo.length === 0 ? (
                <p style={{ color: 'var(--ink-2)' }}>Sin resultados internos cargados.</p>
              ) : (
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>Ensayo</th>
                      <th>Resultado</th>
                      <th>Cumple/No cumple</th>
                    </tr>
                  </thead>
                  <tbody>
                    {recorrido.resultados_orden_trabajo.map((ens) => (
                      <tr key={ens.id_espec_ensayo}>
                        <td>{ens.nombre_ensayo}</td>
                        <td>{resultadoTexto(ens)}</td>
                        <td>{badgeCumple(ens)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </Seccion>
          )}

          {/* Sección 3 — Envíos y resultados externos */}
          {recorrido.envios.length === 0 ? (
            <div className="alert alert-info" style={{ marginBottom: 'var(--sp-4)' }}>Esta muestra todavía no tiene envíos registrados.</div>
          ) : (
            recorrido.envios.map((en) => (
              <Seccion key={en.id_envio} titulo={`Envío N° ${en.nro_remito || en.id_envio} — ${en.laboratorio_nombre}`}>
                <table className="data-table" style={{ marginBottom: 'var(--sp-3)' }}>
                  <tbody>
                    <tr><td>Fecha de envío</td><td style={{ textAlign: 'left' }}>{new Date(en.fecha_despacho).toLocaleString()}</td></tr>
                    <tr>
                      <td>Testigo utilizado</td>
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
                      <th>Metodología</th>
                      <th>Especificación</th>
                      <th>Resultado</th>
                      <th>Estado</th>
                    </tr>
                  </thead>
                  <tbody>
                    {en.ensayos.map((ens) => (
                      <tr key={ens.id_espec_ensayo}>
                        <td>{ens.nombre_ensayo}</td>
                        <td>{ens.metodologia || '—'}</td>
                        <td>{especificacionTexto(ens)}</td>
                        <td>{resultadoTexto(ens)}</td>
                        <td>{estadoSimbolo(ens)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </Seccion>
            ))
          )}

          {/* Sección 4 — Dictamen final */}
          <Seccion titulo="Dictamen final">
            {recorrido.dictamen ? (
              <>
                <span className={`badge ${BADGE_DICTAMEN[recorrido.dictamen.estado_dictamen] || 'badge-neutral'}`} style={{ fontSize: 'var(--fs-lg)', padding: 'var(--sp-2) var(--sp-4)', marginBottom: 'var(--sp-3)', display: 'inline-block' }}>
                  {recorrido.dictamen.estado_dictamen.toUpperCase()}
                </span>
                <table className="data-table">
                  <tbody>
                    <tr><td>QA firmante</td><td style={{ textAlign: 'left' }}>{recorrido.dictamen.usuario_qa_nombre}</td></tr>
                    <tr><td>Fecha del dictamen</td><td style={{ textAlign: 'left' }}>{new Date(recorrido.dictamen.fecha_dictamen).toLocaleString()}</td></tr>
                    {recorrido.dictamen.justificacion_oos && (
                      <tr><td>Justificación</td><td style={{ textAlign: 'left' }}>{recorrido.dictamen.justificacion_oos}</td></tr>
                    )}
                    {recorrido.dictamen.observaciones && (
                      <tr><td>Observaciones</td><td style={{ textAlign: 'left' }}>{recorrido.dictamen.observaciones}</td></tr>
                    )}
                  </tbody>
                </table>
              </>
            ) : (
              <p style={{ color: 'var(--ink-2)' }}>Pendiente de dictamen QA</p>
            )}
          </Seccion>
        </div>
      </div>
    </div>
  );
}
