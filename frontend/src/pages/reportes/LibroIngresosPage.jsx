import { Fragment, useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../../context/AuthContext';
import TopBar from '../../components/TopBar';
import { reportesApi } from '../../api/reportes';
import { ApiError, descargarArchivoConAuth } from '../../api/client';
import { ESTADOS, BADGE_POR_ESTADO } from '../muestras/MuestrasPage';

const LABEL_ESTADO = Object.fromEntries(ESTADOS.filter((e) => e.value).map((e) => [e.value, e.label]));

function hoyISO() {
  return new Date().toISOString().slice(0, 10);
}

function hace30DiasISO() {
  const d = new Date();
  d.setDate(d.getDate() - 30);
  return d.toISOString().slice(0, 10);
}

function formatFecha(iso) {
  if (!iso) return '';
  const [y, m, d] = iso.split('-');
  return `${d}/${m}/${y}`;
}

function formatFechaHora(iso) {
  if (!iso) return '';
  return new Date(iso).toLocaleString();
}

function labelEstado(l) {
  return l.estado_muestra ? (LABEL_ESTADO[l.estado_muestra] || l.estado_muestra) : '';
}

export default function LibroIngresosPage() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const autorizado = ['analista_qc', 'qa', 'admin'].includes(user?.rol);

  const [fechaDesde, setFechaDesde] = useState(hace30DiasISO());
  const [fechaHasta, setFechaHasta] = useState(hoyISO());

  const [lineas, setLineas] = useState(null);
  const [fechaGeneracion, setFechaGeneracion] = useState(null);
  const [generando, setGenerando] = useState(false);
  const [exportando, setExportando] = useState(false);
  const [error, setError] = useState('');

  // 17 columnas -- Oficio horizontal (330mm x 216mm, más ancho que A4
  // landscape) para dar más espacio real a las columnas. @page no se puede
  // condicionar con una clase/selector (es una regla de contexto de
  // impresión, no de un elemento) -- se inyecta un <style> propio mientras
  // esta pantalla está montada, así que solo afecta esta impresión y no el
  // resto de los reportes (que sí quieren A4 portrait).
  //
  // El margin se declara explícito (en vez de dejarlo "sin especificar"):
  // en cuanto una página define su propia regla @page, el navegador deja de
  // respetar la opción "Márgenes: Ninguno/Mínimo" del diálogo de impresión
  // para esa página y cae al margen por defecto del user-agent (bastante
  // más ancho que esto) -- así que el margen real hay que fijarlo acá.
  useEffect(() => {
    const style = document.createElement('style');
    style.textContent = '@media print { @page { size: 330mm 216mm; margin: 10mm; } }';
    document.head.appendChild(style);
    return () => { document.head.removeChild(style); };
  }, []);

  async function generarReporte() {
    setError('');
    setGenerando(true);
    try {
      const data = await reportesApi.libroIngresos({ fechaDesde: fechaDesde || undefined, fechaHasta: fechaHasta || undefined });
      setLineas(data);
      setFechaGeneracion(new Date());
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'No se pudo generar el reporte');
    } finally {
      setGenerando(false);
    }
  }

  // Carga automática al entrar a la pantalla, con el rango por defecto (30
  // días) -- cualquier cambio posterior de fechas requiere click en
  // "Generar reporte" (mismo criterio en todo el sistema, ver
  // GraficoTendenciaPage.jsx).
  useEffect(() => {
    if (!autorizado) return;
    generarReporte();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [autorizado]);

  async function exportarCsv() {
    setError('');
    setExportando(true);
    try {
      const path = reportesApi.libroIngresosExportarPath({ fechaDesde: fechaDesde || undefined, fechaHasta: fechaHasta || undefined });
      await descargarArchivoConAuth(path, 'libro_ingresos.csv');
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'No se pudo exportar el reporte');
    } finally {
      setExportando(false);
    }
  }

  if (!autorizado) {
    return (
      <div className="screen">
        <TopBar titulo="Libro de Ingresos" subtitulo="Reportes" onBack={() => navigate(-1)} />
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
      <TopBar titulo="Libro de Ingresos" subtitulo="Reportes" onBack={() => navigate(-1)} />
      <div className="screen-content">
        {/* Filtros -- estilo plano en línea, igual que Consulta de Muestras /
            Cajas (sin .card "Filtros"), no el bloque tipo reporte de antes. */}
        <div className="no-print" style={{ display: 'flex', gap: 'var(--sp-3)', marginBottom: 'var(--sp-4)', flexWrap: 'wrap', alignItems: 'flex-end' }}>
          <div className="field" style={{ maxWidth: 170 }}>
            <label className="field-label" htmlFor="fechaDesde">Fecha desde</label>
            <input id="fechaDesde" className="field-input" type="date" value={fechaDesde} onChange={(e) => setFechaDesde(e.target.value)} />
          </div>
          <div className="field" style={{ maxWidth: 170 }}>
            <label className="field-label" htmlFor="fechaHasta">Fecha hasta</label>
            <input id="fechaHasta" className="field-input" type="date" value={fechaHasta} onChange={(e) => setFechaHasta(e.target.value)} />
          </div>
          <button className="btn btn-primary" onClick={generarReporte} disabled={generando}>
            {generando ? <span className="spinner" /> : 'Generar reporte →'}
          </button>
          {lineas && (
            <>
              <button className="btn btn-secondary" onClick={exportarCsv} disabled={exportando}>
                {exportando ? <span className="spinner" /> : 'Exportar Excel (CSV)'}
              </button>
              <button className="btn btn-secondary" onClick={() => window.print()}>Imprimir / Exportar PDF</button>
            </>
          )}
        </div>
        <p className="no-print" style={{ color: 'var(--ink-2)', marginBottom: 'var(--sp-4)', fontSize: 'var(--fs-sm)' }}>
          Materia Prima y Material de Empaque solamente (con N° de análisis asignado). El filtro es por fecha de ingreso.
        </p>

        {error && <div className="alert alert-danger no-print" style={{ marginBottom: 'var(--sp-4)' }}>{error}</div>}

        {lineas && (
          <>
            {/* Vista interactiva (pantalla) -- mismo look & feel que Consulta
                de Muestras/Cajas: tabla normal, sin el estilo denso de
                reporte. Scroll horizontal propio (reporte-tabla-scroll +
                libro-ingresos-tabla) porque 17 columnas no entran en el
                ancho de pantalla, pero la densidad/tipografía es la misma
                que el resto de las tablas interactivas del sistema. */}
            {lineas.length === 0 ? (
              <div className="no-print state-block"><span>No hay ingresos numerados en el rango elegido</span></div>
            ) : (
              <div className="no-print reporte-tabla-scroll libro-ingresos-scroll">
                <table className="data-table libro-ingresos-tabla">
                  <thead>
                    <tr>
                      <th>N° análisis</th>
                      <th>Fecha de ingreso</th>
                      <th>N° de IR</th>
                      <th>Fecha de vencimiento</th>
                      <th>Código</th>
                      <th>Descripción</th>
                      <th>Proveedor</th>
                      <th>Fecha de factura</th>
                      <th>N° de factura</th>
                      <th>Lote del proveedor</th>
                      <th>Peso/cantidad</th>
                      <th>Bultos</th>
                      <th>Recibió</th>
                      <th>Rotuló</th>
                      <th>Observaciones / Estado</th>
                      <th>Muestreador</th>
                      <th>Fecha de muestreo</th>
                    </tr>
                  </thead>
                  <tbody>
                    {lineas.map((l) => (
                      <tr key={l.numero_analisis}>
                        <td className="num">{l.numero_analisis}</td>
                        <td>{formatFecha(l.fecha_ingreso)}</td>
                        <td style={{ fontFamily: 'var(--font-mono)' }}>{l.nro_ir || '—'}</td>
                        <td>{formatFecha(l.fecha_vencimiento)}</td>
                        <td>{l.erp_codart || '—'}</td>
                        <td>{l.erp_desart || '—'}</td>
                        <td>{l.proveedor_nombre || '—'}</td>
                        <td>{formatFecha(l.fecha_factura_proveedor)}</td>
                        <td>{l.numero_factura_proveedor || '—'}</td>
                        <td>{l.lote_proveedor}</td>
                        <td>{l.cantidad_texto || '—'}</td>
                        <td>{l.bultos_detalle || '—'}</td>
                        <td>{l.usuario_recibio || '—'}</td>
                        <td>{l.usuario_rotulo || '—'}</td>
                        <td>
                          {l.estado_muestra && (
                            <span className={`badge ${BADGE_POR_ESTADO[l.estado_muestra] || 'badge-neutral'}`}>
                              {LABEL_ESTADO[l.estado_muestra] || l.estado_muestra}
                            </span>
                          )}
                          {l.observaciones && (
                            <div style={{ marginTop: l.estado_muestra ? 4 : 0 }}>{l.observaciones}</div>
                          )}
                        </td>
                        <td>{l.usuario_muestreador || '—'}</td>
                        <td>{formatFechaHora(l.fecha_muestreo)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}

            {/* Vista de impresión -- oculta en pantalla (print-only). Dos
                renglones por muestra: el primero con los 9 datos de
                identificación (con encabezado de columna real), el segundo
                -- indentado, letra más chica -- con los 8 datos operativos
                en una sola línea corrida. Así entran las 17 columnas en una
                página landscape sin tener que achicar tanto la fuente que
                quede ilegible. Línea separadora entre cada par (una muestra
                completa) y el siguiente. */}
            <div className="printable print-only libro-ingresos-print">
              <h1 style={{ fontSize: 'var(--fs-lg)', marginBottom: 'var(--sp-2)' }}>Libro de Ingresos</h1>
              <p style={{ color: 'var(--ink-2)', marginBottom: 'var(--sp-4)' }}>
                Generado el {fechaGeneracion?.toLocaleString()} por {user?.nombre} {user?.apellido} ({user?.codigo}) —{' '}
                {lineas.length} registro{lineas.length === 1 ? '' : 's'}
              </p>

              {lineas.length > 0 && (
                <table className="libro-ingresos-print-tabla">
                  <thead>
                    <tr>
                      <th>N° análisis</th>
                      <th>Fecha de Ingreso</th>
                      <th>N° de IR</th>
                      <th>Fecha de vencimiento</th>
                      <th>Código</th>
                      <th>Descripción</th>
                      <th>Proveedor</th>
                      <th>Fecha de factura</th>
                      <th>N° de factura</th>
                    </tr>
                  </thead>
                  <tbody>
                    {lineas.map((l) => (
                      <Fragment key={l.numero_analisis}>
                        <tr className="libro-ingresos-print-fila1">
                          <td>{l.numero_analisis}</td>
                          <td>{formatFecha(l.fecha_ingreso)}</td>
                          <td>{l.nro_ir || '—'}</td>
                          <td>{formatFecha(l.fecha_vencimiento)}</td>
                          <td>{l.erp_codart || '—'}</td>
                          <td>{l.erp_desart || '—'}</td>
                          <td>{l.proveedor_nombre || '—'}</td>
                          <td>{formatFecha(l.fecha_factura_proveedor)}</td>
                          <td>{l.numero_factura_proveedor || '—'}</td>
                        </tr>
                        <tr className="libro-ingresos-print-fila2">
                          <td colSpan={9}>
                            <span><b>Lote:</b> {l.lote_proveedor}</span>
                            <span><b>Peso/cantidad:</b> {l.cantidad_texto || '—'}</span>
                            <span><b>Bultos:</b> {l.bultos_detalle || '—'}</span>
                            <span><b>Recibió:</b> {l.usuario_recibio || '—'}</span>
                            <span><b>Rotuló:</b> {l.usuario_rotulo || '—'}</span>
                            <span><b>Obs/Estado:</b> {[labelEstado(l), l.observaciones].filter(Boolean).join(' — ') || '—'}</span>
                            <span><b>Muestreador:</b> {l.usuario_muestreador || '—'}</span>
                            <span><b>F. muestreo:</b> {formatFechaHora(l.fecha_muestreo)}</span>
                          </td>
                        </tr>
                      </Fragment>
                    ))}
                  </tbody>
                </table>
              )}
            </div>
          </>
        )}
      </div>
    </div>
  );
}
