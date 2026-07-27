import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../../context/AuthContext';
import TopBar from '../../components/TopBar';
import { maestrosApi } from '../../api/maestros';
import { ApiError } from '../../api/client';

const FORM_VACIO = { nombre_ensayo: '', bibliografia: '', observaciones: '' };

export default function CatalogoEnsayosPage() {
  const navigate = useNavigate();
  const { user } = useAuth();
  const puedeEliminar = ['qa', 'admin'].includes(user?.rol);

  const [ensayos, setEnsayos] = useState([]);
  const [buscar, setBuscar] = useState('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const [mostrarForm, setMostrarForm] = useState(false);
  const [editandoId, setEditandoId] = useState(null);
  const [form, setForm] = useState(FORM_VACIO);
  const [guardando, setGuardando] = useState(false);
  const [formError, setFormError] = useState('');

  function cargar() {
    setLoading(true);
    maestrosApi
      .listarEnsayosMaestro(buscar)
      .then(setEnsayos)
      .catch((err) => setError(err instanceof ApiError ? err.message : 'No se pudo cargar el catálogo'))
      .finally(() => setLoading(false));
  }

  useEffect(() => {
    const timer = setTimeout(cargar, 300);
    return () => clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [buscar]);

  function abrirNuevo() {
    setEditandoId(null);
    setForm(FORM_VACIO);
    setFormError('');
    setMostrarForm(true);
  }

  function abrirEdicion(en) {
    setEditandoId(en.id_ensayo_maestro);
    setForm({
      nombre_ensayo: en.nombre_ensayo,
      bibliografia: en.bibliografia || '',
      observaciones: en.observaciones || '',
    });
    setFormError('');
    setMostrarForm(true);
  }

  function cerrarForm() {
    setMostrarForm(false);
    setEditandoId(null);
  }

  async function handleSubmit(e) {
    e.preventDefault();
    if (!form.nombre_ensayo.trim()) {
      setFormError('El nombre del ensayo es obligatorio');
      return;
    }
    setFormError('');
    setGuardando(true);
    const body = {
      nombre_ensayo: form.nombre_ensayo.trim(),
      bibliografia: form.bibliografia.trim() || null,
      observaciones: form.observaciones.trim() || null,
    };
    try {
      if (editandoId) {
        await maestrosApi.editarEnsayoMaestro(editandoId, body);
      } else {
        await maestrosApi.crearEnsayoMaestro(body);
      }
      cerrarForm();
      cargar();
    } catch (err) {
      setFormError(err instanceof ApiError ? err.message : 'No se pudo guardar el ensayo');
    } finally {
      setGuardando(false);
    }
  }

  async function handleEliminar(en) {
    if (!window.confirm(`¿Confirmar eliminación del ensayo ${en.nombre_ensayo}?`)) return;
    setError('');
    try {
      await maestrosApi.eliminarEnsayoMaestro(en.id_ensayo_maestro);
      cargar();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'No se pudo eliminar el ensayo');
    }
  }

  return (
    <div className="screen">
      <TopBar titulo="Catálogo de Ensayos" subtitulo="Datos Maestros" onBack={() => navigate('/menu')} />
      <div className="screen-content">
        <div style={{ display: 'flex', gap: 'var(--sp-3)', marginBottom: 'var(--sp-4)', flexWrap: 'wrap' }}>
          <input
            className="field-input"
            style={{ flex: 1, minWidth: 200 }}
            placeholder="Buscar por nombre..."
            value={buscar}
            onChange={(e) => setBuscar(e.target.value)}
          />
          <button className="btn btn-primary" onClick={() => (mostrarForm ? cerrarForm() : abrirNuevo())}>
            {mostrarForm ? 'Cancelar' : '+ Nuevo ensayo'}
          </button>
        </div>

        {mostrarForm && (
          <form onSubmit={handleSubmit} className="card" style={{ marginBottom: 'var(--sp-5)' }}>
            <h2 style={{ fontSize: 'var(--fs-lg)', marginBottom: 'var(--sp-3)' }}>
              {editandoId ? 'Editar ensayo' : 'Nuevo ensayo'}
            </h2>

            <div className="field">
              <label className="field-label" htmlFor="nombre_ensayo">Nombre</label>
              <input
                id="nombre_ensayo"
                className="field-input"
                placeholder="Ej. pH, Aspecto, Valoración"
                value={form.nombre_ensayo}
                onChange={(e) => setForm((prev) => ({ ...prev, nombre_ensayo: e.target.value }))}
                disabled={guardando}
              />
            </div>

            <div className="field">
              <label className="field-label" htmlFor="bibliografia">Bibliografía</label>
              <input
                id="bibliografia"
                className="field-input"
                placeholder="Ej. USP, PE, Interna M-04"
                value={form.bibliografia}
                onChange={(e) => setForm((prev) => ({ ...prev, bibliografia: e.target.value }))}
                disabled={guardando}
              />
            </div>

            <div className="field" style={{ marginBottom: 0 }}>
              <label className="field-label" htmlFor="observaciones">Observaciones</label>
              <textarea
                id="observaciones"
                className="field-input"
                style={{ height: 96, paddingTop: 'var(--sp-2)' }}
                placeholder="Notas adicionales (opcional)"
                value={form.observaciones}
                onChange={(e) => setForm((prev) => ({ ...prev, observaciones: e.target.value }))}
                disabled={guardando}
              />
            </div>

            {formError && <div className="alert alert-danger" style={{ marginTop: 'var(--sp-3)' }}>{formError}</div>}
            <button type="submit" className="btn btn-primary" style={{ marginTop: 'var(--sp-4)' }} disabled={guardando}>
              {guardando ? <span className="spinner" /> : 'Guardar'}
            </button>
          </form>
        )}

        {error && <div className="alert alert-danger" style={{ marginBottom: 'var(--sp-4)' }}>{error}</div>}

        {loading ? (
          <div className="state-block"><span className="spinner" /></div>
        ) : ensayos.length === 0 ? (
          <div className="state-block"><span className="state-block-title">Sin ensayos en el catálogo</span></div>
        ) : (
          <div className="table-scroll">
            <table className="data-table data-table-catalogo">
              <thead>
                <tr>
                  <th>Nombre</th>
                  <th>Bibliografía</th>
                  <th>Observaciones</th>
                  <th>Especificaciones</th>
                  <th>Acciones</th>
                </tr>
              </thead>
              <tbody>
                {ensayos.map((en) => (
                  <tr key={en.id_ensayo_maestro}>
                    <td>{en.nombre_ensayo}</td>
                    <td>{en.bibliografia || '—'}</td>
                    <td>{en.observaciones || '—'}</td>
                    <td className="num">{en.cantidad_especificaciones}</td>
                    <td className="catalogo-acciones">
                      <button className="btn btn-ghost" onClick={() => abrirEdicion(en)}>Editar</button>
                      {puedeEliminar && (
                        <button
                          className="btn btn-ghost"
                          style={{ color: 'var(--danger)' }}
                          onClick={() => handleEliminar(en)}
                          disabled={en.cantidad_especificaciones > 0}
                          title={
                            en.cantidad_especificaciones > 0
                              ? `No se puede eliminar: está asignado a ${en.cantidad_especificaciones} especificaci${en.cantidad_especificaciones === 1 ? 'ón' : 'ones'}`
                              : undefined
                          }
                        >
                          Eliminar
                        </button>
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
  );
}
