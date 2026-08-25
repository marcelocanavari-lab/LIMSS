import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../../context/AuthContext';
import TopBar from '../../components/TopBar';
import { reportesApi } from '../../api/reportes';
import { ApiError, descargarArchivoConAuth } from '../../api/client';
import { ESTADOS, BADGE_POR_ESTADO } from '../muestras/MuestrasPage';

const LABEL_ESTADO = Object.fromEntries(ESTADOS.filter((e) => e.value).map((e) => [e.value, e.label]));

function formatFecha(iso) {
  if (!iso) return '';
  const [y, m, d] = iso.split('-');
  return `${d}/${m}/${y}`;
}

function formatFechaHora(iso) {
  if (!iso) return '';
  return new Date(iso).toLocaleString();
}

export default function LibroIngresosPage() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const autorizado = ['analista_qc', 'qa', 'admin'].includes(user?.rol);

  const [fechaDesde, setFechaDesde] = useState('');
  const [fechaHasta, setFechaHasta] = useState('');

  const [lineas, setLineas] = useState(null);
  const [fechaGeneracion, setFechaGeneracion] = useState(null);
  const [generando, setGenerando] = useState(false);
  const [exportando, setExportando] = useState(false);
  const [error, setError] = useState('');

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
        <div className="card no-print" style={{ marginBottom: 'var(--sp-5)' }}>
          <h2 style={{ fontSize: 'var(--fs-lg)', marginBottom: 'var(--sp-3)' }}>Filtros</h2>
          <p style={{ color: 'var(--ink-2)', marginBottom: 'var(--sp-3)' }}>
            Materia Prima y Material de Empaque solamente (con N° de análisis asignado). El filtro es por fecha de ingreso.
          </p>
          <div style={{ display: 'flex', gap: 'var(--sp-3)', flexWrap: 'wrap', marginBottom: 'var(--sp-4)' }}>
            <div className="field" style={{ flex: 1, minWidth: 160 }}>
              <label className="field-label" htmlFor="fechaDesde">Fecha desde</label>
              <input id="fechaDesde" className="field-input" type="date" value={fechaDesde} onChange={(e) => setFechaDesde(e.target.value)} />
            </div>
            <div className="field" style={{ flex: 1, minWidth: 160 }}>
              <label className="field-label" htmlFor="fechaHasta">Fecha hasta</label>
              <input id="fechaHasta" className="field-input" type="date" value={fechaHasta} onChange={(e) => setFechaHasta(e.target.value)} />
            </div>
          </div>

          <button className="btn btn-primary" onClick={generarReporte} disabled={generando}>
            {generando ? <span className="spinner" /> : 'Generar reporte →'}
          </button>
        </div>

        {error && <div className="alert alert-danger no-print" style={{ marginBottom: 'var(--sp-4)' }}>{error}</div>}

        {lineas && (
          <div className="printable">
            <div className="no-print" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 'var(--sp-4)', flexWrap: 'wrap', gap: 'var(--sp-2)' }}>
              <span>{lineas.length} línea{lineas.length === 1 ? '' : 's'}</span>
              <div style={{ display: 'flex', gap: 'var(--sp-2)' }}>
                <button className="btn btn-secondary" onClick={exportarCsv} disabled={exportando}>
                  {exportando ? <span className="spinner" /> : 'Exportar Excel (CSV)'}
                </button>
                <button className="btn btn-secondary" onClick={() => window.print()}>Imprimir / Exportar PDF</button>
              </div>
            </div>

            <h1 style={{ fontSize: 'var(--fs-lg)', marginBottom: 'var(--sp-2)' }}>Libro de Ingresos</h1>
            <p style={{ color: 'var(--ink-2)', marginBottom: 'var(--sp-4)' }}>
              Generado el {fechaGeneracion?.toLocaleString()} por {user?.nombre} {user?.apellido} ({user?.codigo}) —{' '}
              {lineas.length} registro{lineas.length === 1 ? '' : 's'}
            </p>

            {lineas.length === 0 ? (
              <div className="state-block"><span>No hay ingresos numerados en el rango elegido</span></div>
            ) : (
              <div className="table-scroll">
                <table className="data-table data-table-compact">
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
          </div>
        )}
      </div>
    </div>
  );
}
