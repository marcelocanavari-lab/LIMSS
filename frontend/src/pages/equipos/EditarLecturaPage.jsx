import { useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import TopBar from '../../components/TopBar';
import { equiposApi } from '../../api/equipos';
import { solicitudesMuestreoApi } from '../../api/solicitudesMuestreo';
import { ApiError } from '../../api/client';

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

// Bloques de variables CONSECUTIVAS con el mismo grupo -- mismo criterio
// que NuevaLecturaPage.jsx/HistorialLecturasPage.jsx (duplicado a
// propósito, mismo patrón que el resto de este proyecto para helpers
// chicos, ver _se_superponen en impresion_sato.py).
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

// Editar Lectura -- corrige una lectura YA GUARDADA (valor cargado con
// error, fecha/hora, o quién la realizó/verificó). El equipo no se puede
// cambiar acá (ver LecturaUpdate en el backend): editar es corregir esta
// lectura puntual, no recargarla bajo otro equipo con otro juego de
// variables. Mismo formulario agrupado (Presión de/Caudal de/sueltas) que
// Nueva Lectura, pre-cargado con los valores actuales.
export default function EditarLecturaPage() {
  const { idLectura } = useParams();
  const navigate = useNavigate();

  const [variables, setVariables] = useState([]);
  const [nombreEquipo, setNombreEquipo] = useState('');
  const [fecha, setFecha] = useState('');
  const [hora, setHora] = useState('');
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
      equiposApi.obtenerLectura(idLectura),
      solicitudesMuestreoApi.listarUsuariosActivos().catch(() => []),
    ])
      .then(async ([lectura, usuarios]) => {
        setUsuariosActivos(usuarios);
        setNombreEquipo(lectura.equipo_nombre);
        setFecha(lectura.fecha);
        setHora(lectura.hora || '');
        setIdUsuarioRealizo(lectura.id_usuario_realizo ? String(lectura.id_usuario_realizo) : '');
        setIdUsuarioVerifico(lectura.id_usuario_verifico ? String(lectura.id_usuario_verifico) : '');

        // Todas las variables ACTIVAS del equipo (no solo las que esta
        // lectura ya tenía cargadas) -- para poder completar acá una que
        // antes había quedado vacía, igual que Nueva Lectura.
        const todasLasVariables = await equiposApi.listarVariables(lectura.id_equipo);
        setVariables(todasLasVariables);
        const valoresIniciales = {};
        lectura.valores.forEach((v) => { valoresIniciales[v.id_variable] = String(v.valor); });
        setValores(valoresIniciales);
      })
      .catch((err) => setError(err instanceof ApiError ? err.message : 'No se pudo cargar la lectura'))
      .finally(() => setLoading(false));
  }, [idLectura]);

  function actualizarValor(idVariable, texto) {
    setValores((prev) => ({ ...prev, [idVariable]: texto }));
  }

  async function handleSubmit(e) {
    e.preventDefault();
    setError('');
    setMensajeOk('');

    const valoresCargados = Object.entries(valores)
      .filter(([, texto]) => texto !== '' && texto !== null && texto !== undefined)
      .map(([idVariable, texto]) => ({ id_variable: Number(idVariable), valor: Number(texto) }));

    setGuardando(true);
    try {
      await equiposApi.editarLectura(idLectura, {
        fecha,
        hora,
        id_usuario_realizo: idUsuarioRealizo ? Number(idUsuarioRealizo) : null,
        id_usuario_verifico: idUsuarioVerifico ? Number(idUsuarioVerifico) : null,
        valores: valoresCargados,
      });
      setMensajeOk('Lectura actualizada correctamente');
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'No se pudo guardar la corrección');
    } finally {
      setGuardando(false);
    }
  }

  const bloques = bloquesConsecutivos(variables);

  return (
    <div className="screen">
      <TopBar titulo="Editar Lectura" subtitulo="Equipos" onBack={() => navigate(-1)} />
      <div className="screen-content">
        {loading ? (
          <div className="state-block"><span className="spinner" /></div>
        ) : (
          <form onSubmit={handleSubmit}>
            <div className="card" style={{ marginBottom: 'var(--sp-4)' }}>
              <div style={{ display: 'flex', gap: 'var(--sp-3)', flexWrap: 'wrap', alignItems: 'flex-end' }}>
                <div className="field" style={{ flex: '1 1 240px' }}>
                  <label className="field-label">Equipo</label>
                  <div className="field-input" style={{ background: 'var(--surf-2)', color: 'var(--ink-2)' }}>{nombreEquipo}</div>
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

            {variables.length > 0 && (
              <div className="card" style={{ marginBottom: 'var(--sp-4)' }}>
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
                <p style={{ fontSize: 'var(--fs-xs)', color: 'var(--ink-3)', marginTop: 'var(--sp-2)' }}>
                  Vaciar un campo borra ese valor de la lectura (por si se cargó por error).
                </p>
              </div>
            )}

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

            {error && <div className="alert alert-danger" style={{ marginBottom: 'var(--sp-4)' }}>{error}</div>}
            {mensajeOk && <div className="alert alert-ok" style={{ marginBottom: 'var(--sp-4)' }}>{mensajeOk}</div>}

            <button type="submit" className="btn btn-primary btn-block" disabled={guardando}>
              {guardando ? <span className="spinner" /> : 'Guardar corrección'}
            </button>
          </form>
        )}
      </div>
    </div>
  );
}
