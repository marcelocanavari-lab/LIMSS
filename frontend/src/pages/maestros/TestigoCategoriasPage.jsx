import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import TopBar from '../../components/TopBar';
import { maestrosApi } from '../../api/maestros';
import { ApiError } from '../../api/client';

const FORM_VACIO = { codigo: '', nombre: '', activo: true };

export default function TestigoCategoriasPage() {
  const navigate = useNavigate();

  const [categorias, setCategorias] = useState([]);
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
    maestrosApi
      .listarCategoriasTestigo()
      .then(setCategorias)
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

  function abrirEdicion(c) {
    setEditandoId(c.id_categoria);
    setForm({ codigo: c.codigo, nombre: c.nombre, activo: c.activo });
    setFormError('');
    setMostrarForm(true);
  }

  function cerrarForm() {
    setMostrarForm(false);
    setEditandoId(null);
  }

  async function handleSubmit(e) {
    e.preventDefault();
    if (!form.codigo.trim() || !form.nombre.trim()) {
      setFormError('Completá todos los campos obligatorios');
      return;
    }

    setFormError('');
    setGuardando(true);
    try {
      if (editandoId) {
        await maestrosApi.editarCategoriaTestigo(editandoId, {
          codigo: form.codigo.trim().toUpperCase(),
          nombre: form.nombre.trim(),
          activo: form.activo,
        });
        setSuccessMsg('Categoría actualizada correctamente');
      } else {
        await maestrosApi.crearCategoriaTestigo({
          codigo: form.codigo.trim().toUpperCase(),
          nombre: form.nombre.trim(),
        });
        setSuccessMsg('Categoría creada correctamente');
      }
      cerrarForm();
      cargar();
    } catch (err) {
      setFormError(err instanceof ApiError ? err.message : 'No se pudo guardar la categoría');
    } finally {
      setGuardando(false);
    }
  }

  async function toggleEstado(c) {
    try {
      await maestrosApi.editarCategoriaTestigo(c.id_categoria, {
        codigo: c.codigo, nombre: c.nombre, activo: !c.activo,
      });
      cargar();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'No se pudo cambiar el estado');
    }
  }

  return (
    <div className="screen">
      <TopBar titulo="Categorías de Testigos" subtitulo="Administración" onBack={() => navigate(-1)} />
      <div className="screen-content">
        <button className="btn btn-primary" style={{ marginBottom: 'var(--sp-4)' }} onClick={() => (mostrarForm ? cerrarForm() : abrirNuevo())}>
          {mostrarForm ? 'Cancelar' : '+ Nueva categoría'}
        </button>

        {successMsg && <div className="alert alert-ok" style={{ marginBottom: 'var(--sp-4)' }}>{successMsg}</div>}

        {mostrarForm && (
          <form onSubmit={handleSubmit} className="card" style={{ marginBottom: 'var(--sp-5)', maxWidth: 420 }}>
            <h2 style={{ fontSize: 'var(--fs-lg)', marginBottom: 'var(--sp-3)' }}>
              {editandoId ? 'Editar categoría' : 'Nueva categoría'}
            </h2>

            <div className="field">
              <label className="field-label" htmlFor="codigo">Código</label>
              <input
                id="codigo"
                className="field-input"
                placeholder="Ej. ANTIBIOTICOS"
                value={form.codigo}
                onChange={(e) => actualizarCampo('codigo', e.target.value)}
                disabled={guardando}
              />
            </div>

            <div className="field" style={{ marginBottom: editandoId ? 'var(--sp-3)' : 0 }}>
              <label className="field-label" htmlFor="nombre">Nombre</label>
              <input
                id="nombre"
                className="field-input"
                value={form.nombre}
                onChange={(e) => actualizarCampo('nombre', e.target.value)}
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
                <span className="field-label" style={{ marginBottom: 0 }}>Activa</span>
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
        ) : categorias.length === 0 ? (
          <div className="state-block"><span className="state-block-title">Sin categorías cargadas</span></div>
        ) : (
          <div className="table-scroll">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Código</th>
                  <th>Nombre</th>
                  <th>Estado</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {categorias.map((c) => (
                  <tr key={c.id_categoria}>
                    <td style={{ fontFamily: 'var(--font-mono)' }}>{c.codigo}</td>
                    <td>{c.nombre}</td>
                    <td><span className={c.activo ? 'badge badge-ok' : 'badge badge-neutral'}>{c.activo ? 'Activa' : 'Inactiva'}</span></td>
                    <td style={{ display: 'flex', gap: 'var(--sp-2)', flexWrap: 'wrap' }}>
                      <button className="btn btn-ghost" onClick={() => abrirEdicion(c)}>Editar</button>
                      <button className="btn btn-ghost" onClick={() => toggleEstado(c)}>
                        {c.activo ? 'Desactivar' : 'Activar'}
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
