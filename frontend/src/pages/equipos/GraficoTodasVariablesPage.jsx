import { useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import TopBar from '../../components/TopBar';
import { equiposApi } from '../../api/equipos';
import { ApiError } from '../../api/client';
import { GraficoLineas } from './GraficoLineas';

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

// Mismo gráfico de GraficoTendenciaPage.jsx (componente reutilizado, ver
// GraficoLineas.jsx), pero mostrando las 13 variables del equipo juntas en
// una grilla en vez de una por vez -- para ver de un vistazo el estado
// general del equipo en el período, sin tener que ir cambiando el selector
// de variable pantalla por pantalla.
export default function GraficoTodasVariablesPage() {
  const navigate = useNavigate();
  const selectorRef = useRef(null);

  const [equipos, setEquipos] = useState([]);
  const [idEquipo, setIdEquipo] = useState('');
  const [variables, setVariables] = useState([]);
  // Ids de variable a mostrar en la grilla -- por defecto todas (se
  // reinicia cada vez que cambian las variables del equipo elegido). Es un
  // filtro 100% client-side sobre los datos ya cargados: no dispara ningún
  // pedido nuevo al backend, así que no pasa por el botón "Generar".
  const [idsVisibles, setIdsVisibles] = useState([]);
  const [selectorAbierto, setSelectorAbierto] = useState(false);
  const [fechaDesde, setFechaDesde] = useState(hace30DiasISO());
  const [fechaHasta, setFechaHasta] = useState(hoyISO());
  const [lecturas, setLecturas] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    equiposApi.listar().then((data) => {
      setEquipos(data);
      if (data.length >= 1) setIdEquipo((prev) => prev || String(data[0].id_equipo));
    }).catch((err) => setError(err instanceof ApiError ? err.message : 'No se pudo cargar la pantalla'));
  }, []);

  useEffect(() => {
    if (!idEquipo) return;
    equiposApi.listarVariables(idEquipo).then(setVariables).catch(() => setVariables([]));
  }, [idEquipo]);

  useEffect(() => {
    setIdsVisibles(variables.map((v) => v.id_variable));
  }, [variables]);

  useEffect(() => {
    function handleClickFuera(e) {
      if (selectorRef.current && !selectorRef.current.contains(e.target)) setSelectorAbierto(false);
    }
    document.addEventListener('mousedown', handleClickFuera);
    return () => document.removeEventListener('mousedown', handleClickFuera);
  }, []);

  function toggleVariable(idVariable) {
    setIdsVisibles((prev) => (prev.includes(idVariable) ? prev.filter((id) => id !== idVariable) : [...prev, idVariable]));
  }

  // Carga las lecturas con el rango de fechas ACTUAL de los inputs -- se
  // llama automáticamente al cambiar de equipo (selección completa de un
  // <select>, sin riesgo de "valor a medio tipear"), y a demanda desde el
  // botón "Generar" para las fechas. Mismo criterio que
  // GraficoTendenciaPage.jsx/HistorialLecturasPage.jsx.
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

  const equipoElegido = equipos.find((eq) => String(eq.id_equipo) === idEquipo);

  // listarLecturas ya devuelve más recientes primero -- se invierte para
  // que cada gráfico corra en el tiempo de izquierda a derecha (mismo
  // criterio que GraficoTendenciaPage.jsx). Un array de puntos por
  // variable, calculado una sola vez acá en vez de adentro de cada card.
  const puntosPorVariable = variables
    .filter((v) => idsVisibles.includes(v.id_variable))
    .map((v) => ({
      variable: v,
      puntos: lecturas
        .slice()
        .reverse()
        .map((l) => {
          const val = l.valores.find((valor) => valor.id_variable === v.id_variable);
          return val ? { fecha: l.fecha, hora: l.hora, valor: val.valor, fueraDeRango: val.fuera_de_rango } : null;
        })
        .filter(Boolean),
    }));

  return (
    <div className="screen">
      <TopBar titulo="Gráfico de todas las variables" subtitulo="Equipos" onBack={() => navigate(-1)} />
      <div className="screen-content">
        <div className="card card-compact" style={{ marginBottom: 'var(--sp-3)' }}>
          <div style={{ display: 'flex', gap: 'var(--sp-3)', flexWrap: 'wrap', alignItems: 'flex-end' }}>
            <div className="field field-compact" style={{ flex: '1 1 220px' }}>
              <label className="field-label" htmlFor="equipo">Equipo</label>
              <select id="equipo" className="field-input" value={idEquipo} onChange={(e) => setIdEquipo(e.target.value)}>
                {equipos.map((eq) => (
                  <option key={eq.id_equipo} value={eq.id_equipo}>{eq.nombre}</option>
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
            <div className="field field-compact" style={{ flex: '1 1 220px', position: 'relative' }} ref={selectorRef}>
              <label className="field-label">Variables</label>
              <button
                type="button"
                className="field-input"
                style={{ textAlign: 'left', cursor: variables.length === 0 ? 'default' : 'pointer' }}
                onClick={() => variables.length > 0 && setSelectorAbierto((v) => !v)}
                disabled={variables.length === 0}
              >
                {variables.length === 0 ? '—' : `${idsVisibles.length} de ${variables.length} variables`}
              </button>
              {selectorAbierto && (
                <div
                  style={{
                    position: 'absolute', top: '100%', left: 0, right: 0, marginTop: 4,
                    background: 'var(--surf-1)', border: '1px solid var(--border)', borderRadius: 6,
                    boxShadow: '0 4px 12px rgba(0,0,0,0.2)', zIndex: 20, maxHeight: 280, overflowY: 'auto',
                    padding: 'var(--sp-2)',
                  }}
                >
                  <div style={{ display: 'flex', gap: 'var(--sp-3)', marginBottom: 'var(--sp-2)', paddingBottom: 'var(--sp-2)', borderBottom: '1px solid var(--border)' }}>
                    <button type="button" className="btn btn-ghost" style={{ padding: 0, minHeight: 'auto', fontSize: 'var(--fs-xs)' }} onClick={() => setIdsVisibles(variables.map((v) => v.id_variable))}>
                      Todas
                    </button>
                    <button type="button" className="btn btn-ghost" style={{ padding: 0, minHeight: 'auto', fontSize: 'var(--fs-xs)' }} onClick={() => setIdsVisibles([])}>
                      Ninguna
                    </button>
                  </div>
                  {variables.map((v) => (
                    <label key={v.id_variable} style={{ display: 'flex', alignItems: 'center', gap: 'var(--sp-2)', padding: '3px 0', fontSize: 'var(--fs-sm)', cursor: 'pointer' }}>
                      <input type="checkbox" checked={idsVisibles.includes(v.id_variable)} onChange={() => toggleVariable(v.id_variable)} />
                      {nombreVariable(v)}
                    </label>
                  ))}
                </div>
              )}
            </div>
            <button className="btn btn-primary" onClick={cargarLecturas} disabled={loading}>
              {loading ? <span className="spinner" /> : 'Generar →'}
            </button>
          </div>
        </div>

        {error && <div className="alert alert-danger" style={{ marginBottom: 'var(--sp-3)' }}>{error}</div>}

        {loading ? (
          <div className="state-block"><span className="spinner" /></div>
        ) : variables.length === 0 ? (
          <div className="state-block">
            <span className="state-block-title">Sin variables</span>
            <span>Este equipo no tiene variables configuradas</span>
          </div>
        ) : idsVisibles.length === 0 ? (
          <div className="state-block">
            <span className="state-block-title">Sin variables seleccionadas</span>
            <span>Elegí al menos una variable en el desplegable "Variables" para verla acá</span>
          </div>
        ) : (
          <div
            style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))',
              gap: 'var(--sp-3)',
            }}
          >
            {puntosPorVariable.map(({ variable, puntos }) => (
              <div key={variable.id_variable} className="card card-compact">
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', marginBottom: 'var(--sp-1)' }}>
                  <h3 style={{ fontSize: 'var(--fs-sm)', margin: 0 }}>{nombreVariable(variable)}</h3>
                  <span style={{ color: 'var(--ink-2)', fontSize: 'var(--fs-xs)' }}>
                    {puntos.length} lectura{puntos.length === 1 ? '' : 's'}
                  </span>
                </div>
                {puntos.length === 0 ? (
                  <div className="state-block" style={{ minHeight: 120 }}>
                    <span style={{ fontSize: 'var(--fs-xs)' }}>Sin datos en el rango</span>
                  </div>
                ) : (
                  <GraficoLineas
                    puntos={puntos}
                    limiteInferior={variable.limite_inferior}
                    limiteSuperior={variable.limite_superior}
                    unidad={variable.unidad_medida}
                    compacto
                  />
                )}
              </div>
            ))}
          </div>
        )}

        {!loading && variables.length > 0 && (
          <p style={{ color: 'var(--ink-2)', fontSize: 'var(--fs-xs)', marginTop: 'var(--sp-3)' }}>
            {equipoElegido?.nombre} -- Período: {fechaDesde || '...'} a {fechaHasta || '...'} -- líneas punteadas: rango aceptable -- puntos rojos: fuera de rango
          </p>
        )}
      </div>
    </div>
  );
}
