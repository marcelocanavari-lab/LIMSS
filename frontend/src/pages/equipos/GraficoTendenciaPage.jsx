import { useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../../context/AuthContext';
import TopBar from '../../components/TopBar';
import { equiposApi } from '../../api/equipos';
import { ApiError } from '../../api/client';

function hoyISO() {
  return new Date().toISOString().slice(0, 10);
}

function hace30DiasISO() {
  const d = new Date();
  d.setDate(d.getDate() - 30);
  return d.toISOString().slice(0, 10);
}

// new Date('YYYY-MM-DD') interpreta la fecha en UTC -- en huso horario
// negativo (Argentina, UTC-3) se corre un día para atrás al mostrarla con
// toLocaleDateString() (que usa la zona LOCAL). Se arma con las partes
// sueltas, sin pasar por Date, mismo criterio que DiasSinRegistrarPage.jsx.
function formatearFechaCorta(fechaISO) {
  const [, mes, dia] = fechaISO.split('-');
  return `${dia}/${mes}`;
}

const ANCHO_GRAFICO = 900;
const ALTO_GRAFICO = 230;

// Dimensiones de la versión imprimible/exportada -- MUCHO más grande que la
// de pantalla (900x230, pensada para la card compacta): esta se estira al
// 100% de una página A4 horizontal completa (ver .equipos-print-ancho +
// @page más abajo), así que necesita su propio lienzo con más lugar real
// para textos más grandes y más etiquetas de fecha en el eje X, no una
// versión ampliada al mismo % de la chica.
const ANCHO_GRAFICO_IMPRESION = 1500;
const ALTO_GRAFICO_IMPRESION = 760;
// Alto del bloque de título (variable + rango de fechas) que se antepone al
// gráfico SOLO en la versión imprimible/exportada -- la versión en pantalla
// ya tiene ese texto afuera del SVG, en HTML normal (ver el header de la
// card, más abajo); acá hace falta adentro del propio SVG porque tanto la
// impresión como la descarga a PNG solo capturan el contenido del SVG.
const ALTO_TITULO_IMPRESION = 90;

// Paleta fija para impresión/exportación -- independiente de los tokens
// CSS (var(--accent) etc.) que solo existen en el documento vivo de la
// app: un SVG exportado a PNG o mandado a impresión se serializa aparte
// (XMLSerializer / @media print), sin acceso a las custom properties del
// documento, así que ahí habría que resolverlas a mano igual -- más
// simple usar colores fijos pensados para fondo blanco directamente
// (mismo criterio que .printable en components.css, que también fuerza
// colores fijos en vez de heredar el tema oscuro de la app).
const COLORES_PANTALLA = { fondo: 'none', eje: 'var(--border)', texto: 'var(--ink-2)', curva: 'var(--accent)', limite: 'var(--warn)', normal: 'var(--accent)', fuera: 'var(--danger)' };
const COLORES_IMPRESION = { fondo: '#ffffff', eje: '#888888', texto: '#333333', curva: '#1976D2', limite: '#b8860b', normal: '#1976D2', fuera: '#c62828' };

// Gráfico de líneas liviano en SVG puro -- este proyecto no tiene ninguna
// librería de gráficos instalada (ver package.json), así que en vez de
// sumar una dependencia nueva para un solo gráfico de líneas simple, se
// arma a mano. Eje X por índice de punto (no por fecha real): las lecturas
// no son perfectamente periódicas (a veces falta un día, a veces hay dos en
// el mismo día) y espaciarlas por índice da una curva legible sin manejar
// los casos raros de una escala temporal real -- las etiquetas del eje X sí
// muestran la fecha real de una muestra de los puntos, no un promedio.
function GraficoLineas({ puntos, limiteInferior, limiteSuperior, unidad, titulo, subtitulo, paraImprimir = false, svgRef }) {
  const colores = paraImprimir ? COLORES_IMPRESION : COLORES_PANTALLA;
  const ancho = paraImprimir ? ANCHO_GRAFICO_IMPRESION : ANCHO_GRAFICO;
  const altoGrafico = paraImprimir ? ALTO_GRAFICO_IMPRESION : ALTO_GRAFICO;
  const offsetTitulo = titulo ? (paraImprimir ? ALTO_TITULO_IMPRESION : 44) : 0;
  const altoTotal = altoGrafico + offsetTitulo;

  // Tamaños de fuente/trazo/margen escalados aparte para impresión -- no
  // "el mismo gráfico ampliado", sino proporciones pensadas para leerse
  // cómodo en una hoja A4 horizontal real (fuente ~3-4mm de alto en papel),
  // bastante más grandes en relación al lienzo que las de la versión chica
  // de pantalla.
  const fs = paraImprimir
    ? { titulo: 30, subtitulo: 17, eje: 20, limite: 19, fechaX: 17 }
    : { titulo: 15, subtitulo: 11, eje: 11, limite: 11, fechaX: 10 };
  const M_IZQ = paraImprimir ? 100 : 55;
  const M_DER = paraImprimir ? 40 : 20;
  const M_SUP = (paraImprimir ? 30 : 15) + offsetTitulo;
  const M_INF = paraImprimir ? 70 : 34;
  const anchoUtil = ancho - M_IZQ - M_DER;
  const altoUtil = altoGrafico - (paraImprimir ? 30 : 15) - M_INF;
  const grosorCurva = paraImprimir ? 3 : 2;
  const radioPunto = paraImprimir ? 7 : 3;
  const radioPuntoFuera = paraImprimir ? 10 : 4.5;

  const valores = puntos.map((p) => p.valor);
  const referencias = [limiteInferior, limiteSuperior].filter((v) => v !== null && v !== undefined);
  const todosLosValores = [...valores, ...referencias];
  let yMin = Math.min(...todosLosValores);
  let yMax = Math.max(...todosLosValores);
  if (yMin === yMax) { yMin -= 1; yMax += 1; }
  const pad = (yMax - yMin) * 0.1;
  yMin -= pad;
  yMax += pad;

  function escalaX(i) {
    return puntos.length <= 1 ? M_IZQ + anchoUtil / 2 : M_IZQ + (i / (puntos.length - 1)) * anchoUtil;
  }
  function escalaY(v) {
    return M_SUP + altoUtil - ((v - yMin) / (yMax - yMin)) * altoUtil;
  }

  const puntosLinea = puntos.map((p, i) => `${escalaX(i)},${escalaY(p.valor)}`).join(' ');

  // Etiquetas del eje X: la versión de pantalla (card chica) se limita a
  // ~8 para no amontonar; la de impresión tiene mucho más ancho real
  // disponible (ver ANCHO_GRAFICO_IMPRESION), así que entran más sin
  // amontonarse.
  const maxEtiquetas = paraImprimir ? 16 : 8;
  const pasoEtiquetas = Math.max(1, Math.ceil(puntos.length / maxEtiquetas));
  const indicesEtiquetas = puntos.map((_, i) => i).filter((i) => i % pasoEtiquetas === 0 || i === puntos.length - 1);

  const etiquetasY = [yMin + pad, (yMin + yMax) / 2, yMax - pad];

  return (
    <svg ref={svgRef} viewBox={`0 0 ${ancho} ${altoTotal}`} style={{ width: '100%', height: 'auto', display: 'block' }}>
      {paraImprimir && <rect x={0} y={0} width={ancho} height={altoTotal} fill={colores.fondo} />}

      {titulo && (
        <>
          <text x={M_IZQ} y={paraImprimir ? 36 : 20} fill={colores.texto} fontSize={fs.titulo} fontWeight="700">{titulo}</text>
          {subtitulo && <text x={M_IZQ} y={paraImprimir ? 60 : 36} fill={colores.texto} fontSize={fs.subtitulo}>{subtitulo}</text>}
          {paraImprimir && (
            <text x={M_IZQ} y={80} fontSize={fs.subtitulo}>
              <tspan fill={colores.limite}>▬▬ límites del rango aceptable</tspan>
              <tspan fill={colores.texto} dx="18">-- </tspan>
              <tspan fill={colores.fuera}>● fuera de rango</tspan>
              <tspan fill={colores.texto} dx="18">-- </tspan>
              <tspan fill={colores.normal}>● dentro de rango</tspan>
            </text>
          )}
        </>
      )}

      {/* Eje */}
      <line x1={M_IZQ} y1={M_SUP} x2={M_IZQ} y2={M_SUP + altoUtil} stroke={colores.eje} />
      <line x1={M_IZQ} y1={M_SUP + altoUtil} x2={M_IZQ + anchoUtil} y2={M_SUP + altoUtil} stroke={colores.eje} />

      {/* Líneas de referencia (límites) */}
      {limiteInferior !== null && limiteInferior !== undefined && (
        <>
          <line x1={M_IZQ} y1={escalaY(limiteInferior)} x2={M_IZQ + anchoUtil} y2={escalaY(limiteInferior)} stroke={colores.limite} strokeDasharray="6 4" strokeWidth={paraImprimir ? 2 : 1} />
          <text x={M_IZQ + anchoUtil} y={escalaY(limiteInferior) - 6} fill={colores.limite} fontSize={fs.limite} textAnchor="end">límite inf. {limiteInferior}</text>
        </>
      )}
      {limiteSuperior !== null && limiteSuperior !== undefined && (
        <>
          <line x1={M_IZQ} y1={escalaY(limiteSuperior)} x2={M_IZQ + anchoUtil} y2={escalaY(limiteSuperior)} stroke={colores.limite} strokeDasharray="6 4" strokeWidth={paraImprimir ? 2 : 1} />
          <text x={M_IZQ + anchoUtil} y={escalaY(limiteSuperior) - 6} fill={colores.limite} fontSize={fs.limite} textAnchor="end">límite sup. {limiteSuperior}</text>
        </>
      )}

      {/* Etiquetas eje Y */}
      {etiquetasY.map((v, i) => (
        <text key={i} x={M_IZQ - 10} y={escalaY(v) + 5} fill={colores.texto} fontSize={fs.eje} textAnchor="end">{v.toFixed(2)}</text>
      ))}

      {/* Curva */}
      {puntos.length > 1 && <polyline points={puntosLinea} fill="none" stroke={colores.curva} strokeWidth={grosorCurva} />}

      {/* Puntos -- rojos los que están fuera de rango, para que se note de
          un vistazo dónde la curva cruzó los límites. */}
      {puntos.map((p, i) => (
        <circle
          key={i} cx={escalaX(i)} cy={escalaY(p.valor)} r={p.fueraDeRango ? radioPuntoFuera : radioPunto}
          fill={p.fueraDeRango ? colores.fuera : colores.normal}
        >
          <title>{`${p.fecha} ${p.hora} -- ${p.valor}${unidad ? ` ${unidad}` : ''}`}</title>
        </circle>
      ))}

      {/* Etiquetas eje X */}
      {indicesEtiquetas.map((i) => (
        <text key={i} x={escalaX(i)} y={M_SUP + altoUtil + M_INF - (paraImprimir ? 28 : 16)} fill={colores.texto} fontSize={fs.fechaX} textAnchor="middle">
          {formatearFechaCorta(puntos[i].fecha)}
        </text>
      ))}
    </svg>
  );
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
