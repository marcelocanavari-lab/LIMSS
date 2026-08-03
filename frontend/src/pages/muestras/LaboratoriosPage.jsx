import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../../context/AuthContext';
import TopBar from '../../components/TopBar';
import { muestrasApi } from '../../api/muestras';
import { ApiError } from '../../api/client';

const FORM_VACIO = { nombre: '', direccion: '', contacto: '', email: '', telefono: '', activo: true };
const CONTACTO_VACIO = { nombre: '', cargo: '', email: '', telefono: '' };

function ContactosModal({ laboratorio, puedeGestionar, puedeEliminar, onClose }) {
  const [contactos, setContactos] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const [mostrarForm, setMostrarForm] = useState(false);
  const [editandoId, setEditandoId] = useState(null);
  const [form, setForm] = useState(CONTACTO_VACIO);
  const [formActivo, setFormActivo] = useState(true);
  const [guardando, setGuardando] = useState(false);
  const [formError, setFormError] = useState('');

  function cargar() {
    setLoading(true);
    muestrasApi
      .listarContactos(laboratorio.id_laboratorio)
      .then(setContactos)
      .catch((err) => setError(err instanceof ApiError ? err.message : 'No se pudo cargar los contactos'))
      .finally(() => setLoading(false));
  }

  useEffect(cargar, [laboratorio.id_laboratorio]);

  function abrirNuevo() {
    setEditandoId(null);
    setForm(CONTACTO_VACIO);
    setFormActivo(true);
    setFormError('');
    setMostrarForm(true);
  }

  function abrirEdicion(c) {
    setEditandoId(c.id_contacto);
    setForm({ nombre: c.nombre || '', cargo: c.cargo || '', email: c.email || '', telefono: c.telefono || '' });
    setFormActivo(c.activo);
    setFormError('');
    setMostrarForm(true);
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
        cargo: form.cargo.trim() || null,
        email: form.email.trim() || null,
        telefono: form.telefono.trim() || null,
      };
      if (editandoId) {
        await muestrasApi.editarContacto(laboratorio.id_laboratorio, editandoId, { ...datos, activo: formActivo });
      } else {
        await muestrasApi.crearContacto(laboratorio.id_laboratorio, datos);
      }
      setMostrarForm(false);
      cargar();
    } catch (err) {
      setFormError(err instanceof ApiError ? err.message : 'No se pudo guardar el contacto');
    } finally {
      setGuardando(false);
    }
  }

  async function desactivar(c) {
    try {
      await muestrasApi.eliminarContacto(laboratorio.id_laboratorio, c.id_contacto);
      cargar();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'No se pudo desactivar el contacto');
    }
  }

  return (
    <div
      style={{
        position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.5)',
        display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 100, padding: 'var(--sp-4)',
      }}
      onClick={onClose}
    >
      <div
        className="card"
        style={{ width: '90%', maxWidth: 640, maxHeight: '90vh', overflowY: 'auto' }}
        onClick={(e) => e.stopPropagation()}
      >
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 'var(--sp-3)' }}>
          <h2 style={{ fontSize: 'var(--fs-lg)', margin: 0 }}>Contactos — {laboratorio.nombre}</h2>
          <button className="btn btn-ghost" onClick={onClose}>Cerrar</button>
        </div>

        {puedeGestionar && (
          <button className="btn btn-primary" style={{ marginBottom: 'var(--sp-3)' }} onClick={() => (mostrarForm ? setMostrarForm(false) : abrirNuevo())}>
            {mostrarForm ? 'Cancelar' : '+ Agregar contacto'}
          </button>
        )}

        {puedeGestionar && mostrarForm && (
          <form onSubmit={handleSubmit} className="card" style={{ background: 'var(--surf-2)', marginBottom: 'var(--sp-4)' }}>
            <div className="field">
              <label className="field-label" htmlFor="contactoNombre">Nombre</label>
              <input id="contactoNombre" className="field-input" value={form.nombre} onChange={(e) => setForm((p) => ({ ...p, nombre: e.target.value }))} disabled={guardando} autoFocus />
            </div>
            <div className="field">
              <label className="field-label" htmlFor="contactoCargo">Cargo</label>
              <input id="contactoCargo" className="field-input" value={form.cargo} onChange={(e) => setForm((p) => ({ ...p, cargo: e.target.value }))} disabled={guardando} />
            </div>
            <div className="field">
              <label className="field-label" htmlFor="contactoEmail">Email</label>
              <input id="contactoEmail" className="field-input" type="email" value={form.email} onChange={(e) => setForm((p) => ({ ...p, email: e.target.value }))} disabled={guardando} />
            </div>
            <div className="field">
              <label className="field-label" htmlFor="contactoTelefono">Teléfono</label>
              <input id="contactoTelefono" className="field-input" value={form.telefono} onChange={(e) => setForm((p) => ({ ...p, telefono: e.target.value }))} disabled={guardando} />
            </div>
            {editandoId && (
              <label style={{ display: 'flex', alignItems: 'center', gap: 'var(--sp-2)', marginBottom: 'var(--sp-4)' }}>
                <input type="checkbox" checked={formActivo} onChange={(e) => setFormActivo(e.target.checked)} disabled={guardando} />
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
        ) : contactos.length === 0 ? (
          <div className="state-block"><span className="state-block-title">Sin contactos cargados</span></div>
        ) : (
          <div className="table-scroll">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Nombre</th>
                  <th>Cargo</th>
                  <th>Email</th>
                  <th>Teléfono</th>
                  <th>Estado</th>
                  {puedeGestionar && <th></th>}
                </tr>
              </thead>
              <tbody>
                {contactos.map((c) => (
                  <tr key={c.id_contacto}>
                    <td>{c.nombre}</td>
                    <td>{c.cargo || '—'}</td>
                    <td>{c.email || '—'}</td>
                    <td>{c.telefono || '—'}</td>
                    <td><span className={c.activo ? 'badge badge-ok' : 'badge badge-neutral'}>{c.activo ? 'Activo' : 'Inactivo'}</span></td>
                    {puedeGestionar && (
                      <td style={{ display: 'flex', gap: 'var(--sp-2)' }}>
                        <button className="btn btn-ghost" onClick={() => abrirEdicion(c)}>Editar</button>
                        {puedeEliminar && c.activo && (
                          <button className="btn btn-ghost" style={{ color: 'var(--danger)' }} onClick={() => desactivar(c)}>Desactivar</button>
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
  );
}

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

  const [labContactos, setLabContactos] = useState(null);

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
      <TopBar titulo="Laboratorios" subtitulo="Muestras" onBack={() => navigate(-1)} />
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
                <th></th>
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
                  <td style={{ display: 'flex', gap: 'var(--sp-2)' }}>
                    <button className="btn btn-ghost" onClick={() => setLabContactos(l)}>Contactos</button>
                    {puedeGestionar && (
                      <>
                        <button className="btn btn-ghost" onClick={() => abrirEdicion(l)}>Editar</button>
                        <button className="btn btn-ghost" onClick={() => toggleEstado(l)}>
                          {l.activo ? 'Desactivar' : 'Activar'}
                        </button>
                      </>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          </div>
        )}

        {labContactos && (
          <ContactosModal
            laboratorio={labContactos}
            puedeGestionar={puedeGestionar}
            puedeEliminar={['qa', 'admin'].includes(user?.rol)}
            onClose={() => setLabContactos(null)}
          />
        )}
      </div>
    </div>
  );
}
