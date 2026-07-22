import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../../context/AuthContext';
import TopBar from '../../components/TopBar';
import { maestrosApi } from '../../api/maestros';
import { ApiError } from '../../api/client';

const ESTADOS = [
  { value: '', label: 'Todos' },
  { value: 'normal', label: 'Normal' },
  { value: 'por_vencer', label: 'Por vencer' },
  { value: 'vencido', label: 'Vencido' },
  { value: 'sin_vencimiento', label: 'Sin vencimiento' },
];

const ORDENES = [
  { value: '', label: 'Sin ordenar' },
  { value: 'vencimiento_asc', label: 'Vencimiento (más próximo primero)' },
  { value: 'vencimiento_desc', label: 'Vencimiento (más lejano primero)' },
  { value: 'nombre_asc', label: 'Nombre (A-Z)' },
  { value: 'codigo_asc', label: 'Código (A-Z)' },
  { value: 'stock_asc', label: 'Stock (menor primero)' },
  { value: 'ir_asc', label: 'N° IR (ASC)' },
];

function formatFecha(iso) {
  if (!iso) return '—';
  const [y, m, d] = iso.split('-');
  return `${d}/${m}/${y}`;
}

function hoyISO() {
  const hoy = new Date();
  const mes = String(hoy.getMonth() + 1).padStart(2, '0');
  const dia = String(hoy.getDate()).padStart(2, '0');
  return `${hoy.getFullYear()}-${mes}-${dia}`;
}

function labelEstado(t) {
  if (t.vencido) return 'Vencido';
  if (t.por_vencer) return 'Por vencer';
  if (!t.fecha_vencimiento) return 'Sin vencimiento';
  return 'Normal';
}

