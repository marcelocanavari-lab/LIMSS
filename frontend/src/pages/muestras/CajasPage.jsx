import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../../context/AuthContext';
import TopBar from '../../components/TopBar';
import { cajasApi } from '../../api/cajas';
import { ApiError, abrirPdfConAuth } from '../../api/client';

const FORM_VACIO = { codigo: '', ubicacion: '', observaciones: '' };

function formatFechaHora(iso) {
  if (!iso) return '—';
  return new Date(iso).toLocaleString('es-AR', { day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit' });
}

export default function CajasPage() {
  const navigate = useNavigate();
  const { user } = useAuth();
  const puedeGestionar = ['analista_qc', 'qa', 'admin'].includes(user?.rol);

  const [cajas, setCajas] = useState([]);
  const [filtroEstado, setFiltroEstado] = useState('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [successMsg, setSuccessMsg] = useState('');
  const [fechaGeneracion, setFechaGeneracion] = useState(null);

  const [mostrarForm, setMostrarForm] = useState(false);
  const [form, setForm] = useState(FORM_VACIO);
  const [guardando, setGuardando] = useState(false);
  const [formError, setFormError] = useState('');

  const [seleccionadas, setSeleccionadas] = useState(new Set());

  function cargar() {
    setLoading(true);
    cajasApi
      .listar(filtroEstado || undefined)
      .then((data) => {
        setCajas(data);
        setFechaGeneracion(new Date());
      })
      .catch((err) => setError(err instanceof ApiError ? err.message : 'No se pudo cargar el listado'))
      .finally(() => setLoading(false));
  }

  useEffect(cargar, [filtroEstado]);

  useEffect(() => setSeleccionadas(new Set()), [filtroEstado, cajas.length]);

  function actualizarCampo(campo, valor) {
    setForm((prev) => ({ ...prev, [campo]: valor }));
  }

  async function abrirNuevo() {
    setForm(FORM_VACIO);
    setFormError('');
    setMostrarForm(true);
    try {
      const { codigo_sugerido } = await cajasApi.proximoCodigo();
      setForm((prev) => ({ ...prev, codigo: codigo_sugerido }));
    } catch {
      // sin sugerencia, el usuario carga el código a mano
    }
  }

  function cerrarForm() {
    setMostrarForm(false);
  }

  async function handleSubmit(e) {
    e.preventDefault();
    if (!form.codigo.trim()) {
      setFormError('El código es obligatorio');
      return;
    }
    setFormError('');
    setGuardando(true);
    try {
      await cajasApi.crear({
        codigo: form.codigo.trim(),
        ubicacion: form.ubicacion.trim() || null,
        observaciones: form.observaciones.trim() || null,
      });
      setSuccessMsg('Caja creada correctamente');
      cerrarForm();
      cargar();
    } catch (err) {
      setFormError(err instanceof ApiError ? err.message : 'No se pudo crear la caja');
    } finally {
      setGuardando(false);
    }
  }

  async function cerrarCaja(caja) {
    setError('');
    try {
      await cajasApi.cerrar(caja.id_caja);
      cargar();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'No se pudo cerrar la caja');
    }
  }

  async function reabrirCaja(caja) {
    setError('');
    try {
      await cajasApi.reabrir(caja.id_caja);
      cargar();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'No se pudo reabrir la caja');
    }
  }

  function toggleSeleccion(idCaja) {
    setSeleccionadas((prev) => {
      const next = new Set(prev);
      if (next.has(idCaja)) next.delete(idCaja);
      else next.add(idCaja);
      return next;
    });
  }

  async function imprimirEtiquetasSeleccionadas() {
    if (seleccionadas.size === 0) return;
    await abrirPdfConAuth(cajasApi.etiquetasUrl(Array.from(seleccionadas)));
  }

  return (
    <div className="screen">
      <TopBar titulo="Archivo de Contramuestras" subtitulo="Cajas" onBack={() => navigate(-1)} />
      <div className="screen-content">
        <div className="no-print" style={{ display: 'flex', gap: 'var(--sp-2)', marginBottom: 'var(--sp-4)', flexWrap: 'wrap', alignItems: 'center' }}>
          {puedeGestionar && (
            <button className="btn btn-primary" onClick={() => (mostrarForm ? cerrarForm() : abrirNuevo())}>
              {mostrarForm ? 'Cancelar' : '+ Nueva caja'}
            </button>
          )}
          <button className="btn btn-secondary" onClick={() => navigate('/cajas/buscar-producto')}>
            Buscar producto en cajas
          </button>
          <button className="btn btn-secondary" disabled={seleccionadas.size === 0} onClick={imprimirEtiquetasSeleccionadas}>
            Imprimir etiquetas seleccionadas ({seleccionadas.size})
          </button>
          <div style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: 'var(--sp-2)' }}>
            <label className="field-label" style={{ margin: 0 }}>Estado:</label>
            <select className="field-input" style={{ width: 'auto', height: 36 }} value={filtroEstado} onChange={(e) => setFiltroEstado(e.target.value)}>
              <option value="">Todas</option>
              <option value="activa">Activas</option>
              <option value="cerrada">Cerradas</option>
            </select>
          </div>
        </div>

        {successMsg && <div className="alert alert-ok no-print" style={{ marginBottom: 'var(--sp-4)' }}>{successMsg}</div>}

        {puedeGestionar && mostrarForm && (
          <form onSubmit={handleSubmit} className="card no-print" style={{ marginBottom: 'var(--sp-5)' }}>
            <h2 style={{ fontSize: 'var(--fs-lg)', marginBottom: 'var(--sp-3)' }}>Nueva caja</h2>
            <div className="field">
              <label className="field-label" htmlFor="codigo">Código</label>
              <input id="codigo" className="field-input" value={form.codigo} onChange={(e) => actualizarCampo('codigo', e.target.value)} disabled={guardando} autoFocus />
            </div>
            <div className="field">
              <label className="field-label" htmlFor="ubicacion">Ubicación física</label>
              <input id="ubicacion" className="field-input" value={form.ubicacion} onChange={(e) => actualizarCampo('ubicacion', e.target.value)} disabled={guardando} placeholder="Ej.: Depósito A, estante 3" />
            </div>
            <div className="field">
              <label className="field-label" htmlFor="observaciones">Observaciones</label>
              <input id="observaciones" className="field-input" value={form.observaciones} onChange={(e) => actualizarCampo('observaciones', e.target.value)} disabled={guardando} />
            </div>
            {formError && <div className="alert alert-danger" style={{ marginBottom: 'var(--sp-3)' }}>{formError}</div>}
            <button type="submit" className="btn btn-primary" disabled={guardando}>
              {guardando ? <span className="spinner" /> : 'Guardar'}
            </button>
          </form>
        )}

        {error && <div className="alert alert-danger no-print" style={{ marginBottom: 'var(--sp-4)' }}>{error}</div>}

        <div className="printable">
          <div className="no-print" style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: 'var(--sp-3)' }}>
            <button className="btn btn-secondary" onClick={() => window.print()}>Imprimir / Exportar PDF</button>
          </div>

          <h1 style={{ fontSize: 'var(--fs-lg)', marginBottom: 'var(--sp-2)' }}>Reporte de Cajas</h1>
          <p style={{ color: 'var(--ink-2)', marginBottom: 'var(--sp-4)' }}>
            Generado el {fechaGeneracion?.toLocaleString()} por {user?.nombre} {user?.apellido} ({user?.codigo}) —{' '}
            Estado: {filtroEstado === 'activa' ? 'Activas' : filtroEstado === 'cerrada' ? 'Cerradas' : 'Todas'} —{' '}
            {cajas.length} caja{cajas.length === 1 ? '' : 's'}
          </p>

          {loading ? (
            <div className="state-block"><span className="spinner" /></div>
          ) : cajas.length === 0 ? (
            <div className="state-block"><span className="state-block-title">Sin cajas para este filtro</span></div>
          ) : (
            <div className="reporte-tabla-scroll">
              <table className="data-table">
                <thead>
                  <tr>
                    <th className="no-print"></th>
                    <th>Código</th>
                    <th>Ubicación</th>
                    <th>Estado</th>
                    <th>Apertura</th>
                    <th>Cierre</th>
                    <th>Muestras</th>
                    <th className="no-print"></th>
                  </tr>
                </thead>
                <tbody>
                  {cajas.map((c) => (
                    <tr key={c.id_caja}>
                      <td className="no-print">
                        <input type="checkbox" checked={seleccionadas.has(c.id_caja)} onChange={() => toggleSeleccion(c.id_caja)} />
                      </td>
                      <td style={{ fontFamily: 'var(--font-mono)', cursor: 'pointer' }} onClick={() => navigate(`/cajas/${c.id_caja}`)}>
                        {c.codigo}
                      </td>
                      <td>{c.ubicacion || '—'}</td>
                      <td><span className={c.estado === 'activa' ? 'badge badge-ok' : 'badge badge-neutral'}>{c.estado === 'activa' ? 'Activa' : 'Cerrada'}</span></td>
                      <td style={{ whiteSpace: 'nowrap' }}>{formatFechaHora(c.fecha_apertura)}</td>
                      <td style={{ whiteSpace: 'nowrap' }}>{formatFechaHora(c.fecha_cierre)}</td>
                      <td className="num">{c.cantidad_muestras}</td>
                      <td className="no-print" style={{ display: 'flex', gap: 'var(--sp-2)', flexWrap: 'wrap' }}>
                        <button className="btn btn-ghost" onClick={() => navigate(`/cajas/${c.id_caja}`)}>Ver contenido</button>
                        {puedeGestionar && (
                          c.estado === 'activa' ? (
                            <>
                              <button className="btn btn-ghost" onClick={() => navigate(`/cajas/${c.id_caja}?asignar=1`)}>Asignar Contramuestras</button>
                              <button className="btn btn-ghost" onClick={() => cerrarCaja(c)}>Cerrar</button>
                            </>
                          ) : (
                            <button className="btn btn-ghost" onClick={() => reabrirCaja(c)}>Reabrir</button>
                          )
                        )}
                      </td>
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
