import { useEffect, useRef, useState } from 'react';
import { useNavigate, useParams, useSearchParams } from 'react-router-dom';
import { useAuth } from '../../context/AuthContext';
import TopBar from '../../components/TopBar';
import { cajasApi } from '../../api/cajas';
import { ApiError, abrirPdfConAuth } from '../../api/client';

function formatFechaHora(iso) {
  if (!iso) return '—';
  return new Date(iso).toLocaleString('es-AR', { day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit' });
}

export default function CajaDetallePage() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const { user } = useAuth();
  const puedeGestionar = ['analista_qc', 'qa', 'admin'].includes(user?.rol);
  const disponiblesRef = useRef(null);
  const yaAutoAbrio = useRef(false);

  const [caja, setCaja] = useState(null);
  const [historial, setHistorial] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [successMsg, setSuccessMsg] = useState('');
  const [fechaGeneracion, setFechaGeneracion] = useState(null);

  const [mostrarDisponibles, setMostrarDisponibles] = useState(false);
  const [disponibles, setDisponibles] = useState([]);
  const [filtroDisponibles, setFiltroDisponibles] = useState('');
  const [cargandoDisponibles, setCargandoDisponibles] = useState(false);
  const [seleccionadas, setSeleccionadas] = useState(new Set());
  const [agregando, setAgregando] = useState(false);
  const [disponiblesError, setDisponiblesError] = useState('');

  const puedeOperar = puedeGestionar && caja?.estado === 'activa';

  function cargar() {
    setLoading(true);
    setError('');
    cajasApi
      .detalle(id, historial)
      .then((data) => {
        setCaja(data);
        setFechaGeneracion(new Date());
      })
      .catch((err) => setError(err instanceof ApiError ? err.message : 'No se pudo cargar la caja'))
      .finally(() => setLoading(false));
  }

  useEffect(cargar, [id, historial]);

  function cargarDisponibles(buscar = filtroDisponibles) {
    setCargandoDisponibles(true);
    setDisponiblesError('');
    cajasApi
      .muestrasDisponibles(buscar)
      .then(setDisponibles)
      .catch((err) => {
        setDisponibles([]);
        setDisponiblesError(err instanceof ApiError ? err.message : 'No se pudo cargar la lista');
      })
      .finally(() => setCargandoDisponibles(false));
  }

  function abrirDisponibles() {
    setMostrarDisponibles(true);
    setSeleccionadas(new Set());
    cargarDisponibles('');
    setFiltroDisponibles('');
  }

  // Acceso directo desde "Asignar Contramuestras" en el listado de cajas
  // (CajasPage, fila de una caja activa, ?asignar=1) -- abre la sección de
  // selección múltiple automáticamente en vez de obligar a un clic extra
  // en "+ Agregar muestras" como paso intermedio.
  useEffect(() => {
    if (!yaAutoAbrio.current && searchParams.get('asignar') === '1' && puedeOperar) {
      yaAutoAbrio.current = true;
      abrirDisponibles();
      setTimeout(() => disponiblesRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' }), 100);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [puedeOperar]);

  function toggleSeleccion(idMuestra) {
    setSeleccionadas((prev) => {
      const next = new Set(prev);
      if (next.has(idMuestra)) next.delete(idMuestra);
      else next.add(idMuestra);
      return next;
    });
  }

  async function confirmarAgregado() {
    if (seleccionadas.size === 0) return;
    setAgregando(true);
    setDisponiblesError('');
    setSuccessMsg('');
    try {
      const resp = await cajasApi.agregarMuestras(id, Array.from(seleccionadas));
      const nAgregadas = resp.agregadas.length;
      if (resp.rechazadas.length > 0) {
        setDisponiblesError(
          `Se agregaron ${nAgregadas} de ${seleccionadas.size} -- rechazadas: ` +
          resp.rechazadas.map((r) => `${r.codigo_muestra || r.id_muestra} (${r.motivo})`).join('; '),
        );
      } else {
        setSuccessMsg(`${nAgregadas} muestra${nAgregadas === 1 ? '' : 's'} agregada${nAgregadas === 1 ? '' : 's'} correctamente`);
        setMostrarDisponibles(false);
      }
      setSeleccionadas(new Set());
      cargarDisponibles(filtroDisponibles);
      cargar();
    } catch (err) {
      setDisponiblesError(err instanceof ApiError ? err.message : 'No se pudo agregar las muestras');
    } finally {
      setAgregando(false);
    }
  }

  async function retirar(muestraEnCaja) {
    setError('');
    setSuccessMsg('');
    try {
      await cajasApi.retirarMuestra(id, muestraEnCaja.id_muestra);
      cargar();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'No se pudo retirar la muestra');
    }
  }

  async function imprimirEtiqueta() {
    await abrirPdfConAuth(cajasApi.etiquetaUrl(id));
  }

  if (loading && !caja) {
    return (
      <div className="screen">
        <TopBar titulo="Archivo de Contramuestras" subtitulo="Caja" onBack={() => navigate(-1)} />
        <div className="screen-content"><div className="state-block"><span className="spinner" /></div></div>
      </div>
    );
  }

  if (error && !caja) {
    return (
      <div className="screen">
        <TopBar titulo="Archivo de Contramuestras" subtitulo="Caja" onBack={() => navigate(-1)} />
        <div className="screen-content"><div className="alert alert-danger">{error}</div></div>
      </div>
    );
  }

  return (
    <div className="screen">
      <TopBar titulo={`Caja ${caja.codigo}`} subtitulo="Archivo de Contramuestras" onBack={() => navigate(-1)} />
      <div className="screen-content">
        <div className="card no-print" style={{ marginBottom: 'var(--sp-4)' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', flexWrap: 'wrap', gap: 'var(--sp-3)' }}>
            <div>
              <div><strong>Estado:</strong> <span className={caja.estado === 'activa' ? 'badge badge-ok' : 'badge badge-neutral'}>{caja.estado === 'activa' ? 'Activa' : 'Cerrada'}</span></div>
              <div><strong>Ubicación:</strong> {caja.ubicacion || '—'}</div>
              <div><strong>Apertura:</strong> {formatFechaHora(caja.fecha_apertura)} — {caja.usuario_apertura_nombre}</div>
              {caja.fecha_cierre && <div><strong>Último cierre:</strong> {formatFechaHora(caja.fecha_cierre)} — {caja.usuario_cierre_nombre}</div>}
              {caja.observaciones && <div><strong>Observaciones:</strong> {caja.observaciones}</div>}
            </div>
            <div style={{ display: 'flex', gap: 'var(--sp-2)', alignItems: 'flex-start' }}>
              <button className="btn btn-secondary" onClick={imprimirEtiqueta}>Imprimir etiqueta (A4)</button>
              {puedeGestionar && (
                caja.estado === 'activa' ? (
                  <button className="btn btn-secondary" onClick={async () => { await cajasApi.cerrar(id); cargar(); }}>Cerrar caja</button>
                ) : (
                  <button className="btn btn-secondary" onClick={async () => { await cajasApi.reabrir(id); cargar(); }}>Reabrir caja</button>
                )
              )}
            </div>
          </div>
        </div>

        {caja.estado !== 'activa' && (
          <div className="alert alert-warn no-print" style={{ marginBottom: 'var(--sp-4)' }}>
            Esta caja está cerrada -- reabrila para poder agregar o retirar muestras.
          </div>
        )}

        {successMsg && <div className="alert alert-ok no-print" style={{ marginBottom: 'var(--sp-4)' }}>{successMsg}</div>}

        {puedeOperar && (
          <div className="no-print" style={{ marginBottom: 'var(--sp-4)' }}>
            <button className="btn btn-primary" onClick={() => (mostrarDisponibles ? setMostrarDisponibles(false) : abrirDisponibles())}>
              {mostrarDisponibles ? 'Cancelar' : '+ Agregar muestras'}
            </button>
          </div>
        )}

        {puedeOperar && mostrarDisponibles && (
          <div ref={disponiblesRef} className="card no-print" style={{ marginBottom: 'var(--sp-5)' }}>
            <h2 style={{ fontSize: 'var(--fs-base)', marginBottom: 'var(--sp-3)' }}>Contramuestras libres (sin caja)</h2>
            <form
              onSubmit={(e) => { e.preventDefault(); cargarDisponibles(filtroDisponibles); }}
              style={{ display: 'flex', gap: 'var(--sp-2)', marginBottom: 'var(--sp-3)' }}
            >
              <input
                className="field-input"
                placeholder="Filtrar por código, material o IR (opcional)"
                value={filtroDisponibles}
                onChange={(e) => setFiltroDisponibles(e.target.value)}
              />
              <button type="submit" className="btn btn-secondary" disabled={cargandoDisponibles}>
                {cargandoDisponibles ? <span className="spinner" /> : 'Filtrar'}
              </button>
            </form>

            {disponiblesError && <div className="alert alert-danger" style={{ marginBottom: 'var(--sp-3)' }}>{disponiblesError}</div>}

            {cargandoDisponibles ? (
              <div className="state-block"><span className="spinner" /></div>
            ) : disponibles.length === 0 ? (
              <div className="state-block"><span className="state-block-title">Sin contramuestras libres para este filtro</span></div>
            ) : (
              <>
                <div className="table-scroll" style={{ maxHeight: 360, overflowY: 'auto' }}>
                  <table className="data-table">
                    <thead>
                      <tr>
                        <th></th>
                        <th>Código</th>
                        <th>Material</th>
                        <th>IR</th>
                        <th>Fecha de muestreo</th>
                      </tr>
                    </thead>
                    <tbody>
                      {disponibles.map((m) => (
                        <tr key={m.id_muestra} style={{ cursor: 'pointer' }} onClick={() => toggleSeleccion(m.id_muestra)}>
                          <td onClick={(e) => e.stopPropagation()}>
                            <input type="checkbox" checked={seleccionadas.has(m.id_muestra)} onChange={() => toggleSeleccion(m.id_muestra)} />
                          </td>
                          <td style={{ fontFamily: 'var(--font-mono)' }}>{m.codigo_muestra}</td>
                          <td>{m.erp_DESART} <span style={{ color: 'var(--ink-3)' }}>({m.erp_CODART.trim()})</span></td>
                          <td style={{ fontFamily: 'var(--font-mono)' }}>{m.erp_nro_ir || '—'}</td>
                          <td style={{ whiteSpace: 'nowrap' }}>{formatFechaHora(m.fecha_muestreo)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                <button
                  className="btn btn-primary"
                  style={{ marginTop: 'var(--sp-3)' }}
                  disabled={seleccionadas.size === 0 || agregando}
                  onClick={confirmarAgregado}
                >
                  {agregando ? <span className="spinner" /> : `Agregar seleccionadas (${seleccionadas.size})`}
                </button>
              </>
            )}
          </div>
        )}

        <div className="printable">
          <div className="no-print" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 'var(--sp-3)' }}>
            <label style={{ display: 'flex', alignItems: 'center', gap: 'var(--sp-2)', fontSize: 'var(--fs-sm)' }}>
              <input type="checkbox" checked={historial} onChange={(e) => setHistorial(e.target.checked)} />
              Ver historial completo (incluye retiradas)
            </label>
            <button className="btn btn-secondary" onClick={() => window.print()}>Imprimir / Exportar PDF</button>
          </div>

          <h1 style={{ fontSize: 'var(--fs-lg)', marginBottom: 'var(--sp-2)' }}>Contenido — Caja {caja.codigo}</h1>
          <p style={{ color: 'var(--ink-2)', marginBottom: 'var(--sp-4)' }}>
            Generado el {fechaGeneracion?.toLocaleString()} por {user?.nombre} {user?.apellido} ({user?.codigo})
            {historial ? ' — incluye historial completo' : ' — solo muestras actualmente archivadas'}
          </p>

          {error && <div className="alert alert-danger no-print" style={{ marginBottom: 'var(--sp-4)' }}>{error}</div>}

          {caja.muestras.length === 0 ? (
            <div className="state-block"><span className="state-block-title">Sin muestras {historial ? 'en el historial' : 'archivadas'}</span></div>
          ) : (
            <div className="reporte-tabla-scroll">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Código</th>
                    <th>Material</th>
                    <th>IR</th>
                    <th>Ingreso</th>
                    {historial && <th>Retiro</th>}
                    {puedeOperar && <th className="no-print"></th>}
                  </tr>
                </thead>
                <tbody>
                  {caja.muestras.map((m) => (
                    <tr key={m.id}>
                      <td style={{ fontFamily: 'var(--font-mono)' }}>{m.codigo_muestra}</td>
                      <td>{m.erp_DESART} <span style={{ color: 'var(--ink-3)' }}>({m.erp_CODART.trim()})</span></td>
                      <td style={{ fontFamily: 'var(--font-mono)' }}>{m.erp_nro_ir || '—'}</td>
                      <td style={{ whiteSpace: 'nowrap' }}>{formatFechaHora(m.fecha_ingreso)} — {m.usuario_ingreso_nombre}</td>
                      {historial && (
                        <td style={{ whiteSpace: 'nowrap' }}>{m.fecha_retiro ? `${formatFechaHora(m.fecha_retiro)} — ${m.usuario_retiro_nombre}` : '—'}</td>
                      )}
                      {puedeOperar && (
                        <td className="no-print">
                          {!m.fecha_retiro && (
                            <button className="btn btn-ghost" style={{ color: 'var(--danger)' }} onClick={() => retirar(m)}>Retirar</button>
                          )}
                        </td>
                      )}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
