import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import TopBar from '../../components/TopBar';
import { equiposApi } from '../../api/equipos';
import { ApiError } from '../../api/client';

const FORM_VACIO = { nombre: '', descripcion: '', activo: true };

// ABM de Equipos (lims_equipos) -- antes la única forma de cargar un equipo
// nuevo era por SQL directo, lo que iba en contra de la idea original del
// módulo de Control de Variables de Equipos (que agregar un equipo sea un
// dato de tabla, no un cambio de código/base a mano). Mismo patrón visual
// que TestigoCategoriasPage.jsx (listado + form inline + baja lógica).
export default function EquiposPage() {
  const navigate = useNavigate();

  const [equipos, setEquipos] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [successMsg, setSuccessMsg] = useState('');

  const [mostrarForm, setMostrarForm] = useState(false);
  const [editandoId, setEditandoId] = useState(null);
  const [form, setForm] = useState(FORM_VACIO);
  const [guardando, setGuardando] = useState(false);
  const [formError, setFormError] = useState('');

  function cargar() {
    setLoading(true);
    equiposApi
      .listar(null)
      .then(setEquipos)
      .catch((err) => setError(err instanceof ApiError ? err.message : 'No se pudo cargar el listado'))
      .finally(() => setLoading(false));
  }

  useEffect(cargar, []);

  function actualizarCampo(campo, valor) {
    setForm((prev) => ({ ...prev, [campo]: valor }));
  }

  function abrirNuevo() {
    setEditandoId(null);
    setForm(FORM_VACIO);
    setFormError('');
    setMostrarForm(true);
  }

  function abrirEdicion(eq) {
    setEditandoId(eq.id_equipo);
    setForm({ nombre: eq.nombre, descripcion: eq.descripcion || '', activo: eq.activo });
    setFormError('');
    setMostrarForm(true);
  }

  function cerrarForm() {
    setMostrarForm(false);
    setEditandoId(null);
  }

  async function handleSubmit(e) {
    e.preventDefault();
    if (!form.nombre.trim()) {
      setFormError('Completá el nombre');
      return;
    }

    setFormError('');
    setGuardando(true);
    try {
      if (editandoId) {
        await equiposApi.editarEquipo(editandoId, {
          nombre: form.nombre.trim(),
          descripcion: form.descripcion.trim() || null,
          activo: form.activo,
        });
        setSuccessMsg('Equipo actualizado correctamente');
      } else {
        await equiposApi.crearEquipo({
          nombre: form.nombre.trim(),
          descripcion: form.descripcion.trim() || null,
        });
        setSuccessMsg('Equipo creado correctamente');
      }
      cerrarForm();
      cargar();
    } catch (err) {
      setFormError(err instanceof ApiError ? err.message : 'No se pudo guardar el equipo');
    } finally {
      setGuardando(false);
    }
  }

  async function toggleEstado(eq) {
    try {
      await equiposApi.editarEquipo(eq.id_equipo, {
        nombre: eq.nombre, descripcion: eq.descripcion, activo: !eq.activo,
      });
      cargar();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'No se pudo cambiar el estado');
    }
  }

  return (
    <div className="screen">
      <TopBar titulo="Equipos" subtitulo="Datos Maestros" onBack={() => navigate(-1)} />
      <div className="screen-content">
        <button className="btn btn-primary" style={{ marginBottom: 'var(--sp-4)' }} onClick={() => (mostrarForm ? cerrarForm() : abrirNuevo())}>
          {mostrarForm ? 'Cancelar' : '+ Nuevo equipo'}
        </button>

        {successMsg && <div className="alert alert-ok" style={{ marginBottom: 'var(--sp-4)' }}>{successMsg}</div>}

        {mostrarForm && (
          <form onSubmit={handleSubmit} className="card" style={{ marginBottom: 'var(--sp-5)', maxWidth: 480 }}>
            <h2 style={{ fontSize: 'var(--fs-lg)', marginBottom: 'var(--sp-3)' }}>
              {editandoId ? 'Editar equipo' : 'Nuevo equipo'}
            </h2>

            <div className="field">
              <label className="field-label" htmlFor="nombre">Nombre</label>
              <input
                id="nombre"
                className="field-input"
                placeholder="Ej. Equipo de Purificación de Agua"
                value={form.nombre}
                onChange={(e) => actualizarCampo('nombre', e.target.value)}
                disabled={guardando}
              />
            </div>

            <div className="field" style={{ marginBottom: editandoId ? 'var(--sp-3)' : 0 }}>
              <label className="field-label" htmlFor="descripcion">Descripción (opcional)</label>
              <input
                id="descripcion"
                className="field-input"
                value={form.descripcion}
                onChange={(e) => actualizarCampo('descripcion', e.target.value)}
                disabled={guardando}
              />
            </div>

            {editandoId && (
              <label style={{ display: 'flex', alignItems: 'center', gap: 'var(--sp-2)', marginBottom: 0, cursor: 'pointer' }}>
                <input
                  type="checkbox"
                  checked={form.activo}
                  onChange={(e) => actualizarCampo('activo', e.target.checked)}
                  disabled={guardando}
                />
                <span className="field-label" style={{ marginBottom: 0 }}>Activo</span>
              </label>
            )}

            {formError && <div className="alert alert-danger" style={{ marginTop: 'var(--sp-3)' }}>{formError}</div>}
            <button type="submit" className="btn btn-primary" style={{ marginTop: 'var(--sp-4)' }} disabled={guardando}>
              {guardando ? <span className="spinner" /> : 'Guardar'}
            </button>
          </form>
        )}

        {error && <div className="alert alert-danger" style={{ marginBottom: 'var(--sp-4)' }}>{error}</div>}

        {loading ? (
          <div className="state-block"><span className="spinner" /></div>
        ) : equipos.length === 0 ? (
          <div className="state-block"><span className="state-block-title">Sin equipos cargados</span></div>
        ) : (
          <div className="table-scroll">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Nombre</th>
                  <th>Descripción</th>
                  <th>Estado</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {equipos.map((eq) => (
                  <tr key={eq.id_equipo}>
                    <td>{eq.nombre}</td>
                    <td>{eq.descripcion || '—'}</td>
                    <td><span className={eq.activo ? 'badge badge-ok' : 'badge badge-neutral'}>{eq.activo ? 'Activo' : 'Inactivo'}</span></td>
                    <td style={{ display: 'flex', gap: 'var(--sp-2)', flexWrap: 'wrap' }}>
                      <button className="btn btn-ghost" onClick={() => navigate(`/maestros/equipos/${eq.id_equipo}/variables`)}>Variables</button>
                      <button className="btn btn-ghost" onClick={() => abrirEdicion(eq)}>Editar</button>
                      <button className="btn btn-ghost" onClick={() => toggleEstado(eq)}>
                        {eq.activo ? 'Desactivar' : 'Activar'}
                      </button>
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
