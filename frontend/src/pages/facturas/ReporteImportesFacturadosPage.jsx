import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../../context/AuthContext';
import TopBar from '../../components/TopBar';
import { facturasApi } from '../../api/facturas';
import { muestrasApi } from '../../api/muestras';
import { maestrosApi } from '../../api/maestros';
import { ApiError } from '../../api/client';

function formatFecha(iso) {
  if (!iso) return '—';
  const [y, m, d] = iso.split('-');
  return `${d}/${m}/${y}`;
}

export default function ReporteImportesFacturadosPage() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const autorizado = ['analista_qc', 'qa', 'admin'].includes(user?.rol);

  const [laboratorios, setLaboratorios] = useState([]);
  const [ensayosMaestro, setEnsayosMaestro] = useState([]);
  const [idLaboratorio, setIdLaboratorio] = useState('');
  const [fechaDesde, setFechaDesde] = useState('');
  const [fechaHasta, setFechaHasta] = useState('');
  const [nombreEnsayo, setNombreEnsayo] = useState('');

  const [resultado, setResultado] = useState(null);
  const [fechaGeneracion, setFechaGeneracion] = useState(null);
  const [generando, setGenerando] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    if (!autorizado) return;
    muestrasApi.listarLaboratorios(true).then(setLaboratorios).catch(() => {});
    maestrosApi.listarEnsayosMaestro().then(setEnsayosMaestro).catch(() => {});
  }, [autorizado]);

  async function generarReporte() {
    setError('');
    setGenerando(true);
    try {
      const data = await facturasApi.reporteImportesFacturados({
        idLaboratorio: idLaboratorio || undefined,
        fechaDesde: fechaDesde || undefined,
        fechaHasta: fechaHasta || undefined,
        nombreEnsayo: nombreEnsayo || undefined,
      });
      setResultado(data);
      setFechaGeneracion(new Date());
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'No se pudo generar el reporte');
    } finally {
      setGenerando(false);
    }
  }

  if (!autorizado) {
    return (
      <div className="screen">
        <TopBar titulo="Importes Facturados" subtitulo="Facturación de Laboratorios" onBack={() => navigate(-1)} />
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
      <TopBar titulo="Reporte de Importes Facturados" subtitulo="Facturación de Laboratorios" onBack={() => navigate(-1)} />
      <div className="screen-content">
        <div className="card no-print" style={{ marginBottom: 'var(--sp-5)' }}>
          <h2 style={{ fontSize: 'var(--fs-lg)', marginBottom: 'var(--sp-3)' }}>Filtros</h2>
          <div style={{ display: 'flex', gap: 'var(--sp-3)', flexWrap: 'wrap', marginBottom: 'var(--sp-4)' }}>
            <div className="field" style={{ flex: 1, minWidth: 180 }}>
              <label className="field-label" htmlFor="idLaboratorio">Laboratorio</label>
              <select id="idLaboratorio" className="field-input" value={idLaboratorio} onChange={(e) => setIdLaboratorio(e.target.value)}>
                <option value="">Todos</option>
                {laboratorios.map((l) => (
                  <option key={l.id_laboratorio} value={l.id_laboratorio}>{l.nombre}</option>
                ))}
              </select>
            </div>

            <div className="field" style={{ flex: 1, minWidth: 160 }}>
              <label className="field-label" htmlFor="fechaDesde">Fecha desde</label>
              <input id="fechaDesde" className="field-input" type="date" value={fechaDesde} onChange={(e) => setFechaDesde(e.target.value)} />
            </div>

            <div className="field" style={{ flex: 1, minWidth: 160 }}>
              <label className="field-label" htmlFor="fechaHasta">Fecha hasta</label>
              <input id="fechaHasta" className="field-input" type="date" value={fechaHasta} onChange={(e) => setFechaHasta(e.target.value)} />
            </div>

            <div className="field" style={{ flex: 1, minWidth: 180 }}>
              <label className="field-label" htmlFor="nombreEnsayo">Ensayo</label>
              <select id="nombreEnsayo" className="field-input" value={nombreEnsayo} onChange={(e) => setNombreEnsayo(e.target.value)}>
                <option value="">Todos</option>
                {ensayosMaestro.map((em) => (
                  <option key={em.id_ensayo_maestro} value={em.nombre_ensayo}>{em.nombre_ensayo}</option>
                ))}
              </select>
            </div>
          </div>

          <button className="btn btn-primary" onClick={generarReporte} disabled={generando}>
            {generando ? <span className="spinner" /> : 'Generar reporte →'}
          </button>
        </div>

        {error && <div className="alert alert-danger no-print" style={{ marginBottom: 'var(--sp-4)' }}>{error}</div>}

        {resultado && (
          <div className="printable">
            <div className="no-print" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 'var(--sp-4)' }}>
              <span>{resultado.lineas.length} línea{resultado.lineas.length === 1 ? '' : 's'}</span>
              <button className="btn btn-secondary" onClick={() => window.print()}>Imprimir / Exportar PDF</button>
            </div>

            <h1 style={{ fontSize: 'var(--fs-lg)', marginBottom: 'var(--sp-2)' }}>Reporte de Importes Facturados</h1>
            <p style={{ color: 'var(--ink-2)', marginBottom: 'var(--sp-4)' }}>
              Generado el {fechaGeneracion?.toLocaleString()} por {user?.nombre} {user?.apellido} ({user?.codigo}) —{' '}
              {resultado.lineas.length} registro{resultado.lineas.length === 1 ? '' : 's'}
            </p>

            {resultado.lineas.length === 0 ? (
              <div className="state-block"><span className="state-block-title">Sin resultados</span></div>
            ) : (
              <>
                <div className="table-scroll">
                  <table className="data-table">
                    <thead>
                      <tr>
                        <th>N° Factura</th>
                        <th>Fecha</th>
                        <th>Laboratorio</th>
                        <th>N° Remito</th>
                        <th>Ensayo</th>
                        <th>Importe</th>
                      </tr>
                    </thead>
                    <tbody>
                      {resultado.lineas.map((l, i) => (
                        <tr key={i}>
                          <td style={{ fontFamily: 'var(--font-mono)' }}>{l.nro_factura}</td>
                          <td style={{ whiteSpace: 'nowrap' }}>{formatFecha(l.fecha_factura)}</td>
                          <td>{l.laboratorio_nombre}</td>
                          <td style={{ fontFamily: 'var(--font-mono)' }}>{l.nro_remito || '—'}</td>
                          <td>{l.analito ? `${l.nombre_ensayo} — ${l.analito}` : l.nombre_ensayo}</td>
                          <td className="num">{l.moneda} {Number(l.importe).toFixed(2)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>

                <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: 4, marginTop: 'var(--sp-4)' }}>
                  {resultado.totales_por_moneda.map((t) => (
                    <div key={t.moneda} style={{ fontSize: 'var(--fs-base)' }}>
                      <span style={{ color: 'var(--ink-2)' }}>Total {t.moneda}: </span>
                      <strong>{t.moneda} {t.total.toFixed(2)}</strong>
                    </div>
                  ))}
                </div>
              </>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
