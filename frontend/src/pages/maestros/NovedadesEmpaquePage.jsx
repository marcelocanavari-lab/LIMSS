import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../../context/AuthContext';
import TopBar from '../../components/TopBar';
import { novedadesEmpaqueApi } from '../../api/novedadesEmpaque';
import { materialesApi } from '../../api/materiales';
import { ApiError } from '../../api/client';

const FORM_VACIO = { erp_CODART: '', titulo: '', descripcion: '' };

function formatFechaHora(iso) {
  if (!iso) return '—';
  return new Date(iso).toLocaleString('es-AR', { day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit' });
}

function ResolverModal({ novedad, onClose, onResuelta }) {
  const [observaciones, setObservaciones] = useState('');
  const [guardando, setGuardando] = useState(false);
  const [error, setError] = useState('');

  async function handleResolver() {
    setGuardando(true);
    setError('');
    try {
      const actualizada = await novedadesEmpaqueApi.resolver(novedad.id_novedad, observaciones.trim() || null);
      onResuelta(actualizada);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'No se pudo marcar como resuelta');
    } finally {
      setGuardando(false);
    }
  }

  return (
    <div
      style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.5)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 100, padding: 'var(--sp-4)' }}
      onClick={onClose}
    >
      <div className="card" style={{ width: '90%', maxWidth: 520 }} onClick={(e) => e.stopPropagation()}>
        <h2 style={{ fontSize: 'var(--fs-lg)', marginBottom: 'var(--sp-2)' }}>Marcar como resuelta</h2>
        <p style={{ color: 'var(--ink-2)', marginBottom: 'var(--sp-3)' }}>
          <strong>{novedad.erp_CODART}</strong> — {novedad.titulo}
        </p>
        <div className="field">
          <label className="field-label" htmlFor="observacionesResolucion">Observaciones (opcional)</label>
          <textarea
            id="observacionesResolucion"
            className="field-input"
            rows={4}
            placeholder="Qué se verificó, en qué contexto..."
            value={observaciones}
            onChange={(e) => setObservaciones(e.target.value)}
            disabled={guardando}
          />
        </div>
        {error && <div className="alert alert-danger" style={{ marginBottom: 'var(--sp-3)' }}>{error}</div>}
        <div style={{ display: 'flex', gap: 'var(--sp-2)' }}>
          <button className="btn btn-ghost" onClick={onClose} disabled={guardando}>Cancelar</button>
          <button className="btn btn-primary" onClick={handleResolver} disabled={guardando}>
            {guardando ? <span className="spinner" /> : 'Confirmar'}
          </button>
        </div>
      </div>
    </div>
  );
}

