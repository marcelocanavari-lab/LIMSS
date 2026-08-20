import { useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import TopBar from '../../components/TopBar';
import { muestrasApi } from '../../api/muestras';
import { ApiError, abrirPdfConAuth } from '../../api/client';
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

// marginBottom: 0 + border (ya la trae .card) en vez de var(--sp-4) -- un
// bloque termina y el siguiente empieza inmediatamente después, sin espacio
// en blanco entre ellos (pedido explícito: menos hojas al imprimir).
function Seccion({ titulo, defaultOpen = true, children }) {
  const [abierto, setAbierto] = useState(defaultOpen);
  return (
    <div className="card" style={{ marginBottom: 0, padding: 'var(--sp-3)' }}>
      <div className="acordeon-header" onClick={() => setAbierto((v) => !v)}>
        <h2 style={{ fontSize: 'var(--fs-base)', margin: 0 }}>{titulo}</h2>
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
  // Si ya existe una etiqueta impresa para esta muestra, la próxima queda
  // registrada como reimpresión (lims_etiquetas.reimpresion) -- se refleja
  // en el texto del botón en vez de imprimir/reimprimir en silencio.
  const [tieneEtiqueta, setTieneEtiqueta] = useState(false);

  // Legajo completo: Recorrido de Muestra + documentos adjuntos reales
  // seleccionables (ver GET /{id}/legajo-pdf) -- las 3 casillas van
  // tildadas por defecto, tal como lo pide el ticket.
  const [modalLegajoAbierto, setModalLegajoAbierto] = useState(false);
  const [incluirProtocoloProveedor, setIncluirProtocoloProveedor] = useState(true);
  const [incluirProtocoloLaboratorio, setIncluirProtocoloLaboratorio] = useState(true);
  const [incluirDocumentacionProveedor, setIncluirDocumentacionProveedor] = useState(true);
  const [generandoLegajo, setGenerandoLegajo] = useState(false);
  const [errorLegajo, setErrorLegajo] = useState('');

  function abrirModalLegajo() {
    setIncluirProtocoloProveedor(true);
    setIncluirProtocoloLaboratorio(true);
    setIncluirDocumentacionProveedor(true);
    setErrorLegajo('');
    setModalLegajoAbierto(true);
  }

  async function generarLegajo() {
    setGenerandoLegajo(true);
    setErrorLegajo('');
    try {
      const params = new URLSearchParams();
      params.set('protocolo_proveedor', incluirProtocoloProveedor);
      params.set('protocolo_laboratorio', incluirProtocoloLaboratorio);
      params.set('documentacion_proveedor', incluirDocumentacionProveedor);
      await abrirPdfConAuth(`/api/muestras/${id}/legajo-pdf?${params.toString()}`);
      setModalLegajoAbierto(false);
    } catch (err) {
      setErrorLegajo(err instanceof ApiError ? err.message : 'No se pudo generar el legajo completo');
    } finally {
      setGenerandoLegajo(false);
    }
  }

  useEffect(() => {
    muestrasApi
      .obtenerRecorrido(id)
      .then(setRecorrido)
      .catch((err) => setError(err instanceof ApiError ? err.message : 'No se pudo cargar el recorrido de la muestra'));
  }, [id]);

  useEffect(() => {
    muestrasApi
      .obtenerUltimaEtiqueta(id)
      .then(() => setTieneEtiqueta(true))
      .catch(() => setTieneEtiqueta(false));
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

  // Proveedor es un dato de la muestra -- se muestra UNA sola vez, en
  // Identificación, nunca por envío. s.proveedor_* (de la solicitud) es más
  // completo (código + nombre) que recorrido.erp_proveedor (solo nombre,
  // copiado a la muestra al confirmar el muestreo); se prioriza el primero
  // cuando hay solicitud vinculada.
  const proveedorTexto = s?.proveedor_nombre
    ? (s.proveedor_codigo ? `${s.proveedor_codigo} - ${s.proveedor_nombre}` : s.proveedor_nombre)
    : recorrido.erp_proveedor;

  // Bloque "Datos del Contenedor": solo lo físico del contenedor en sí.
  const datosContenedor = s
    ? [
        ['Identificación de contenedor', s.datos_fisicos.identificacion_contenedor],
        ['Aspecto externo', s.datos_fisicos.aspecto_externo],
        ['Cierre', s.datos_fisicos.cierre],
        ['Aspecto interno', s.datos_fisicos.aspecto_interno],
        ['Precintos', s.datos_fisicos.precintos],
        ['N° de bultos muestreados', s.datos_fisicos.nro_bultos_muestreados],
      ].filter(([, valor]) => valor !== null && valor !== undefined && valor !== '')
    : [];

  // Bloque "Aspecto de la Materia Prima": aspecto/olor/color observados +
  // vencimiento real confirmado durante el muestreo (distinto del
  // vencimiento "de catálogo" que ya se muestra en Identificación).
  const aspectoMateriaPrima = s
    ? [
        ['Aspecto de la MP', s.datos_fisicos.aspecto_mp],
        ['Materias extrañas', s.datos_fisicos.materias_extranas],
        ['Olor', s.datos_fisicos.olor],
        ['Color', s.datos_fisicos.color],
        ['Fecha de vencimiento real', formatFechaSimple(s.datos_fisicos.fecha_vencimiento_real)],
        ['Fecha de reanálisis real', formatFechaSimple(s.datos_fisicos.fecha_reanalisis_real)],
      ].filter(([, valor]) => valor !== null && valor !== undefined && valor !== '')
    : [];

  return (
    <div className="screen">
      <TopBar titulo={recorrido.codigo_muestra} subtitulo="Consulta de Muestras" onBack={() => navigate(-1)} />
      <div className="screen-content">
        <div style={{ display: 'flex', gap: 'var(--sp-3)', marginBottom: 'var(--sp-4)' }}>
          <button className="btn btn-primary no-print" onClick={() => window.print()}>
            Ver recorrido →
          </button>
          <button className="btn btn-secondary no-print" onClick={abrirModalLegajo}>
            Legajo completo →
          </button>
          <button className="btn btn-secondary no-print" onClick={() => navigate(`/muestras/${id}/etiqueta`)}>
            {tieneEtiqueta ? 'Reimprimir etiqueta' : 'Imprimir etiqueta'}
          </button>
          <button className="btn btn-ghost no-print" onClick={() => navigate(-1)}>
            Volver
          </button>
        </div>

        {modalLegajoAbierto && (
          <div
            className="no-print"
            style={{
              position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.5)',
              display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 100, padding: 'var(--sp-4)',
            }}
            onClick={() => !generandoLegajo && setModalLegajoAbierto(false)}
          >
            <div
              className="card"
              style={{ width: '90%', maxWidth: 480, maxHeight: '90vh', overflowY: 'auto' }}
              onClick={(e) => e.stopPropagation()}
            >
              <h2 style={{ fontSize: 'var(--fs-lg)', marginBottom: 'var(--sp-2)' }}>Legajo completo</h2>
              <p style={{ color: 'var(--ink-2)', fontSize: 'var(--fs-sm)', marginBottom: 'var(--sp-4)' }}>
                El Recorrido de Muestra siempre se incluye. Elegí qué documentos adjuntos sumar en un solo PDF.
              </p>

              <label style={{ display: 'flex', alignItems: 'center', gap: 'var(--sp-2)', marginBottom: 'var(--sp-3)', cursor: 'pointer' }}>
                <input
                  type="checkbox"
                  checked={incluirProtocoloProveedor}
                  onChange={(e) => setIncluirProtocoloProveedor(e.target.checked)}
                  disabled={generandoLegajo}
                />
                Protocolo del proveedor
              </label>
              <label style={{ display: 'flex', alignItems: 'center', gap: 'var(--sp-2)', marginBottom: 'var(--sp-3)', cursor: 'pointer' }}>
                <input
                  type="checkbox"
                  checked={incluirProtocoloLaboratorio}
                  onChange={(e) => setIncluirProtocoloLaboratorio(e.target.checked)}
                  disabled={generandoLegajo}
                />
                Protocolo del laboratorio externo
              </label>
              <label style={{ display: 'flex', alignItems: 'center', gap: 'var(--sp-2)', marginBottom: 'var(--sp-4)', cursor: 'pointer' }}>
                <input
                  type="checkbox"
                  checked={incluirDocumentacionProveedor}
                  onChange={(e) => setIncluirDocumentacionProveedor(e.target.checked)}
                  disabled={generandoLegajo}
                />
                Factura/remito del proveedor
              </label>

              {errorLegajo && <div className="alert alert-danger" style={{ marginBottom: 'var(--sp-3)' }}>{errorLegajo}</div>}

              <div style={{ display: 'flex', gap: 'var(--sp-3)' }}>
                <button type="button" className="btn btn-ghost" onClick={() => setModalLegajoAbierto(false)} disabled={generandoLegajo}>
                  Cancelar
                </button>
                <button type="button" className="btn btn-primary" onClick={generarLegajo} disabled={generandoLegajo}>
                  {generandoLegajo ? <span className="spinner" /> : 'Generar PDF →'}
                </button>
              </div>
            </div>
          </div>
        )}

        <div className="printable">
          {/* Encabezado liviano -- no es uno de los bloques del reporte, solo
              título y estado; los datos en sí van en Identificación. */}
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 'var(--sp-2)' }}>
            <h1 style={{ fontSize: 'var(--fs-xl)' }}>{recorrido.erp_DESART}</h1>
            <div style={{ display: 'flex', gap: 4 }}>
              <span className={`badge ${BADGE_POR_ESTADO[recorrido.estado] || 'badge-neutral'}`}>
                {recorrido.estado.replace(/_/g, ' ')}
              </span>
              {recorrido.datos_muestreo_pendientes && (
                <span className="badge badge-warn" title="El envío se generó por adelantado -- todavía falta completar el registro físico del muestreo">
                  Datos de muestreo pendientes
                </span>
              )}
            </div>
          </div>

          {/* 1. Solicitud de Muestreo */}
          <Seccion titulo="Solicitud de Muestreo">
            <table className="data-table data-table-compact">
              <tbody>
                {s && <tr><td>N° Solicitud</td><td style={{ textAlign: 'left' }}>{s.nro_solicitud}</td></tr>}
                {s && <tr><td>Generada por</td><td style={{ textAlign: 'left' }}>{s.usuario_qa_nombre}</td></tr>}
                {s && <tr><td>Fecha de solicitud</td><td style={{ textAlign: 'left' }}>{new Date(s.fecha_solicitud).toLocaleString()}</td></tr>}
                <tr><td>Muestreador</td><td style={{ textAlign: 'left' }}>{recorrido.usuario_muestreo_nombre}</td></tr>
                <tr><td>Fecha de muestreo</td><td style={{ textAlign: 'left' }}>{new Date(recorrido.fecha_muestreo).toLocaleString()}</td></tr>
              </tbody>
            </table>
          </Seccion>

          {/* 2. Identificación -- Proveedor aparece UNA sola vez acá, no se
              repite en Datos del Envío aunque haya varios envíos. La celda
              de N° de IR/Lote no tiene ancho fijo ni corte: se deja
              wordBreak para que un nro_referencia largo (ej. trazabilidad
              eBR) se vea completo en vez de recortarse. */}
          <Seccion titulo="Identificación">
            <table className="data-table data-table-compact">
              <tbody>
                <tr>
                  <td style={{ whiteSpace: 'nowrap' }}>{recorrido.tipo_referencia === 'ir' ? 'N° de IR' : 'N° de Lote'}</td>
                  <td style={{ textAlign: 'left', wordBreak: 'break-word' }}>{recorrido.nro_referencia}</td>
                </tr>
                <tr><td>Nombre</td><td style={{ textAlign: 'left' }}>{recorrido.erp_DESART}</td></tr>
                <tr><td>Código</td><td style={{ textAlign: 'left' }}>{recorrido.erp_CODART}</td></tr>
                <tr><td>Tipo de material</td><td style={{ textAlign: 'left' }}>{recorrido.tipo_material || '—'}</td></tr>
                {proveedorTexto && <tr><td>Proveedor</td><td style={{ textAlign: 'left' }}>{proveedorTexto}</td></tr>}
                {s?.lote_proveedor && <tr><td>Lote del proveedor</td><td style={{ textAlign: 'left' }}>{s.lote_proveedor}</td></tr>}
                {s?.fecha_vencimiento && <tr><td>Fecha de vencimiento</td><td style={{ textAlign: 'left' }}>{formatFechaSimple(s.fecha_vencimiento)}</td></tr>}
                {s?.fecha_reanalisis && <tr><td>Fecha de reanálisis</td><td style={{ textAlign: 'left' }}>{formatFechaSimple(s.fecha_reanalisis)}</td></tr>}
              </tbody>
            </table>
          </Seccion>

          {/* 3. Datos del Contenedor */}
          {datosContenedor.length > 0 && (
            <Seccion titulo="Datos del Contenedor">
              <table className="data-table data-table-compact">
                <tbody>
                  {datosContenedor.map(([label, valor]) => (
                    <tr key={label}><td>{label}</td><td style={{ textAlign: 'left' }}>{valor}</td></tr>
                  ))}
                </tbody>
              </table>
            </Seccion>
          )}

          {/* 3.5 Checklist de Muestreo: ítems configurables de etapa
              'muestreo' (ver lims_resultados_muestreo) -- sección propia,
              separada de las especificaciones de laboratorio (etapa
              'analisis', sección siguiente). Vacío en muestras muestreadas
              antes de este cambio o sin especificación con ítems de esta
              etapa, no se muestra el bloque. */}
          {recorrido.checklist_muestreo.length > 0 && (
            <Seccion titulo="Checklist de Muestreo">
              <table className="data-table data-table-compact">
                <thead>
                  <tr>
                    <th>Ítem</th>
                    <th>Resultado</th>
                  </tr>
                </thead>
                <tbody>
                  {recorrido.checklist_muestreo.map((it) => (
                    <tr key={it.id_espec_ensayo}>
                      <td>{it.nombre_ensayo}</td>
                      <td>{badgeCumple(it)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </Seccion>
          )}

          {/* 4. Aspecto de la Materia Prima: aspecto/olor/color observados +
              todas las especificaciones (ensayos) definidas para la
              solicitud, con su resultado interno + observaciones del
              muestreo -- todo lo que caracteriza la MP más allá del
              contenedor que la trae. */}
          {(aspectoMateriaPrima.length > 0 || s) && (
            <Seccion titulo="Aspecto de la Materia Prima">
              {aspectoMateriaPrima.length > 0 && (
                <table className="data-table data-table-compact" style={{ marginBottom: 'var(--sp-2)' }}>
                  <tbody>
                    {aspectoMateriaPrima.map(([label, valor]) => (
                      <tr key={label}><td>{label}</td><td style={{ textAlign: 'left' }}>{valor}</td></tr>
                    ))}
                  </tbody>
                </table>
              )}

              {s && (
                <>
                  <h3 style={{ fontSize: 'var(--fs-sm)', marginBottom: 'var(--sp-1)' }}>Especificaciones definidas</h3>
                  {recorrido.resultados_orden_trabajo.length === 0 ? (
                    <p style={{ color: 'var(--ink-2)', margin: 0 }}>Sin resultados internos cargados.</p>
                  ) : (
                    <table className="data-table data-table-compact" style={{ marginBottom: 'var(--sp-2)' }}>
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
                  {s.datos_fisicos.observaciones_muestreo && (
                    <p style={{ margin: 0 }}>
                      <strong>Observaciones: </strong>{s.datos_fisicos.observaciones_muestreo}
                    </p>
                  )}
                </>
              )}
            </Seccion>
          )}

          {/* 5. Datos del Envío -- se repite un bloque completo por cada
              envío (remito/laboratorio/fecha/ensayos/testigos son propios
              de CADA envío); el proveedor NO se repite acá, ya se mostró
              una sola vez en Identificación. */}
          {recorrido.envios.length === 0 ? (
            <div className="alert alert-info" style={{ marginBottom: 0 }}>Esta muestra todavía no tiene envíos registrados.</div>
          ) : (
            recorrido.envios.map((en) => (
              <Seccion key={en.id_envio} titulo={`Datos del Envío — N° ${en.nro_remito || en.id_envio} — ${en.laboratorio_nombre}`}>
                <table className="data-table data-table-compact" style={{ marginBottom: 'var(--sp-2)' }}>
                  <tbody>
                    <tr><td>Laboratorio</td><td style={{ textAlign: 'left' }}>{en.laboratorio_nombre}</td></tr>
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

                <table className="data-table data-table-compact">
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

          {/* 6. Dictamen Final */}
          <Seccion titulo="Dictamen Final">
            {recorrido.dictamen ? (
              <>
                <span className={`badge ${BADGE_DICTAMEN[recorrido.dictamen.estado_dictamen] || 'badge-neutral'}`} style={{ fontSize: 'var(--fs-base)', padding: 'var(--sp-1) var(--sp-3)', marginBottom: 'var(--sp-2)', display: 'inline-block' }}>
                  {recorrido.dictamen.estado_dictamen.toUpperCase()}
                </span>
                <table className="data-table data-table-compact">
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
              <p style={{ color: 'var(--ink-2)', margin: 0 }}>Pendiente de dictamen QA</p>
            )}
          </Seccion>
        </div>
      </div>
    </div>
  );
}
