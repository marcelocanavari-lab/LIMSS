import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import TopBar from '../../components/TopBar';
import { equiposApi } from '../../api/equipos';
import { solicitudesMuestreoApi } from '../../api/solicitudesMuestreo';
import { ApiError } from '../../api/client';

function horaActual() {
  const d = new Date();
  return `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`;
}

function hoyISO() {
  return new Date().toISOString().slice(0, 10);
}

function formatearRango(limiteInferior, limiteSuperior) {
  if (limiteInferior !== null && limiteSuperior !== null) return `${limiteInferior} - ${limiteSuperior}`;
  if (limiteInferior !== null) return `≥ ${limiteInferior}`;
  if (limiteSuperior !== null) return `≤ ${limiteSuperior}`;
  return null;
}

function fueraDeRango(valor, limiteInferior, limiteSuperior) {
  if (valor === '' || valor === null || Number.isNaN(Number(valor))) return false;
  const n = Number(valor);
  if (limiteInferior !== null && n < limiteInferior) return true;
  if (limiteSuperior !== null && n > limiteSuperior) return true;
  return false;
}

// Bloques de variables CONSECUTIVAS con el mismo grupo (a diferencia de
// agrupar por clave en un Map, esto respeta el orden real de la planilla:
// si el mismo nombre de grupo apareciera dos veces separado por otra
// variable, queda como dos bloques -- lo que importa acá es qué columnas
// son adyacentes en la fila, para el colSpan del encabezado "Presión de"/
// "Caudal de". Las variables sueltas (ORP, pH, Conductividad) quedan cada
// una en su propio bloque sin grupo.
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