export default function ReporteTestigosPage() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const autorizado = ['qa', 'admin'].includes(user?.rol);

  const [estado, setEstado] = useState('');
  const [stockBajo, setStockBajo] = useState(false);
  const [orden, setOrden] = useState('');
  const [fechaRef, setFechaRef] = useState(hoyISO());
  const [resultados, setResultados] = useState(null);
  const [fechaGeneracion, setFechaGeneracion] = useState(null);
  const [fechaRefUsada, setFechaRefUsada] = useState(null);
  const [generando, setGenerando] = useState(false);
  const [error, setError] = useState('');

  async function generarReporte() {
    setError('');
    setGenerando(true);
    try {
      const data = await maestrosApi.listarTestigos({
        estado: estado || undefined,
        stockBajo: stockBajo || undefined,
        orden: orden || undefined,
        fechaRef: fechaRef || undefined,
      });
      setResultados(data);
      setFechaGeneracion(new Date());
      setFechaRefUsada(fechaRef);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'No se pudo generar el reporte');
    } finally {
      setGenerando(false);
    }
  }

  if (!autorizado) {
    return (
      <div className="screen">
        <TopBar titulo="Reporte de Testigos" subtitulo="Datos Maestros" onBack={() => navigate('/maestros/testigos')} />
        <div className="screen-content">
          <div className="state-block">
            <span className="state-block-title">Acceso restringido</span>
            <span>Esta pantalla es solo para roles QA y Admin</span>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="screen">
      <TopBar titulo="Reporte de Testigos" subtitulo="Datos Maestros" onBack={() => navigate('/maestros/testigos')} />
      <div className="screen-content">
        <div className="card no-print" style={{ marginBottom: 'var(--sp-5)' }}>
          <h2 style={{ fontSize: 'var(--fs-lg)', marginBottom: 'var(--sp-3)' }}>Filtros</h2>
          <div style={{ display: 'flex', gap: 'var(--sp-3)', flexWrap: 'wrap', marginBottom: 'var(--sp-3)' }}>
            <div className="field" style={{ flex: 1, minWidth: 180 }}>
              <label className="field-label" htmlFor="fechaRef">Fecha de referencia</label>
              <input
                id="fechaRef"
                className="field-input"
                type="date"
                value={fechaRef}
                onChange={(e) => setFechaRef(e.target.value)}
              />
            </div>

            <div className="field" style={{ flex: 1, minWidth: 180 }}>
              <label className="field-label" htmlFor="estado">Estado</label>
              <select id="estado" className="field-input" value={estado} onChange={(e) => setEstado(e.target.value)}>
                {ESTADOS.map((o) => (
                  <option key={o.value} value={o.value}>{o.label}</option>
                ))}
              </select>
            </div>

            <div className="field" style={{ flex: 1, minWidth: 180 }}>
              <label className="field-label" htmlFor="orden">Ordenar por</label>
              <select id="orden" className="field-input" value={orden} onChange={(e) => setOrden(e.target.value)}>
                {ORDENES.map((o) => (
                  <option key={o.value} value={o.value}>{o.label}</option>
                ))}
              </select>
            </div>
          </div>

          <label style={{ display: 'flex', alignItems: 'center', gap: 'var(--sp-2)', marginBottom: 'var(--sp-4)' }}>
            <input type="checkbox" checked={stockBajo} onChange={(e) => setStockBajo(e.target.checked)} />
            Solo stock bajo (stock actual ≤ stock mínimo)
          </label>

          <button className="btn btn-primary" onClick={generarReporte} disabled={generando}>
            {generando ? <span className="spinner" /> : 'Generar reporte →'}
          </button>
        </div>

        {error && <div className="alert alert-danger no-print" style={{ marginBottom: 'var(--sp-4)' }}>{error}</div>}

        {resultados && (
          <div className="printable">
            <div className="no-print" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 'var(--sp-4)' }}>
              <span>{resultados.length} testigo{resultados.length === 1 ? '' : 's'} encontrado{resultados.length === 1 ? '' : 's'}</span>
              <button className="btn btn-secondary" onClick={() => window.print()}>Imprimir / Exportar PDF</button>
            </div>

            <h1 style={{ fontSize: 'var(--fs-lg)', marginBottom: 'var(--sp-2)' }}>Reporte de Testigos</h1>
            <p style={{ color: 'var(--ink-2)', marginBottom: 'var(--sp-1)' }}>
              <b>Fecha de referencia:</b> {formatFecha(fechaRefUsada)}
            </p>
            <p style={{ color: 'var(--ink-2)', marginBottom: 'var(--sp-4)' }}>
              Generado el {fechaGeneracion?.toLocaleString()} por {user?.nombre} {user?.apellido} ({user?.codigo}) —{' '}
              {resultados.length} registro{resultados.length === 1 ? '' : 's'}
            </p>

            {resultados.length === 0 ? (
              <div className="state-block"><span className="state-block-title">Sin resultados</span></div>
            ) : (
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Código</th>
                    <th>Nombre</th>
                    <th>Lote</th>
                    <th>N° IR</th>
                    <th>Vencimiento</th>
                    <th>Stock</th>
                    <th>Unidad</th>
                    <th>Estado</th>
                    <th>Certificado</th>
                  </tr>
                </thead>
                <tbody>
                  {resultados.map((t) => (
                    <tr key={t.id_testigo}>
                      <td style={{ fontFamily: 'var(--font-mono)', whiteSpace: 'nowrap' }}>{t.codigo}</td>
                      <td>{t.nombre}</td>
                      <td>{t.nro_lote}</td>
                      <td style={{ whiteSpace: 'nowrap' }}>{t.nro_ir || '—'}</td>
                      <td className="num" style={{ whiteSpace: 'nowrap' }}>{formatFecha(t.fecha_vencimiento)}</td>
                      <td className="num">{t.stock_actual}</td>
                      <td>{t.unidad_medida || '—'}</td>
                      <td>{labelEstado(t)}</td>
                      <td>{t.pdf_certificado ? 'Sí' : 'No'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
