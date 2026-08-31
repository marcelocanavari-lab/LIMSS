import { Fragment, useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../../context/AuthContext';
import TopBar from '../../components/TopBar';
import { equiposApi } from '../../api/equipos';
import { ApiError, descargarArchivoConAuth } from '../../api/client';

// Bloques de variables CONSECUTIVAS con el mismo grupo, para el colSpan del
// encabezado "Presión de"/"Caudal de" -- mismo criterio que
// NuevaLecturaPage.jsx (duplicado a propósito, mismo patrón que el resto
// de este proyecto para helpers chicos, ver _se_superponen en
// impresion_sato.py).
function bloquesConsecutivos(variables) {
  const bloques = [];
  for (const v of variables) {
    const ultimo = bloques[bloques.length - 1];
    if (ultimo && ultimo.grupo === (v.grupo || '')) {
      ultimo.vars.push(v);
    } else {
      bloques.push({ grupo: v.grupo || '', vars: [v] });
    }
  }
  return bloques;
}

export default function HistorialLecturasPage() {
  const { user } = useAuth();
  const navigate = useNavigate();

  const [equipos, setEquipos] = useState([]);
  const [idEquipo, setIdEquipo] = useState('');
  const [variables, setVariables] = useState([]);
  const [fechaDesde, setFechaDesde] = useState('');
  const [fechaHasta, setFechaHasta] = useState('');
  const [lecturas, setLecturas] = useState([]);
  const [fechaGeneracion, setFechaGeneracion] = useState(null);
  const [expandidoId, setExpandidoId] = useState(null);
  const [loading, setLoading] = useState(true);
  const [exportando, setExportando] = useState(false);
  const [error, setError] = useState('');

  // Reporte de Mediciones: hasta 17 columnas (Fecha/Hora + 13 variables +
  // Realizó/Verificó) -- mismo ancho de página Oficio horizontal que Libro
  // de Ingresos (17 columnas también), inyectado solo mientras esta
  // pantalla está montada (ver el comentario completo en
  // LibroIngresosPage.jsx: @page no se puede condicionar con una clase).
  useEffect(() => {
    const style = document.createElement('style');
    style.textContent = '@media print { @page { size: 330mm 216mm; margin: 10mm; } }';
    document.head.appendChild(style);
    return () => { document.head.removeChild(style); };
  }, []);

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
    equiposApi.listarVariables(idEquipo).then(setVariables).catch(() => setVariables([]));
  }, [idEquipo]);

  function cargar() {
    if (!idEquipo) return;
    setLoading(true);
    setError('');
    equiposApi
      .listarLecturas({ idEquipo, fechaDesde: fechaDesde || undefined, fechaHasta: fechaHasta || undefined })
      .then((data) => {
        setLecturas(data);
        setFechaGeneracion(new Date());
      })
      .catch((err) => setError(err instanceof ApiError ? err.message : 'No se pudo cargar el historial'))
      .finally(() => setLoading(false));
  }

  useEffect(cargar, [idEquipo, fechaDesde, fechaHasta]);

  async function exportarCsv() {
    setError('');
    setExportando(true);
    try {
      const path = equiposApi.exportarLecturasPath({ idEquipo, fechaDesde: fechaDesde || undefined, fechaHasta: fechaHasta || undefined });
      await descargarArchivoConAuth(path, 'mediciones_equipo.csv');
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'No se pudo exportar el reporte');
    } finally {
      setExportando(false);
    }
  }

  const equipoElegido = equipos.find((eq) => String(eq.id_equipo) === idEquipo);
  const bloques = bloquesConsecutivos(variables);
  const cantidadColumnas = 2 + variables.length + 1; // Fecha/Hora + variables + toggle

  return (
    <div className="screen">
      <TopBar titulo="Historial de Lecturas" subtitulo="Equipos" onBack={() => navigate(-1)} />
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
            <div className="field" style={{ flex: '1 1 160px' }}>
              <label className="field-label" htmlFor="desde">Desde</label>
              <input id="desde" className="field-input" type="date" value={fechaDesde} onChange={(e) => setFechaDesde(e.target.value)} />
            </div>
            <div className="field" style={{ flex: '1 1 160px' }}>
              <label className="field-label" htmlFor="hasta">Hasta</label>
              <input id="hasta" className="field-input" type="date" value={fechaHasta} onChange={(e) => setFechaHasta(e.target.value)} />
            </div>
            {lecturas.length > 0 && (
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
        ) : lecturas.length === 0 ? (
          <div className="no-print state-block">
            <span className="state-block-title">Sin lecturas</span>
            <span>No hay lecturas guardadas para estos filtros</span>
          </div>
        ) : (
          <>
            {/* Vista interactiva (pantalla) -- las 13 variables en un solo
                renglón por lectura, igual que la planilla Excel original.
                Mismo patrón de scroll horizontal propio (reporte-tabla-
                scroll) que Libro de Ingresos/Reporte de Testigos. */}
            <div className="no-print reporte-tabla-scroll">
              <table className="data-table equipos-tabla-historial">
                <thead>
                  <tr>
                    <th rowSpan={2} style={{ verticalAlign: 'bottom' }}>Fecha</th>
                    <th rowSpan={2} style={{ verticalAlign: 'bottom' }}>Hora</th>
                    {bloques.map((b, i) => (
                      b.grupo ? (
                        <th key={`g-${i}`} colSpan={b.vars.length} style={{ textAlign: 'center' }}>{b.grupo}</th>
                      ) : (
                        b.vars.map((v) => (
                          <th key={v.id_variable} rowSpan={2} style={{ verticalAlign: 'bottom' }}>{v.nombre}</th>
                        ))
                      )
                    ))}
                    <th rowSpan={2}></th>
                  </tr>
                  <tr>
                    {bloques.filter((b) => b.grupo).flatMap((b) => b.vars).map((v) => (
                      <th key={v.id_variable}>{v.nombre}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {lecturas.map((l) => {
                    const expandido = expandidoId === l.id_lectura;
                    const valoresPorVariable = new Map(l.valores.map((v) => [v.id_variable, v]));
                    return (
                      <Fragment key={l.id_lectura}>
                        <tr style={{ cursor: 'pointer' }} onClick={() => setExpandidoId(expandido ? null : l.id_lectura)}>
                          <td style={{ whiteSpace: 'nowrap' }}>
                            {l.tiene_fuera_de_rango && <span title="Tiene valores fuera de rango" style={{ color: 'var(--danger)', marginRight: 4 }}>⚠</span>}
                            {new Date(l.fecha).toLocaleDateString()}
                          </td>
                          <td style={{ whiteSpace: 'nowrap' }}>{l.hora}</td>
                          {variables.map((v) => {
                            const val = valoresPorVariable.get(v.id_variable);
                            if (!val) return <td key={v.id_variable} style={{ textAlign: 'center', color: 'var(--ink-3)' }}>—</td>;
                            return (
                              <td
                                key={v.id_variable}
                                style={{
                                  textAlign: 'center', whiteSpace: 'nowrap',
                                  ...(val.fuera_de_rango ? { background: 'var(--danger-soft)', color: 'var(--danger)', fontWeight: 600 } : {}),
                                }}
                              >
                                {val.valor}
                              </td>
                            );
                          })}
                          <td style={{ color: 'var(--accent)', textAlign: 'center' }}>{expandido ? '▲' : '▼'}</td>
                        </tr>
                        {expandido && (
                          <tr>
                            <td colSpan={cantidadColumnas} style={{ background: 'var(--surf-2)', fontSize: 'var(--fs-sm)', color: 'var(--ink-2)' }}>
                              <div style={{ display: 'flex', gap: 'var(--sp-5)' }}>
                                <span>Realizó: {l.usuario_realizo_nombre || '—'}</span>
                                <span>Verificó: {l.usuario_verifico_nombre || '—'}</span>
                              </div>
                            </td>
                          </tr>
                        )}
                      </Fragment>
                    );
                  })}
                </tbody>
              </table>
            </div>

            {/* Vista de impresión -- estática (sin fila expandible: Realizó/
                Verificó van siempre visibles como 2 columnas más), oculta en
                pantalla (print-only). */}
            <div className="printable print-only equipos-print-ancho">
              <h1 style={{ fontSize: 'var(--fs-lg)', marginBottom: 'var(--sp-2)' }}>
                Reporte de Mediciones -- {equipoElegido?.nombre}
              </h1>
              <p style={{ color: 'var(--ink-2)', marginBottom: 'var(--sp-4)' }}>
                {fechaDesde || fechaHasta ? `Período: ${fechaDesde || '...'} a ${fechaHasta || '...'} -- ` : ''}
                Generado el {fechaGeneracion?.toLocaleString()} por {user?.nombre} {user?.apellido} ({user?.codigo}) —{' '}
                {lecturas.length} lectura{lecturas.length === 1 ? '' : 's'}
              </p>
              <table className="data-table equipos-tabla-historial">
                <thead>
                  <tr>
                    <th rowSpan={2} style={{ verticalAlign: 'bottom' }}>Fecha</th>
                    <th rowSpan={2} style={{ verticalAlign: 'bottom' }}>Hora</th>
                    {bloques.map((b, i) => (
                      b.grupo ? (
                        <th key={`g-${i}`} colSpan={b.vars.length} style={{ textAlign: 'center' }}>{b.grupo}</th>
                      ) : (
                        b.vars.map((v) => (
                          <th key={v.id_variable} rowSpan={2} style={{ verticalAlign: 'bottom' }}>{v.nombre}</th>
                        ))
                      )
                    ))}
                    <th rowSpan={2}>Realizó</th>
                    <th rowSpan={2}>Verificó</th>
                  </tr>
                  <tr>
                    {bloques.filter((b) => b.grupo).flatMap((b) => b.vars).map((v) => (
                      <th key={v.id_variable}>{v.nombre}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {lecturas.map((l) => {
                    const valoresPorVariable = new Map(l.valores.map((v) => [v.id_variable, v]));
                    return (
                      <tr key={l.id_lectura}>
                        <td style={{ whiteSpace: 'nowrap' }}>{new Date(l.fecha).toLocaleDateString()}</td>
                        <td style={{ whiteSpace: 'nowrap' }}>{l.hora}</td>
                        {variables.map((v) => {
                          const val = valoresPorVariable.get(v.id_variable);
                          if (!val) return <td key={v.id_variable} style={{ textAlign: 'center' }}>—</td>;
                          return (
                            <td
                              key={v.id_variable}
                              style={{
                                textAlign: 'center', whiteSpace: 'nowrap',
                                // Sin background: la impresión no garantiza
                                // que sobreviva un relleno de color (mismo
                                // motivo por el que .printable .badge en
                                // components.css cambia a borde en vez de
                                // fondo) -- acá el resalte es borde + negrita
                                // + color de texto.
                                ...(val.fuera_de_rango ? { border: '2px solid #b71c1c', fontWeight: 700, color: '#b71c1c' } : {}),
                              }}
                            >
                              {val.valor}
                            </td>
                          );
                        })}
                        <td>{l.usuario_realizo_nombre || '—'}</td>
                        <td>{l.usuario_verifico_nombre || '—'}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