export default function NuevaLecturaPage() {
  const navigate = useNavigate();

  const [equipos, setEquipos] = useState([]);
  const [idEquipo, setIdEquipo] = useState('');
  const [variables, setVariables] = useState([]);
  const [fecha, setFecha] = useState(hoyISO());
  const [hora, setHora] = useState(horaActual());
  const [valores, setValores] = useState({}); // id_variable -> string
  const [usuariosActivos, setUsuariosActivos] = useState([]);
  const [idUsuarioRealizo, setIdUsuarioRealizo] = useState('');
  const [idUsuarioVerifico, setIdUsuarioVerifico] = useState('');
  const [loading, setLoading] = useState(true);
  const [guardando, setGuardando] = useState(false);
  const [error, setError] = useState('');
  const [mensajeOk, setMensajeOk] = useState('');

  useEffect(() => {
    Promise.all([
      equiposApi.listar().then((data) => {
        setEquipos(data);
        if (data.length === 1) setIdEquipo(String(data[0].id_equipo));
      }),
      solicitudesMuestreoApi.listarUsuariosActivos().then(setUsuariosActivos).catch(() => {}),
    ])
      .catch((err) => setError(err instanceof ApiError ? err.message : 'No se pudo cargar la pantalla'))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    if (!idEquipo) {
      setVariables([]);
      return;
    }
    equiposApi
      .listarVariables(idEquipo)
      .then((data) => {
        setVariables(data);
        setValores({});
      })
      .catch((err) => setError(err instanceof ApiError ? err.message : 'No se pudo cargar las variables del equipo'));
  }, [idEquipo]);

  function actualizarValor(idVariable, texto) {
    setValores((prev) => ({ ...prev, [idVariable]: texto }));
  }

  async function handleSubmit(e) {
    e.preventDefault();
    setError('');
    setMensajeOk('');

    if (!idEquipo) {
      setError('Seleccioná un equipo');
      return;
    }

    const valoresCargados = Object.entries(valores)
      .filter(([, texto]) => texto !== '' && texto !== null && texto !== undefined)
      .map(([idVariable, texto]) => ({ id_variable: Number(idVariable), valor: Number(texto) }));

    if (valoresCargados.length === 0) {
      setError('Cargá al menos un valor');
      return;
    }

    setGuardando(true);
    try {
      await equiposApi.crearLectura({
        id_equipo: Number(idEquipo),
        fecha,
        hora,
        id_usuario_realizo: idUsuarioRealizo ? Number(idUsuarioRealizo) : null,
        id_usuario_verifico: idUsuarioVerifico ? Number(idUsuarioVerifico) : null,
        valores: valoresCargados,
      });
      setMensajeOk('Lectura guardada correctamente');
      setValores({});
      setHora(horaActual());
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'No se pudo guardar la lectura');
    } finally {
      setGuardando(false);
    }
  }

  const bloques = bloquesConsecutivos(variables);

  return (
    <div className="screen">
      <TopBar titulo="Nueva Lectura" subtitulo="Equipos" onBack={() => navigate(-1)} />
      <div className="screen-content">
        {loading ? (
          <div className="state-block"><span className="spinner" /></div>
        ) : (
          <form onSubmit={handleSubmit}>
            <div className="card" style={{ marginBottom: 'var(--sp-4)' }}>
              <div style={{ display: 'flex', gap: 'var(--sp-3)', flexWrap: 'wrap' }}>
                <div className="field" style={{ flex: '1 1 240px' }}>
                  <label className="field-label" htmlFor="equipo">Equipo</label>
                  <select
                    id="equipo"
                    className="field-input"
                    value={idEquipo}
                    onChange={(e) => setIdEquipo(e.target.value)}
                    disabled={guardando}
                  >
                    <option value="">Seleccioná un equipo...</option>
                    {equipos.map((eq) => (
                      <option key={eq.id_equipo} value={eq.id_equipo}>{eq.nombre}</option>
                    ))}
                  </select>
                </div>
                <div className="field" style={{ flex: '1 1 160px' }}>
                  <label className="field-label" htmlFor="fecha">Fecha</label>
                  <input
                    id="fecha" className="field-input" type="date"
                    value={fecha} onChange={(e) => setFecha(e.target.value)} disabled={guardando}
                  />
                </div>
                <div className="field" style={{ flex: '1 1 120px' }}>
                  <label className="field-label" htmlFor="hora">Hora</label>
                  <input
                    id="hora" className="field-input" type="time"
                    value={hora} onChange={(e) => setHora(e.target.value)} disabled={guardando}
                  />
                </div>
              </div>
            </div>

            {idEquipo && variables.length === 0 && (
              <div className="alert alert-warn" style={{ marginBottom: 'var(--sp-4)' }}>
                Este equipo no tiene variables configuradas.
              </div>
            )}

            {variables.length > 0 && (
              <div className="card" style={{ marginBottom: 'var(--sp-4)' }}>
                {/* Las 13 variables en un solo renglón horizontal, igual que
                    la planilla Excel original -- encabezado de 2 filas
                    (grupo "Presión de"/"Caudal de" con colSpan sobre sus
                    columnas, variable suelta con rowSpan sobre las dos filas
                    de encabezado). Scroll horizontal propio (reporte-tabla-
                    scroll, mismo patrón que Libro de Ingresos/Reporte de
                    Testigos) en vez de achicar la letra hasta ilegible. */}
                <div className="reporte-tabla-scroll">
                  <table className="data-table equipos-tabla-variables">
                    <thead>
                      <tr>
                        {bloques.map((b, i) => (
                          b.grupo ? (
                            <th key={`g-${i}`} colSpan={b.vars.length} style={{ textAlign: 'center' }}>{b.grupo}</th>
                          ) : (
                            b.vars.map((v) => (
                              <th key={v.id_variable} rowSpan={2} style={{ verticalAlign: 'bottom' }}>{v.nombre}</th>
                            ))
                          )
                        ))}
                      </tr>
                      <tr>
                        {bloques.filter((b) => b.grupo).flatMap((b) => b.vars).map((v) => (
                          <th key={v.id_variable}>{v.nombre}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      <tr>
                        {variables.map((v) => {
                          const valorActual = valores[v.id_variable] ?? '';
                          const fuera = fueraDeRango(valorActual, v.limite_inferior, v.limite_superior);
                          const rango = formatearRango(v.limite_inferior, v.limite_superior);
                          return (
                            <td key={v.id_variable}>
                              <input
                                id={`var-${v.id_variable}`}
                                className="field-input"
                                type="number"
                                step="any"
                                style={{
                                  width: 100,
                                  ...(fuera ? { borderColor: 'var(--danger)', backgroundColor: 'var(--danger-soft)', color: 'var(--danger)' } : {}),
                                }}
                                value={valorActual}
                                onChange={(e) => actualizarValor(v.id_variable, e.target.value)}
                                disabled={guardando}
                                title={rango ? `Rango: ${rango}${v.unidad_medida ? ` ${v.unidad_medida}` : ''}` : undefined}
                              />
                              <div style={{ fontSize: 'var(--fs-xs)', color: 'var(--ink-3)', marginTop: 2, whiteSpace: 'nowrap' }}>
                                {rango}{v.unidad_medida ? ` ${v.unidad_medida}` : ''}
                              </div>
                            </td>
                          );
                        })}
                      </tr>
                    </tbody>
                  </table>
                </div>
              </div>
            )}

            {variables.length > 0 && (
              <div className="card" style={{ marginBottom: 'var(--sp-4)' }}>
                <div style={{ display: 'flex', gap: 'var(--sp-3)', flexWrap: 'wrap' }}>
                  <div className="field" style={{ flex: '1 1 240px' }}>
                    <label className="field-label" htmlFor="realizo">Realizó</label>
                    <select
                      id="realizo" className="field-input"
                      value={idUsuarioRealizo} onChange={(e) => setIdUsuarioRealizo(e.target.value)} disabled={guardando}
                    >
                      <option value="">Seleccioná un usuario...</option>
                      {usuariosActivos.map((u) => (
                        <option key={u.id_usuario} value={u.id_usuario}>{u.nombre_completo}</option>
                      ))}
                    </select>
                  </div>
                  <div className="field" style={{ flex: '1 1 240px' }}>
                    <label className="field-label" htmlFor="verifico">Verificó</label>
                    <select
                      id="verifico" className="field-input"
                      value={idUsuarioVerifico} onChange={(e) => setIdUsuarioVerifico(e.target.value)} disabled={guardando}
                    >
                      <option value="">Seleccioná un usuario...</option>
                      {usuariosActivos.map((u) => (
                        <option key={u.id_usuario} value={u.id_usuario}>{u.nombre_completo}</option>
                      ))}
                    </select>
                  </div>
                </div>
              </div>
            )}

            {error && <div className="alert alert-danger" style={{ marginBottom: 'var(--sp-4)' }}>{error}</div>}
            {mensajeOk && <div className="alert alert-ok" style={{ marginBottom: 'var(--sp-4)' }}>{mensajeOk}</div>}

            {variables.length > 0 && (
              <button type="submit" className="btn btn-primary btn-block" disabled={guardando}>
                {guardando ? <span className="spinner" /> : 'Guardar lectura'}
              </button>
            )}
          </form>
        )}
      </div>
    </div>
  );
}
