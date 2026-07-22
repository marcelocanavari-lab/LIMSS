import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../../context/AuthContext';
import TopBar from '../../components/TopBar';
import { muestrasApi } from '../../api/muestras';
import { ApiError } from '../../api/client';

const FORM_VACIO = { nombre: '', direccion: '', contacto: '', email: '', telefono: '', activo: true };

export default function LaboratoriosPage() {
  const navigate = useNavigate();
  const { user } = useAuth();
  const puedeGestionar = ['analista_qc', 'qa', 'admin'].includes(user?.rol);

  const [laboratorios, setLaboratorios] = useState([]);
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
    muestrasApi
      .listarLaboratorios(null)
      .then(setLaboratorios)
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

  function abrirEdicion(lab) {
    setEditandoId(lab.id_laboratorio);
    setForm({
      nombre: lab.nombre || '',
      direccion: lab.direccion || '',
      contacto: lab.contacto || '',
      email: lab.email || '',
      telefono: lab.telefono || '',
      activo: lab.activo,
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
    if (!form.nombre.trim()) {
      setFormError('El nombre es obligatorio');
      return;
    }
    setFormError('');
    setGuardando(true);
    try {
      const datos = {
        nombre: form.nombre.trim(),
        direccion: form.direccion.trim() || null,
        contacto: form.contacto.trim() || null,
        email: form.email.trim() || null,
        telefono: form.telefono.trim() || null,
      };
      if (editandoId) {
        await muestrasApi.editarLaboratorio(editandoId, { ...datos, activo: form.activo });
        setSuccessMsg('Laboratorio actualizado correctamente');
      } else {
        await muestrasApi.crearLaboratorio(datos);
        setSuccessMsg('Laboratorio creado correctamente');
      }
      cerrarForm();
      cargar();
    } catch (err) {
      setFormError(err instanceof ApiError ? err.message : 'No se pudo guardar el laboratorio');
    } finally {
      setGuardando(false);
    }
  }

  async function toggleEstado(lab) {
    try {
      await muestrasApi.cambiarEstadoLaboratorio(lab.id_laboratorio, !lab.activo);
      cargar();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'No se pudo cambiar el estado');
    }
  }

  return (
    <div className="screen">
      <TopBar titulo="Laboratorios" subtitulo="Muestras" onBack={() => navigate('/menu')} />
      <div className="screen-content">
        {puedeGestionar && (
          <button className="btn btn-primary" style={{ marginBottom: 'var(--sp-4)' }} onClick={() => (mostrarForm ? cerrarForm() : abrirNuevo())}>
            {mostrarForm ? 'Cancelar' : '+ Nuevo laboratorio'}
          </button>
        )}

        {successMsg && <div className="alert alert-ok" style={{ marginBottom: 'var(--sp-4)' }}>{successMsg}</div>}

        {puedeGestionar && mostrarForm && (
          <form onSubmit={handleSubmit} className="card" style={{ marginBottom: 'var(--sp-5)' }}>
            <h2 style={{ fontSize: 'var(--fs-lg)', marginBottom: 'var(--sp-3)' }}>
              {editandoId ? 'Editar laboratorio' : 'Nuevo laboratorio'}
            </h2>
            <div className="field">
              <label className="field-label" htmlFor="nombre">Nombre</label>
              <input id="nombre" className="field-input" value={form.nombre} onChange={(e) => actualizarCampo('nombre', e.target.value)} disabled={guardando} />
            </div>
            <div className="field">
              <label className="field-label" htmlFor="direccion">Dirección</label>
              <input id="direccion" className="field-input" value={form.direccion} onChange={(e) => actualizarCampo('direccion', e.target.value)} disabled={guardando} />
            </div>
            <div className="field">
              <label className="field-label" htmlFor="contacto">Contacto</label>
              <input id="contacto" className="field-input" value={form.contacto} onChange={(e) => actualizarCampo('contacto', e.target.value)} disabled={guardando} />
            </div>
            <div className="field">
              <label className="field-label" htmlFor="email">Email</label>
              <input id="email" className="field-input" type="email" value={form.email} onChange={(e) => actualizarCampo('email', e.target.value)} disabled={guardando} />
            </div>
            <div className="field">
              <label className="field-label" htmlFor="telefono">Teléfono</label>
              <input id="telefono" className="field-input" value={form.telefono} onChange={(e) => actualizarCampo('telefono', e.target.value)} disabled={guardando} />
            </div>
            {editandoId && (
              <label style={{ display: 'flex', alignItems: 'center', gap: 'var(--sp-2)', marginBottom: 'var(--sp-4)' }}>
                <input
                  type="checkbox"
                  checked={form.activo}
                  onChange={(e) => actualizarCampo('activo', e.target.checked)}
                  disabled={guardando}
                />
                Activo
              </label>
            )}
            {formError && <div className="alert alert-danger" style={{ marginBottom: 'var(--sp-3)' }}>{formError}</div>}
            <button type="submit" className="btn btn-primary" disabled={guardando}>
              {guardando ? <span className="spinner" /> : 'Guardar'}
            </button>
          </form>
        )}

        {error && <div className="alert alert-danger" style={{ marginBottom: 'var(--sp-4)' }}>{error}</div>}

        {loading ? (
          <div className="state-block"><span className="spinner" /></div>
        ) : laboratorios.length === 0 ? (
          <div className="state-block"><span className="state-block-title">Sin laboratorios</span></div>
        ) : (
          <div className="table-scroll">
          <table className="data-table">
            <thead>
              <tr>
                <th>Nombre</th>
                <th>Contacto</th>
                <th>Email</th>
                <th>Teléfono</th>
                <th>Estado</th>
                {puedeGestionar && <th></th>}
              </tr>
            </thead>
            <tbody>
              {laboratorios.map((l) => (
                <tr key={l.id_laboratorio}>
                  <td>{l.nombre}</td>
                  <td>{l.contacto || '—'}</td>
                  <td>{l.email || '—'}</td>
                  <td>{l.telefono || '—'}</td>
                  <td><span className={l.activo ? 'badge badge-ok' : 'badge badge-neutral'}>{l.activo ? 'Activo' : 'Inactivo'}</span></td>
                  {puedeGestionar && (
                    <td style={{ display: 'flex', gap: 'var(--sp-2)' }}>
                      <button className="btn btn-ghost" onClick={() => abrirEdicion(l)}>Editar</button>
                      <button className="btn btn-ghost" onClick={() => toggleEstado(l)}>
                        {l.activo ? 'Desactivar' : 'Activar'}
                      </button>
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
  );
}