export default function NovedadesEmpaquePage() {
  const navigate = useNavigate();
  const { user } = useAuth();
  const puedeGestionar = ['analista_qc', 'qa', 'admin'].includes(user?.rol);

  const [novedades, setNovedades] = useState([]);
  const [filtroEstado, setFiltroEstado] = useState('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [successMsg, setSuccessMsg] = useState('');

  const [mostrarForm, setMostrarForm] = useState(false);
  const [form, setForm] = useState(FORM_VACIO);
  const [articuloBuscar, setArticuloBuscar] = useState('');
  const [articulos, setArticulos] = useState([]);
  const [articuloElegido, setArticuloElegido] = useState(null);
  const [guardando, setGuardando] = useState(false);
  const [formError, setFormError] = useState('');

  const [resolviendo, setResolviendo] = useState(null);

  function cargar() {
    setLoading(true);
    novedadesEmpaqueApi
      .listar(filtroEstado || undefined)
      .then(setNovedades)
      .catch((err) => setError(err instanceof ApiError ? err.message : 'No se pudo cargar el listado'))
      .finally(() => setLoading(false));
  }

  useEffect(cargar, [filtroEstado]);

  useEffect(() => {
    if (articuloBuscar.trim().length < 2) {
      setArticulos([]);
      return;
    }
    const timer = setTimeout(() => {
      materialesApi.buscarMateriales('material_empaque', articuloBuscar).then(setArticulos).catch(() => setArticulos([]));
    }, 300);
    return () => clearTimeout(timer);
  }, [articuloBuscar]);

  function abrirNuevo() {
    setForm(FORM_VACIO);
    setArticuloBuscar('');
    setArticulos([]);
    setArticuloElegido(null);
    setFormError('');
    setMostrarForm(true);
  }

  function cerrarForm() {
    setMostrarForm(false);
  }

  function elegirArticulo(art) {
    setArticuloElegido(art);
    setForm((prev) => ({ ...prev, erp_CODART: art.CODART.trim() }));
    setArticuloBuscar('');
    setArticulos([]);
  }

  async function handleSubmit(e) {
    e.preventDefault();
    if (!form.erp_CODART.trim()) {
      setFormError('El código de artículo es obligatorio');
      return;
    }
    if (!form.titulo.trim()) {
      setFormError('El título es obligatorio');
      return;
    }
    if (!form.descripcion.trim()) {
      setFormError('La descripción es obligatoria');
      return;
    }
    setFormError('');
    setGuardando(true);
    try {
      await novedadesEmpaqueApi.crear({
        erp_CODART: form.erp_CODART.trim(),
        titulo: form.titulo.trim(),
        descripcion: form.descripcion.trim(),
      });
      setSuccessMsg('Novedad creada correctamente');
      cerrarForm();
      cargar();
    } catch (err) {
      setFormError(err instanceof ApiError ? err.message : 'No se pudo crear la novedad');
    } finally {
      setGuardando(false);
    }
  }

  return (
    <div className="screen">
      <TopBar titulo="Novedades de Empaque" subtitulo="Datos Maestros" onBack={() => navigate(-1)} />
      <div className="screen-content">
        <div style={{ display: 'flex', gap: 'var(--sp-2)', marginBottom: 'var(--sp-4)', flexWrap: 'wrap', alignItems: 'center' }}>
          {puedeGestionar && (
            <button className="btn btn-primary" onClick={() => (mostrarForm ? cerrarForm() : abrirNuevo())}>
              {mostrarForm ? 'Cancelar' : '+ Nueva novedad'}
            </button>
          )}
          <div style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: 'var(--sp-2)' }}>
            <label className="field-label" style={{ margin: 0 }}>Estado:</label>
            <select className="field-input" style={{ width: 'auto', height: 36 }} value={filtroEstado} onChange={(e) => setFiltroEstado(e.target.value)}>
              <option value="">Todas</option>
              <option value="pendiente">Pendientes</option>
              <option value="resuelta">Resueltas</option>
            </select>
          </div>
        </div>

        {successMsg && <div className="alert alert-ok" style={{ marginBottom: 'var(--sp-4)' }}>{successMsg}</div>}

        {puedeGestionar && mostrarForm && (
          <form onSubmit={handleSubmit} className="card" style={{ marginBottom: 'var(--sp-5)' }}>
            <h2 style={{ fontSize: 'var(--fs-lg)', marginBottom: 'var(--sp-3)' }}>Nueva novedad</h2>

            <div className="field">
              <label className="field-label" htmlFor="articuloBuscar">Artículo de empaque</label>
              {articuloElegido ? (
                <div className="select-item select-item-active" style={{ marginBottom: 'var(--sp-2)' }}>
                  <span className="select-item-main">
                    <span className="select-item-title">{articuloElegido.DESART}</span>
                    <span className="select-item-sub">{articuloElegido.CODART}</span>
                  </span>
                  <button type="button" className="btn btn-ghost" onClick={() => { setArticuloElegido(null); setForm((p) => ({ ...p, erp_CODART: '' })); }}>
                    Cambiar
                  </button>
                </div>
              ) : (
                <>
                  <input
                    id="articuloBuscar"
                    className="field-input"
                    placeholder="Buscar por código o nombre del artículo (mínimo 2 caracteres)"
                    value={articuloBuscar}
                    onChange={(e) => setArticuloBuscar(e.target.value)}
                    disabled={guardando}
                  />
                  {articulos.length > 0 && (
                    <div className="select-list" style={{ marginTop: 'var(--sp-2)' }}>
                      {articulos.map((a) => (
                        <button type="button" key={a.IdM21} className="select-item" onClick={() => elegirArticulo(a)}>
                          <span className="select-item-main">
                            <span className="select-item-title">{a.DESART}</span>
                            <span className="select-item-sub">{a.CODART}</span>
                          </span>
                        </button>
                      ))}
                    </div>
                  )}
                  <p style={{ fontSize: 'var(--fs-xs)', color: 'var(--ink-3)', marginTop: 'var(--sp-1)' }}>
                    Si no encontrás el artículo en el buscador, escribí el código directamente:
                  </p>
                  <input
                    className="field-input"
                    placeholder="Código de artículo (erp_CODART)"
                    value={form.erp_CODART}
                    onChange={(e) => setForm((p) => ({ ...p, erp_CODART: e.target.value }))}
                    disabled={guardando}
                  />
                </>
              )}
            </div>

            <div className="field">
              <label className="field-label" htmlFor="titulo">Título</label>
              <input
                id="titulo"
                className="field-input"
                value={form.titulo}
                onChange={(e) => setForm((p) => ({ ...p, titulo: e.target.value }))}
                disabled={guardando}
              />
            </div>

            <div className="field">
              <label className="field-label" htmlFor="descripcion">Descripción</label>
              <textarea
                id="descripcion"
                className="field-input"
                rows={4}
                value={form.descripcion}
                onChange={(e) => setForm((p) => ({ ...p, descripcion: e.target.value }))}
                disabled={guardando}
              />
            </div>

            {formError && <div className="alert alert-danger" style={{ marginBottom: 'var(--sp-3)' }}>{formError}</div>}
            <button type="submit" className="btn btn-primary" disabled={guardando}>
              {guardando ? <span className="spinner" /> : 'Guardar'}
            </button>
          </form>
        )}

        {error && <div className="alert alert-danger" style={{ marginBottom: 'var(--sp-4)' }}>{error}</div>}

        {loading ? (
          <div className="state-block"><span className="spinner" /></div>
        ) : novedades.length === 0 ? (
          <div className="state-block"><span className="state-block-title">Sin novedades para este filtro</span></div>
        ) : (
          <div className="table-scroll">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Artículo</th>
                  <th>Título</th>
                  <th>Estado</th>
                  <th>Carga</th>
                  <th>Resolución</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {novedades.map((n) => (
                  <tr key={n.id_novedad}>
                    <td>{n.erp_DESART || '—'} <span style={{ color: 'var(--ink-3)' }}>({n.erp_CODART.trim()})</span></td>
                    <td>{n.titulo}</td>
                    <td><span className={n.estado === 'pendiente' ? 'badge badge-warn' : 'badge badge-ok'}>{n.estado === 'pendiente' ? 'Pendiente' : 'Resuelta'}</span></td>
                    <td style={{ whiteSpace: 'nowrap' }}>{formatFechaHora(n.fecha_carga)} — {n.usuario_carga_nombre}</td>
                    <td style={{ whiteSpace: 'nowrap' }}>
                      {n.fecha_resolucion ? `${formatFechaHora(n.fecha_resolucion)} — ${n.usuario_resolucion_nombre}` : '—'}
                    </td>
                    <td>
                      {puedeGestionar && n.estado === 'pendiente' && (
                        <button className="btn btn-ghost" onClick={() => setResolviendo(n)}>Marcar como resuelta</button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {resolviendo && (
          <ResolverModal
            novedad={resolviendo}
            onClose={() => setResolviendo(null)}
            onResuelta={() => {
              setResolviendo(null);
              setSuccessMsg('Novedad marcada como resuelta');
              cargar();
            }}
          />
        )}
      </div>
    </div>
  );
}
