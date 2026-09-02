import { useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { useAuth } from '../../context/AuthContext';
import TopBar from '../../components/TopBar';
import { maestrosApi } from '../../api/maestros';
import { muestrasApi } from '../../api/muestras';
import { testigosRemitosApi } from '../../api/testigosRemitos';
import { ApiError, abrirPdfConAuth } from '../../api/client';

// new Date('YYYY-MM-DD') interpreta la fecha en UTC -- en huso horario
// negativo (Argentina, UTC-3) se corre un día para atrás al mostrarla con
// toLocaleDateString() (que usa la zona LOCAL). Se arma con las partes
// sueltas, sin pasar por Date, mismo criterio que en Equipos.
function formatearFecha(fechaISO) {
  const [anio, mes, dia] = fechaISO.split('-');
  return `${dia}/${mes}/${anio}`;
}

export default function TestigoDetallePage() {
  const { id } = useParams();
  const navigate = useNavigate();
  const { user } = useAuth();
  const puedeGestionar = ['analista_qc', 'qa', 'admin'].includes(user?.rol);
  const puedeQuitarLaboratorio = ['qa', 'admin'].includes(user?.rol);

  const [testigo, setTestigo] = useState(null);
  const [movimientos, setMovimientos] = useState([]);
  const [historialEnvios, setHistorialEnvios] = useState([]);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);

  const [laboratoriosDisponibles, setLaboratoriosDisponibles] = useState([]);
  const [idLaboratorioNuevo, setIdLaboratorioNuevo] = useState('');
  const [consumoNuevo, setConsumoNuevo] = useState('');
  const [unidadConsumoNuevo, setUnidadConsumoNuevo] = useState('mg');
  const [fechaEnvioNuevo, setFechaEnvioNuevo] = useState('');
  const [agregandoLab, setAgregandoLab] = useState(false);
  const [quitandoLab, setQuitandoLab] = useState(null);
  const [errorLab, setErrorLab] = useState('');

  const [editandoConsumoId, setEditandoConsumoId] = useState(null);
  const [consumoEditado, setConsumoEditado] = useState('');
  const [unidadConsumoEditado, setUnidadConsumoEditado] = useState('mg');
  const [fechaEnvioEditado, setFechaEnvioEditado] = useState('');
  const [guardandoConsumo, setGuardandoConsumo] = useState(false);

  const [ajusteCantidad, setAjusteCantidad] = useState('');
  const [ajusteObs, setAjusteObs] = useState('');
  const [ajustando, setAjustando] = useState(false);
  const [ajusteError, setAjusteError] = useState('');

  function cargar() {
    setLoading(true);
    Promise.all([maestrosApi.obtenerTestigo(id), maestrosApi.historialMovimientos(id), testigosRemitosApi.historialEnvios(id)])
      .then(([t, m, envios]) => {
        setTestigo(t);
        setMovimientos(m);
        setHistorialEnvios(envios);
      })
      .catch((err) => setError(err instanceof ApiError ? err.message : 'No se pudo cargar el testigo'))
      .finally(() => setLoading(false));
  }

  useEffect(cargar, [id]);

  useEffect(() => {
    muestrasApi.listarLaboratorios(true).then(setLaboratoriosDisponibles).catch(() => {});
  }, []);

  async function agregarLaboratorio() {
    if (!idLaboratorioNuevo) return;
    setErrorLab('');
    setAgregandoLab(true);
    try {
      const laboratorios = await maestrosApi.asignarLaboratorioTestigo(
        id, Number(idLaboratorioNuevo), consumoNuevo, unidadConsumoNuevo, fechaEnvioNuevo
      );
      setTestigo((prev) => ({ ...prev, laboratorios }));
      setIdLaboratorioNuevo('');
      setConsumoNuevo('');
      setUnidadConsumoNuevo('mg');
      setFechaEnvioNuevo('');
    } catch (err) {
      setErrorLab(err instanceof ApiError ? err.message : 'No se pudo asignar el laboratorio');
    } finally {
      setAgregandoLab(false);
    }
  }

  async function quitarLaboratorio(idLaboratorio) {
    setErrorLab('');
    setQuitandoLab(idLaboratorio);
    try {
      const laboratorios = await maestrosApi.desvincularLaboratorioTestigo(id, idLaboratorio);
      setTestigo((prev) => ({ ...prev, laboratorios }));
    } catch (err) {
      setErrorLab(err instanceof ApiError ? err.message : 'No se pudo quitar el laboratorio');
    } finally {
      setQuitandoLab(null);
    }
  }

  function abrirEdicionConsumo(l) {
    setEditandoConsumoId(l.id_laboratorio);
    setConsumoEditado(l.consumo_estimado != null ? String(l.consumo_estimado) : '');
    setUnidadConsumoEditado(l.unidad_consumo || 'mg');
    setFechaEnvioEditado(l.fecha_envio_real || '');
    setErrorLab('');
  }

  function cancelarEdicionConsumo() {
    setEditandoConsumoId(null);
  }

  async function guardarConsumo(idLaboratorio) {
    setErrorLab('');
    setGuardandoConsumo(true);
    try {
      const laboratorios = await maestrosApi.editarConsumoLaboratorioTestigo(
        id, idLaboratorio, consumoEditado, unidadConsumoEditado, fechaEnvioEditado
      );
      setTestigo((prev) => ({ ...prev, laboratorios }));
      setEditandoConsumoId(null);
    } catch (err) {
      setErrorLab(err instanceof ApiError ? err.message : 'No se pudo actualizar el consumo');
    } finally {
      setGuardandoConsumo(false);
    }
  }

  async function verCertificado() {
    try {
      await abrirPdfConAuth(`/api/maestros/testigos/${id}/certificado`);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'No se pudo descargar el certificado');
    }
  }

  async function toggleEstado() {
    try {
      await maestrosApi.cambiarEstadoTestigo(id, !testigo.activo);
      cargar();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'No se pudo cambiar el estado');
    }
  }

  async function handleAjuste(e) {
    e.preventDefault();
    setAjusteError('');
    const cantidad = Number(ajusteCantidad);
    if (!ajusteCantidad || Number.isNaN(cantidad) || cantidad === 0) {
      setAjusteError('Ingresá una cantidad distinta de cero');
      return;
    }
    setAjustando(true);
    try {
      await maestrosApi.ajustarStockTestigo(id, cantidad, ajusteObs.trim() || undefined);
      setAjusteCantidad('');
      setAjusteObs('');
      cargar();
    } catch (err) {
      setAjusteError(err instanceof ApiError ? err.message : 'No se pudo ajustar el stock');
    } finally {
      setAjustando(false);
    }
  }

  if (loading) {
    return (
      <div className="screen" style={{ alignItems: 'center', justifyContent: 'center' }}>
        <span className="spinner" />
      </div>
    );
  }

  if (error && !testigo) {
    return (
      <div className="screen">
        <TopBar titulo="Testigo" subtitulo="Datos Maestros" onBack={() => navigate(-1)} />
        <div className="screen-content">
          <div className="alert alert-danger">{error}</div>
        </div>
      </div>
    );
  }

  return (
    <div className="screen">
      <TopBar titulo={testigo.nombre} subtitulo={testigo.codigo} onBack={() => navigate(-1)} />
      <div className="screen-content">
        {error && <div className="alert alert-danger" style={{ marginBottom: 'var(--sp-4)' }}>{error}</div>}

        <div className="card" style={{ marginBottom: 'var(--sp-5)' }}>
          <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap', marginBottom: 'var(--sp-4)' }}>
            {testigo.vencido && <span className="badge badge-danger">Vencido</span>}
            {!testigo.vencido && testigo.por_vencer && <span className="badge badge-warn">Vence en menos de 30 días</span>}
            {!testigo.vencido && !testigo.por_vencer && !testigo.fecha_vencimiento && (
              <span className="badge badge-neutral">Sin vencimiento</span>
            )}
            {testigo.stock_bajo && <span className="badge badge-warn">Stock bajo</span>}
            <span className={testigo.activo ? 'badge badge-ok' : 'badge badge-neutral'}>
              {testigo.activo ? 'Activo' : 'Inactivo'}
            </span>
          </div>

          <table className="data-table">
            <tbody>
              <tr><td>Lote</td><td className="num" style={{ textAlign: 'left' }}>{testigo.nro_lote}</td></tr>
              <tr><td>N° de IR</td><td className="num" style={{ textAlign: 'left' }}>{testigo.nro_ir || '—'}</td></tr>
              <tr><td>Vencimiento</td><td className="num" style={{ textAlign: 'left' }}>{testigo.fecha_vencimiento || 'Sin vencimiento'}</td></tr>
              <tr><td>Stock actual</td><td className="num" style={{ textAlign: 'left' }}>{testigo.stock_actual} {testigo.unidad_medida || ''}</td></tr>
              <tr><td>Stock mínimo</td><td className="num" style={{ textAlign: 'left' }}>{testigo.stock_minimo} {testigo.unidad_medida || ''}</td></tr>
              <tr><td>Categoría</td><td style={{ textAlign: 'left' }}>{testigo.categoria_nombre || '—'}</td></tr>
              <tr><td>Origen</td><td style={{ textAlign: 'left' }}>{testigo.origen_nombre || '—'}</td></tr>
              <tr><td>Observaciones</td><td style={{ textAlign: 'left' }}>{testigo.observaciones || '—'}</td></tr>
            </tbody>
          </table>

          <div style={{ display: 'flex', gap: 'var(--sp-3)', marginTop: 'var(--sp-4)', flexWrap: 'wrap' }}>
            <button className="btn btn-secondary" onClick={verCertificado}>Ver certificado (PDF)</button>
            {puedeGestionar && (
              <button className="btn btn-secondary" onClick={() => navigate(`/maestros/testigos/${id}/editar`)}>
                Editar
              </button>
            )}
            {puedeGestionar && (
              <button className="btn btn-secondary" onClick={toggleEstado}>
                {testigo.activo ? 'Desactivar' : 'Activar'}
              </button>
            )}
          </div>
        </div>

        <div className="card" style={{ marginBottom: 'var(--sp-5)' }}>
          <h2 style={{ fontSize: 'var(--fs-lg)', marginBottom: 'var(--sp-3)' }}>Laboratorios asignados</h2>

          {testigo.laboratorios && testigo.laboratorios.length > 0 ? (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--sp-2)', marginBottom: 'var(--sp-3)' }}>
              {testigo.laboratorios.map((l) => (
                <div
                  key={l.id_laboratorio}
                  style={{ display: 'flex', flexDirection: 'column', gap: 'var(--sp-2)', padding: 'var(--sp-2) var(--sp-3)', background: 'var(--surf-1)', borderRadius: 6 }}
                >
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <span>{l.nombre}</span>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--sp-3)' }}>
                      <span style={{ color: 'var(--ink-2)', fontSize: 'var(--fs-sm)' }}>
                        Consumo estimado: {l.consumo_estimado != null ? `${l.consumo_estimado} ${l.unidad_consumo || ''}` : '—'}
                      </span>
                      <span style={{ color: 'var(--ink-2)', fontSize: 'var(--fs-sm)' }}>
                        Fecha de envío: {l.fecha_envio_real || '—'}
                      </span>
                      {puedeGestionar && editandoConsumoId !== l.id_laboratorio && (
                        <button
                          type="button"
                          className="btn btn-ghost"
                          style={{ padding: 0 }}
                          onClick={() => abrirEdicionConsumo(l)}
                        >
                          Editar consumo
                        </button>
                      )}
                      {puedeQuitarLaboratorio && (
                        <button
                          type="button"
                          className="btn btn-ghost"
                          style={{ color: 'var(--danger)', padding: 0 }}
                          onClick={() => quitarLaboratorio(l.id_laboratorio)}
                          disabled={quitandoLab === l.id_laboratorio}
                        >
                          {quitandoLab === l.id_laboratorio ? <span className="spinner" /> : 'Quitar'}
                        </button>
                      )}
                    </div>
                  </div>

                  {editandoConsumoId === l.id_laboratorio && (
                    <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--sp-3)', flexWrap: 'wrap' }}>
                      <div className="field" style={{ margin: 0, flex: '0 0 160px' }}>
                        <label className="field-label" style={{ fontSize: 'var(--fs-xs)' }}>Consumo estimado por análisis</label>
                        <input
                          className="field-input"
                          type="number"
                          step="any"
                          min="0"
                          value={consumoEditado}
                          onChange={(e) => setConsumoEditado(e.target.value)}
                          disabled={guardandoConsumo}
                        />
                      </div>
                      <div className="field" style={{ margin: 0, flex: '0 0 100px' }}>
                        <label className="field-label" style={{ fontSize: 'var(--fs-xs)' }}>Unidad</label>
                        <select
                          className="field-input"
                          value={unidadConsumoEditado}
                          onChange={(e) => setUnidadConsumoEditado(e.target.value)}
                          disabled={guardandoConsumo}
                        >
                          <option value="mg">mg</option>
                          <option value="ml">ml</option>
                        </select>
                      </div>
                      <div className="field" style={{ margin: 0, flex: '0 0 160px' }}>
                        <label className="field-label" style={{ fontSize: 'var(--fs-xs)' }}>Fecha de envío</label>
                        <input
                          className="field-input"
                          type="date"
                          value={fechaEnvioEditado}
                          onChange={(e) => setFechaEnvioEditado(e.target.value)}
                          disabled={guardandoConsumo}
                        />
                      </div>
                      <button
                        type="button"
                        className="btn btn-primary"
                        onClick={() => guardarConsumo(l.id_laboratorio)}
                        disabled={guardandoConsumo}
                      >
                        {guardandoConsumo ? <span className="spinner" /> : 'Guardar'}
                      </button>
                      <button
                        type="button"
                        className="btn btn-ghost"
                        onClick={cancelarEdicionConsumo}
                        disabled={guardandoConsumo}
                      >
                        Cancelar
                      </button>
                    </div>
                  )}
                </div>
              ))}
            </div>
          ) : (
            <p style={{ color: 'var(--ink-2)', marginBottom: 'var(--sp-3)' }}>Sin laboratorios asignados</p>
          )}

          {puedeGestionar && (
            <div style={{ display: 'flex', gap: 'var(--sp-3)', alignItems: 'center', flexWrap: 'wrap' }}>
              <select
                className="field-input"
                style={{ flex: 1, minWidth: 200 }}
                value={idLaboratorioNuevo}
                onChange={(e) => setIdLaboratorioNuevo(e.target.value)}
                disabled={agregandoLab}
              >
                <option value="">Seleccionar laboratorio...</option>
                {laboratoriosDisponibles
                  .filter((l) => !(testigo.laboratorios || []).some((tl) => tl.id_laboratorio === l.id_laboratorio))
                  .map((l) => (
                    <option key={l.id_laboratorio} value={l.id_laboratorio}>{l.nombre}</option>
                  ))}
              </select>
              <div className="field" style={{ margin: 0, flex: '0 0 200px' }}>
                <label className="field-label" style={{ fontSize: 'var(--fs-xs)' }}>Consumo estimado por análisis</label>
                <input
                  className="field-input"
                  type="number"
                  step="any"
                  min="0"
                  placeholder="Opcional"
                  value={consumoNuevo}
                  onChange={(e) => setConsumoNuevo(e.target.value)}
                  disabled={agregandoLab}
                />
              </div>
              <div className="field" style={{ margin: 0, flex: '0 0 100px' }}>
                <label className="field-label" style={{ fontSize: 'var(--fs-xs)' }}>Unidad</label>
                <select
                  className="field-input"
                  value={unidadConsumoNuevo}
                  onChange={(e) => setUnidadConsumoNuevo(e.target.value)}
                  disabled={agregandoLab}
                >
                  <option value="mg">mg</option>
                  <option value="ml">ml</option>
                </select>
              </div>
              <div className="field" style={{ margin: 0, flex: '0 0 160px' }}>
                <label className="field-label" style={{ fontSize: 'var(--fs-xs)' }}>Fecha de envío</label>
                <input
                  className="field-input"
                  type="date"
                  value={fechaEnvioNuevo}
                  onChange={(e) => setFechaEnvioNuevo(e.target.value)}
                  disabled={agregandoLab}
                />
              </div>
              <button
                type="button"
                className="btn btn-secondary"
                onClick={agregarLaboratorio}
                disabled={agregandoLab || !idLaboratorioNuevo}
              >
                {agregandoLab ? <span className="spinner" /> : '+ Agregar laboratorio'}
              </button>
            </div>
          )}

          {errorLab && <div className="alert alert-danger" style={{ marginTop: 'var(--sp-3)' }}>{errorLab}</div>}
        </div>

        {puedeGestionar && (
          <div className="card" style={{ marginBottom: 'var(--sp-5)' }}>
            <h2 style={{ fontSize: 'var(--fs-lg)', marginBottom: 'var(--sp-3)' }}>Ajustar stock</h2>
            <form onSubmit={handleAjuste}>
              <div style={{ display: 'flex', gap: 'var(--sp-3)', alignItems: 'flex-end', flexWrap: 'wrap' }}>
                <div className="field" style={{ flex: '0 0 160px' }}>
                  <label className="field-label">Cantidad (+/-)</label>
                  <input
                    className="field-input"
                    type="number"
                    step="any"
                    value={ajusteCantidad}
                    onChange={(e) => setAjusteCantidad(e.target.value)}
                    disabled={ajustando}
                  />
                </div>
                <div className="field" style={{ flex: 1, minWidth: 200 }}>
                  <label className="field-label">Motivo</label>
                  <input
                    className="field-input"
                    value={ajusteObs}
                    onChange={(e) => setAjusteObs(e.target.value)}
                    disabled={ajustando}
                  />
                </div>
                <button type="submit" className="btn btn-primary" disabled={ajustando} style={{ marginBottom: 'var(--sp-4)' }}>
                  {ajustando ? <span className="spinner" /> : 'Aplicar'}
                </button>
              </div>
              {ajusteError && <div className="alert alert-danger">{ajusteError}</div>}
            </form>
          </div>
        )}

        <h2 style={{ fontSize: 'var(--fs-lg)', marginBottom: 'var(--sp-3)' }}>Historial de movimientos</h2>
        {movimientos.length === 0 ? (
          <div className="state-block"><span>Sin movimientos registrados</span></div>
        ) : (
          <table className="data-table">
            <thead>
              <tr>
                <th>Fecha</th>
                <th>Tipo</th>
                <th>Cantidad</th>
                <th>Stock resultante</th>
                <th>Observaciones</th>
              </tr>
            </thead>
            <tbody>
              {movimientos.map((m) => (
                <tr key={m.id_movimiento}>
                  <td>{new Date(m.fecha_hora).toLocaleString()}</td>
                  <td>{m.tipo}</td>
                  <td className="num">{m.cantidad}</td>
                  <td className="num">{m.stock_resultante}</td>
                  <td>{m.observaciones || '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}

        <h2 style={{ fontSize: 'var(--fs-lg)', margin: 'var(--sp-5) 0 var(--sp-3)' }}>Historial de envíos</h2>
        {historialEnvios.length === 0 ? (
          <div className="state-block"><span>Este testigo todavía no se envió a ningún laboratorio</span></div>
        ) : (
          <table className="data-table">
            <thead>
              <tr>
                <th>Fecha</th>
                <th>Laboratorio</th>
                <th>Cantidad enviada</th>
                <th>N° Remito</th>
              </tr>
            </thead>
            <tbody>
              {historialEnvios.map((h) => (
                <tr key={h.id_remito}>
                  <td>{formatearFecha(h.fecha_envio)}</td>
                  <td>{h.laboratorio_nombre}</td>
                  <td className="num">{h.cantidad_enviada} {h.unidad}</td>
                  <td style={{ fontFamily: 'var(--font-mono)' }}>{h.nro_remito}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
