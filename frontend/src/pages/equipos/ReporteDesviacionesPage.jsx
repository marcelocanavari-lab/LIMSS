import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../../context/AuthContext';
import TopBar from '../../components/TopBar';
import { equiposApi } from '../../api/equipos';
import { ApiError, descargarArchivoConAuth } from '../../api/client';

function hoyISO() {
  return new Date().toISOString().slice(0, 10);
}

function hace30DiasISO() {
  const d = new Date();
  d.setDate(d.getDate() - 30);
  return d.toISOString().slice(0, 10);
}

function nombreVariable(v) {
  return v.grupo ? `${v.grupo} ${v.nombre}` : v.nombre;
}

function formatearLimite(li, ls) {
  if (li !== null && ls !== null) return `${li} - ${ls}`;
  if (li !== null) return `≥ ${li}`;
  if (ls !== null) return `≤ ${ls}`;
  return '—';
}

// Reporte de valores fuera de rango -- para revisión/auditoría: a
// diferencia del Historial (todas las lecturas, las 13 variables en
// columnas), acá cada FILA es UNA desviación puntual (lectura + variable
// que se salió del rango) -- una misma lectura con 3 valores fuera de
// rango genera 3 filas. Mismo criterio que exportar_desviaciones_csv en
// el backend (misma forma de datos en pantalla, CSV e impresión).
export default function ReporteDesviacionesPage() {
  const { user } = useAuth();
  const navigate = useNavigate();

  const [equipos, setEquipos] = useState([]);
  const [idEquipo, setIdEquipo] = useState('');
  const [variables, setVariables] = useState([]);
  const [idVariable, setIdVariable] = useState(''); // '' = todas
  const [fechaDesde, setFechaDesde] = useState(hace30DiasISO());
  const [fechaHasta, setFechaHasta] = useState(hoyISO());
  const [lecturas, setLecturas] = useState([]);
  const [fechaGeneracion, setFechaGeneracion] = useState(null);
  const [loading, setLoading] = useState(true);
  const [exportando, setExportando] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    equiposApi.listar().then((data) => {
      setEquipos(data);
      if (data.length >= 1) setIdEquipo((prev) => prev || String(data[0].id_equipo));
    }).catch(() => {});
  }, []);

  useEffect(() => {
    if (!idEquipo) {
      setVariables([]);
      return;
    }
    equiposApi.listarVariables(idEquipo).then((data) => {
      setVariables(data);
      // Si la variable elegida no pertenece al equipo nuevo, vuelve a "todas".
      setIdVariable((prev) => (data.some((v) => String(v.id_variable) === prev) ? prev : ''));
    }).catch(() => setVariables([]));
  }, [idEquipo]);

  // Carga las lecturas con el rango de fechas ACTUAL de los inputs -- se
  // llama automáticamente al cambiar de equipo (selección completa de un
  // <select>, sin riesgo de "valor a medio tipear"), y a demanda desde el
  // botón "Generar" para las fechas. Mismo fix y mismo criterio ya
  // aplicado en GraficoTendenciaPage.jsx/HistorialLecturasPage.jsx --
  // idVariable no está acá porque ya filtra 100% client-side sobre
  // `lecturas` (ver `filas` más abajo), nunca disparó una consulta nueva.
  function cargar() {
    if (!idEquipo) return;
    setLoading(true);
    setError('');
    equiposApi
      .listarLecturas({ idEquipo, fechaDesde: fechaDesde || undefined, fechaHasta: fechaHasta || undefined, soloFueraDeRango: true })
      .then((data) => {
        setLecturas(data);
        setFechaGeneracion(new Date());
      })
      .catch((err) => setError(err instanceof ApiError ? err.message : 'No se pudo cargar el reporte'))
      .finally(() => setLoading(false));
  }

  useEffect(cargar, [idEquipo]);

  async function exportarCsv() {
    setError('');
    setExportando(true);
    try {
      const path = equiposApi.exportarDesviacionesPath({
        idEquipo, fechaDesde: fechaDesde || undefined, fechaHasta: fechaHasta || undefined,
        idVariable: idVariable || undefined,
      });
      await descargarArchivoConAuth(path, 'desviaciones_equipo.csv');
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'No se pudo exportar el reporte');
    } finally {
      setExportando(false);
    }
  }

  const equipoElegido = equipos.find((eq) => String(eq.id_equipo) === idEquipo);
  const variableElegida = variables.find((v) => String(v.id_variable) === idVariable);

  // Una fila por desviación (lectura + variable puntual) -- mismo criterio
  // que el CSV del backend. Filtro por variable (opcional, "todas" por
  // defecto) client-side: los datos ya vienen con las 13 variables
  // mezcladas, no hace falta volver a pedirlos al backend para acotar la
  // vista a una sola.
  const filas = lecturas
    .flatMap((l) =>
      l.valores
        .filter((v) => v.fuera_de_rango)
        .map((v) => ({
          id: `${l.id_lectura}-${v.id_variable}`,
          fecha: l.fecha, hora: l.hora,
          variable: v, usuarioRealizo: l.usuario_realizo_nombre, usuarioVerifico: l.usuario_verifico_nombre,
        }))
    )
    .filter((f) => !idVariable || String(f.variable.id_variable) === idVariable);

  return (
    <div className="screen">
      <TopBar titulo="Reporte de Desviaciones" subtitulo="Equipos" onBack={() => navigate(-1)} />
      <div className="screen-content">
        <div className="no-print card" style={{ marginBottom: 'var(--sp-4)' }}>
          <div style={{ display: 'flex', gap: 'var(--sp-3)', flexWrap: 'wrap', alignItems: 'flex-end' }}>
            <div className="field" style={{ flex: '1 1 220px' }}>
              <label className="field-label" htmlFor="equipoFiltro">Equipo</label>
              <select id="equipoFiltro" className="field-input" value={idEquipo} onChange={(e) => setIdEquipo(e.target.value)}>
                {equipos.map((eq) => (
                  <option key={eq.id_equipo} value={eq.id_equipo}>{eq.nombre}</option>
                ))}
              </select>
            </div>
            <div className="field" style={{ flex: '1 1 220px' }}>
              <label className="field-label" htmlFor="variableFiltro">Variable</label>
              <select id="variableFiltro" className="field-input" value={idVariable} onChange={(e) => setIdVariable(e.target.value)}>
                <option value="">Todas</option>
                {variables.map((v) => (
                  <option key={v.id_variable} value={v.id_variable}>{nombreVariable(v)}</option>
                ))}
              </select>
            </div>
            <div className="field" style={{ flex: '1 1 160px' }}>
              <label className="field-label" htmlFor="desde">Desde</label>
              <input id="desde" className="field-input" type="date" value={fechaDesde} onChange={(e) => setFechaDesde(e.target.value)} />
            </div>
            <div className="field" style={{ flex: '1 1 160px' }}>
              <label className="field-label" htmlFor="hasta">Hasta</label>
              <input id="hasta" className="field-input" type="date" value={fechaHasta} onChange={(e) => setFechaHasta(e.target.value)} />
            </div>
            <button className="btn btn-primary" onClick={cargar} disabled={loading}>
              {loading ? <span className="spinner" /> : 'Generar →'}
            </button>
            {filas.length > 0 && (
              <>
                <button className="btn btn-secondary" onClick={exportarCsv} disabled={exportando}>
                  {exportando ? <span className="spinner" /> : 'Exportar Excel (CSV)'}
                </button>
                <button className="btn btn-secondary" onClick={() => window.print()}>Imprimir / Exportar PDF</button>
              </>
            )}
          </div>
        </div>

        {error && <div className="no-print alert alert-danger" style={{ marginBottom: 'var(--sp-4)' }}>{error}</div>}

        {loading ? (
          <div className="no-print state-block"><span className="spinner" /></div>
        ) : filas.length === 0 ? (
          <div className="no-print state-block">
            <span className="state-block-title">Sin desviaciones</span>
            <span>Ninguna lectura de este equipo tuvo valores fuera de rango en el período elegido</span>
          </div>
        ) : (
          <>
            <div className="no-print table-scroll">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Fecha</th>
                    <th>Hora</th>
                    <th>Variable</th>
                    <th>Valor</th>
                    <th>Rango aceptable</th>
                    <th>Realizó</th>
                    <th>Verificó</th>
                  </tr>
                </thead>
                <tbody>
                  {filas.map((f) => (
                    <tr key={f.id}>
                      <td style={{ whiteSpace: 'nowrap' }}>{new Date(f.fecha).toLocaleDateString()}</td>
                      <td style={{ whiteSpace: 'nowrap' }}>{f.hora}</td>
                      <td>{nombreVariable(f.variable)}</td>
                      <td className="num" style={{ color: 'var(--danger)', fontWeight: 600 }}>
                        {f.variable.valor}{f.variable.unidad_medida ? ` ${f.variable.unidad_medida}` : ''}
                      </td>
                      <td className="num">{formatearLimite(f.variable.limite_inferior, f.variable.limite_superior)}</td>
                      <td>{f.usuarioRealizo || '—'}</td>
                      <td>{f.usuarioVerifico || '—'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <div className="printable print-only equipos-print-ancho">
              <h1 style={{ fontSize: 'var(--fs-lg)', marginBottom: 'var(--sp-2)' }}>
                Reporte de Desviaciones -- {equipoElegido?.nombre}{variableElegida ? ` -- ${nombreVariable(variableElegida)}` : ''}
              </h1>
              <p style={{ color: 'var(--ink-2)', marginBottom: 'var(--sp-4)' }}>
                {fechaDesde || fechaHasta ? `Período: ${fechaDesde || '...'} a ${fechaHasta || '...'} -- ` : ''}
                Generado el {fechaGeneracion?.toLocaleString()} por {user?.nombre} {user?.apellido} ({user?.codigo}) —{' '}
                {filas.length} desviación{filas.length === 1 ? '' : 'es'}
              </p>
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Fecha</th>
                    <th>Hora</th>
                    <th>Variable</th>
                    <th>Valor</th>
                    <th>Rango aceptable</th>
                    <th>Realizó</th>
                    <th>Verificó</th>
                  </tr>
                </thead>
                <tbody>
                  {filas.map((f) => (
                    <tr key={f.id}>
                      <td style={{ whiteSpace: 'nowrap' }}>{new Date(f.fecha).toLocaleDateString()}</td>
                      <td style={{ whiteSpace: 'nowrap' }}>{f.hora}</td>
                      <td>{nombreVariable(f.variable)}</td>
                      <td style={{ fontWeight: 700, border: '2px solid #b71c1c' }}>
                        {f.variable.valor}{f.variable.unidad_medida ? ` ${f.variable.unidad_medida}` : ''}
                      </td>
                      <td>{formatearLimite(f.variable.limite_inferior, f.variable.limite_superior)}</td>
                      <td>{f.usuarioRealizo || '—'}</td>
                      <td>{f.usuarioVerifico || '—'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
