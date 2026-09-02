export const ANCHO_GRAFICO = 900;
export const ALTO_GRAFICO = 230;

// Dimensiones de la versión imprimible/exportada -- MUCHO más grande que la
// de pantalla (900x230, pensada para la card compacta): esta se estira al
// 100% de una página A4 horizontal completa (ver .equipos-print-ancho +
// @page en GraficoTendenciaPage.jsx), así que necesita su propio lienzo con
// más lugar real para textos más grandes y más etiquetas de fecha en el eje
// X, no una versión ampliada al mismo % de la chica.
export const ANCHO_GRAFICO_IMPRESION = 1500;
export const ALTO_GRAFICO_IMPRESION = 760;
// Alto del bloque de título (variable + rango de fechas) que se antepone al
// gráfico SOLO en la versión imprimible/exportada -- la versión en pantalla
// ya tiene ese texto afuera del SVG, en HTML normal; acá hace falta adentro
// del propio SVG porque tanto la impresión como la descarga a PNG solo
// capturan el contenido del SVG.
export const ALTO_TITULO_IMPRESION = 90;

// Versión "chica" para grillas con un gráfico por variable (ver
// GraficoTodasVariablesPage.jsx) -- lienzo mucho más angosto que el de
// pantalla normal a propósito: como el SVG escala su viewBox al 100% del
// ancho del contenedor (width:'100%'), el tamaño de fuente/trazo definido
// en unidades del viewBox termina rindiendo casi 1:1 en píxeles reales solo
// si el viewBox tiene un ancho parecido al del contenedor -- reusar el
// viewBox de 900 de pantalla completa en una card angosta de grilla haría
// el texto ilegible (se escala junto con el resto del dibujo).
const ANCHO_GRAFICO_CHICO = 340;
const ALTO_GRAFICO_CHICO = 190;

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

// new Date('YYYY-MM-DD') interpreta la fecha en UTC -- en huso horario
// negativo (Argentina, UTC-3) se corre un día para atrás al mostrarla con
// toLocaleDateString() (que usa la zona LOCAL). Se arma con las partes
// sueltas, sin pasar por Date, mismo criterio que DiasSinRegistrarPage.jsx.
function formatearFechaCorta(fechaISO) {
  const [, mes, dia] = fechaISO.split('-');
  return `${dia}/${mes}`;
}

// Gráfico de líneas liviano en SVG puro -- este proyecto no tiene ninguna
// librería de gráficos instalada (ver package.json), así que en vez de
// sumar una dependencia nueva para un solo gráfico de líneas simple, se
// arma a mano. Eje X por índice de punto (no por fecha real): las lecturas
// no son perfectamente periódicas (a veces falta un día, a veces hay dos en
// el mismo día) y espaciarlas por índice da una curva legible sin manejar
// los casos raros de una escala temporal real -- las etiquetas del eje X sí
// muestran la fecha real de una muestra de los puntos, no un promedio.
//
// Reutilizado en 3 tamaños: pantalla completa (GraficoTendenciaPage.jsx),
// impresión/exportación (paraImprimir) y chico para grillas de varias
// variables a la vez (compacto, ver GraficoTodasVariablesPage.jsx).
export function GraficoLineas({
  puntos, limiteInferior, limiteSuperior, unidad, titulo, subtitulo,
  paraImprimir = false, compacto = false, svgRef,
}) {
  const colores = paraImprimir ? COLORES_IMPRESION : COLORES_PANTALLA;
  const ancho = paraImprimir ? ANCHO_GRAFICO_IMPRESION : compacto ? ANCHO_GRAFICO_CHICO : ANCHO_GRAFICO;
  const altoGrafico = paraImprimir ? ALTO_GRAFICO_IMPRESION : compacto ? ALTO_GRAFICO_CHICO : ALTO_GRAFICO;
  const offsetTitulo = titulo ? (paraImprimir ? ALTO_TITULO_IMPRESION : compacto ? 20 : 44) : 0;
  const altoTotal = altoGrafico + offsetTitulo;

  // Tamaños de fuente/trazo/margen escalados aparte para cada variante -- no
  // "el mismo gráfico ampliado/achicado", sino proporciones pensadas para
  // leerse cómodo en cada contexto (hoja A4 horizontal real para impresión,
  // card angosta de grilla para compacto).
  const fs = paraImprimir
    ? { titulo: 30, subtitulo: 17, eje: 20, limite: 19, fechaX: 17 }
    : compacto
      ? { titulo: 12, subtitulo: 9, eje: 8, limite: 8, fechaX: 7 }
      : { titulo: 15, subtitulo: 11, eje: 11, limite: 11, fechaX: 10 };
  const M_IZQ = paraImprimir ? 100 : compacto ? 34 : 55;
  const M_DER = paraImprimir ? 40 : compacto ? 8 : 20;
  const M_SUP = (paraImprimir ? 30 : compacto ? 8 : 15) + offsetTitulo;
  const M_INF = paraImprimir ? 70 : compacto ? 20 : 34;
  const anchoUtil = ancho - M_IZQ - M_DER;
  const altoUtil = altoGrafico - (paraImprimir ? 30 : compacto ? 8 : 15) - M_INF;
  const grosorCurva = paraImprimir ? 3 : compacto ? 1.5 : 2;
  const radioPunto = paraImprimir ? 7 : compacto ? 2 : 3;
  const radioPuntoFuera = paraImprimir ? 10 : compacto ? 3 : 4.5;

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
  // ~8 para no amontonar, la compacta (grilla) a ~4 -- la de impresión tiene
  // mucho más ancho real disponible, así que entran más sin amontonarse.
  const maxEtiquetas = paraImprimir ? 16 : compacto ? 4 : 8;
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
        <text key={i} x={escalaX(i)} y={M_SUP + altoUtil + M_INF - (paraImprimir ? 28 : compacto ? 8 : 16)} fill={colores.texto} fontSize={fs.fechaX} textAnchor="middle">
          {formatearFechaCorta(puntos[i].fecha)}
        </text>
      ))}
    </svg>
  );
}
