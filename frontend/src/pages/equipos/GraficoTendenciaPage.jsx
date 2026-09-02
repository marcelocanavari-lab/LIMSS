import { useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../../context/AuthContext';
import TopBar from '../../components/TopBar';
import { equiposApi } from '../../api/equipos';
import { ApiError } from '../../api/client';
import { GraficoLineas, ANCHO_GRAFICO_IMPRESION, ALTO_GRAFICO_IMPRESION, ALTO_TITULO_IMPRESION } from './GraficoLineas';

function hoyISO() {
  return new Date().toISOString().slice(0, 10);
}

function hace30DiasISO() {
  const d = new Date();
  d.setDate(d.getDate() - 30);
  return d.toISOString().slice(0, 10);
}

export default function GraficoTendenciaPage() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const svgImprimirRef = useRef(null);

  const [equipos, setEquipos] = useState([]);
  const [idEquipo, setIdEquipo] = useState('');
  const [variables, setVariables] = useState([]);
  const [idVariable, setIdVariable] = useState('');
  const [fechaDesde, setFechaDesde] = useState(hace30DiasISO());
  const [fechaHasta, setFechaHasta] = useState(hoyISO());
  const [lecturas, setLecturas] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [exportandoImagen, setExportandoImagen] = useState(false);

  // A4 horizontal explícito, con margen chico -- mismo problema y mismo fix
  // que Libro de Ingresos/Historial de Lecturas (ver el comentario completo
  // en LibroIngresosPage.jsx): sin esto, la impresión cae al tamaño/
  // orientación por defecto del navegador (A4/Carta VERTICAL), y ni el
  // gráfico (ancho pensado para horizontal) ni el max-width:100% de
  // .printable alcanzan a ocupar la página real -- justo el problema
  // reportado (PDF chico, arrinconado arriba a la izquierda).
  useEffect(() => {
    const style = document.createElement('style');
    style.textContent = '@media print { @page { size: 297mm 210mm; margin: 10mm; } }';
    document.head.appendChild(style);
    return () => { document.head.removeChild(style); };
  }, []);

  useEffect(() => {
    equiposApi.listar().then((data) => {
      setEquipos(data);
      if (data.length >= 1) setIdEquipo((prev) => prev || String(data[0].id_equipo));
    }).catch((err) => setError(err instanceof ApiError ? err.message : 'No se pudo cargar la pantalla'));
  }, []);

  useEffect(() => {
    if (!idEquipo) return;
    equiposApi.listarVariables(idEquipo).then((data) => {
      setVariables(data);
      setIdVariable((prev) => (data.some((v) => String(v.id_variable) === prev) ? prev : (data[0] ? String(data[0].id_variable) : '')));
    }).catch(() => setVariables([]));
  }, [idEquipo]);

  // Carga las lecturas con el rango de fechas ACTUAL de los inputs -- se
  // llama automáticamente al cambiar de equipo (selección completa, sin
  // riesgo de "valor a medio tipear"), y a demanda desde el botón
  // "Generar" para las fechas. Antes las fechas también estaban en las
  // dependencias del efecto: como <input type="date"> puede disparar
  // onChange con un valor todavía incompleto mientras se escribe a mano
  // (no solo al elegir del selector nativo), cada tecla llegaba a pedir el
  // gráfico con una fecha inválida a mitad de tipeo -- el mismo patrón ya
  // usado en Libro de Ingresos (botón "Generar reporte" en vez de
  // auto-disparar por cambio de input) evita eso.
  function cargarLecturas() {
    if (!idEquipo) return;
    setLoading(true);
    setError('');
    equiposApi
      .listarLecturas({ idEquipo, fechaDesde: fechaDesde || undefined, fechaHasta: fechaHasta || undefined })
      .then(setLecturas)
      .catch((err) => setError(err instanceof ApiError ? err.message : 'No se pudo cargar las lecturas'))
      .finally(() => setLoading(false));
  }

  useEffect(cargarLecturas, [idEquipo]);

  const variableElegida = variables.find((v) => String(v.id_variable) === idVariable);
  const equipoElegido = equipos.find((eq) => String(eq.id_equipo) === idEquipo);
  const nombreVariable = variableElegida ? (variableElegida.grupo ? `${variableElegida.grupo} ${variableElegida.nombre}` : variableElegida.nombre) : '';

  // listarLecturas ya devuelve más recientes primero -- se invierte para
  // que el gráfico corra en el tiempo de izquierda a derecha.
  const puntos = variableElegida
    ? lecturas
      .slice()
      .reverse()
      .map((l) => {
        const val = l.valores.find((v) => v.id_variable === variableElegida.id_variable);
        return val ? { fecha: l.fecha, hora: l.hora, valor: val.valor, fueraDeRango: val.fuera_de_rango } : null;
      })
      .filter(Boolean)
    : [];

  const subtituloReporte = `${equipoElegido?.nombre || ''} -- Período: ${fechaDesde || '...'} a ${fechaHasta || '...'} -- ${puntos.length} lectura${puntos.length === 1 ? '' : 's'}`;

  // Descarga el gráfico como PNG -- se serializa la copia "para imprimir"
  // del SVG (colores fijos, título adentro) a un <img>, se dibuja sobre un
  // canvas (2x resolución para que no se vea pixelado al imprimir esa
  // imagen después) y se exporta con toBlob. Todo client-side: los datos
  // ya están cargados, no hace falta generar nada en el servidor para esto.
  async function descargarImagen() {
    const svgEl = svgImprimirRef.current;
    if (!svgEl) return;
    setError('');
    setExportandoImagen(true);
    try {
      const svgString = new XMLSerializer().serializeToString(svgEl);
      const svgBlob = new Blob([svgString], { type: 'image/svg+xml;charset=utf-8' });
      const url = URL.createObjectURL(svgBlob);
      const alto = ALTO_GRAFICO_IMPRESION + ALTO_TITULO_IMPRESION;
      const escala = 2;
      await new Promise((resolve, reject) => {
        const img = new Image();
        img.onload = () => {
          const canvas = document.createElement('canvas');
          canvas.width = ANCHO_GRAFICO_IMPRESION * escala;
          canvas.height = alto * escala;
          const ctx = canvas.getContext('2d');
          ctx.fillStyle = '#ffffff';
          ctx.fillRect(0, 0, canvas.width, canvas.height);
          ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
          URL.revokeObjectURL(url);
          canvas.toBlob((blob) => {
            const a = document.createElement('a');
            a.href = URL.createObjectURL(blob);
            a.download = `tendencia_${(nombreVariable || 'variable').replace(/\s+/g, '_')}.png`;
            document.body.appendChild(a);
            a.click();
            a.remove();
            resolve();
          }, 'image/png');
        };
        img.onerror = reject;
        img.src = url;
      });
    } catch {
      setError('No se pudo exportar la imagen');
    } finally {
      setExportandoImagen(false);
    }
  }

  return (
    <div className="screen">
      <TopBar titulo="Gráfico de Tendencia" subtitulo="Equipos" onBack={() => navigate(-1)} />
      {/* Filtro + gráfico en UNA sola card compacta (card-compact/field-
          compact, mismo criterio que el formulario unificado de Solicitud
          de Muestreo) -- para que encabezado y gráfico entren juntos en
          1366x768 sin scroll. */}
      <div className="screen-content">
        <div className="no-print card card-compact" style={{ marginBottom: 'var(--sp-2)' }}>
          <div style={{ display: 'flex', gap: 'var(--sp-3)', flexWrap: 'wrap', alignItems: 'flex-end' }}>
            <div className="field field-compact" style={{ flex: '1 1 220px' }}>
              <label className="field-label" htmlFor="equipo">Equipo</label>
              <select id="equipo" className="field-input" value={idEquipo} onChange={(e) => setIdEquipo(e.target.value)}>
                {equipos.map((eq) => (
                  <option key={eq.id_equipo} value={eq.id_equipo}>{eq.nombre}</option>
                ))}
              </select>
            </div>
            <div className="field field-compact" style={{ flex: '1 1 220px' }}>
              <label className="field-label" htmlFor="variable">Variable</label>
              <select id="variable" className="field-input" value={idVariable} onChange={(e) => setIdVariable(e.target.value)}>
                {variables.map((v) => (
                  <option key={v.id_variable} value={v.id_variable}>{v.grupo ? `${v.grupo} ${v.nombre}` : v.nombre}</option>
                ))}
              </select>
            </div>
            <div className="field field-compact" style={{ flex: '1 1 160px' }}>
              <label className="field-label" htmlFor="desde">Desde</label>
              <input id="desde" className="field-input" type="date" value={fechaDesde} onChange={(e) => setFechaDesde(e.target.value)} />
            </div>
            <div className="field field-compact" style={{ flex: '1 1 160px' }}>
              <label className="field-label" htmlFor="hasta">Hasta</label>
              <input id="hasta" className="field-input" type="date" value={fechaHasta} onChange={(e) => setFechaHasta(e.target.value)} />
            </div>
            <button className="btn btn-primary" onClick={cargarLecturas} disabled={loading}>
              {loading ? <span className="spinner" /> : 'Generar →'}
            </button>
            {puntos.length > 0 && (
              <>
                <button className="btn btn-secondary" onClick={descargarImagen} disabled={exportandoImagen}>
                  {exportandoImagen ? <span className="spinner" /> : 'Descargar imagen (PNG)'}
                </button>
                <button className="btn btn-secondary" onClick={() => window.print()}>Imprimir / Exportar PDF</button>
              </>
            )}
          </div>
        </div>

        {error && <div className="no-print alert alert-danger" style={{ marginBottom: 'var(--sp-2)' }}>{error}</div>}

        {loading ? (
          <div className="no-print state-block"><span className="spinner" /></div>
        ) : puntos.length === 0 ? (
          <div className="no-print state-block">
            <span className="state-block-title">Sin datos</span>
            <span>No hay lecturas de esta variable en el rango de fechas elegido</span>
          </div>
        ) : (
          <>
            {/* Vista en pantalla -- colores del tema de la app (var(--...)). */}
            <div className="no-print card card-compact">
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', flexWrap: 'wrap', marginBottom: 'var(--sp-2)' }}>
                <h2 style={{ fontSize: 'var(--fs-base)', margin: 0 }}>{nombreVariable}</h2>
                <span style={{ color: 'var(--ink-2)', fontSize: 'var(--fs-xs)' }}>
                  {puntos.length} lectura{puntos.length === 1 ? '' : 's'} -- líneas punteadas: rango aceptable -- puntos rojos: fuera de rango
                </span>
              </div>
              <GraficoLineas puntos={puntos} limiteInferior={variableElegida.limite_inferior} limiteSuperior={variableElegida.limite_superior} unidad={variableElegida.unidad_medida} />
            </div>

            {/* Vista de impresión/exportación -- colores fijos para fondo
                blanco (mismo criterio que .printable en components.css) y
                título/subtítulo dibujados DENTRO del SVG, porque tanto
                @media print como la descarga a PNG solo capturan el
                contenido del propio SVG, no el HTML de alrededor. Este
                mismo <svg> (vía svgImprimirRef) es la fuente del botón
                "Descargar imagen (PNG)". */}
            <div className="printable print-only equipos-print-ancho">
              <GraficoLineas
                svgRef={svgImprimirRef}
                puntos={puntos}
                limiteInferior={variableElegida.limite_inferior}
                limiteSuperior={variableElegida.limite_superior}
                unidad={variableElegida.unidad_medida}
                titulo={`Gráfico de Tendencia -- ${nombreVariable}`}
                subtitulo={subtituloReporte}
                paraImprimir
              />
              <p style={{ color: '#666', fontSize: '11px', marginTop: 'var(--sp-2)' }}>
                Generado el {new Date().toLocaleString()} por {user?.nombre} {user?.apellido} ({user?.codigo})
              </p>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
