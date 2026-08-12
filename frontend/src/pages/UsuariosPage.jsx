import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import TopBar from '../components/TopBar';
import { authApi } from '../api/auth';
import { ApiError } from '../api/client';

const ROLES = [
  { value: 'muestreador', label: 'Muestreador' },
  { value: 'analista_qc', label: 'Analista QC' },
  { value: 'qa', label: 'QA' },
  { value: 'admin', label: 'Admin' },
];

const BADGE_ROL = {
  muestreador: 'badge-neutral',
  analista_qc: 'badge-info',
  qa: 'badge-warn',
  admin: 'badge-ok',
};

function labelRol(rol) {
  return ROLES.find((r) => r.value === rol)?.label || rol;
}

// Rol del usuario en el eBR -- sistema separado del LIMSS, con sus propios
// niveles de acceso. value: '' es el sentinel de "Sin acceso" en el <select>;
// se convierte a null antes de mandarlo al backend.
const ROLES_EBR = [
  { value: '', label: 'Sin acceso' },
  { value: 'operario', label: 'Operario' },
  { value: 'supervisor', label: 'Supervisor' },
  { value: 'qa', label: 'QA' },
  { value: 'admin', label: 'Admin' },
];

const BADGE_ROL_EBR = {
  operario: 'badge-neutral',
  supervisor: 'badge-info',
  qa: 'badge-warn',
  admin: 'badge-ok',
};

function labelRolEbr(rolEbr) {
  return ROLES_EBR.find((r) => r.value === rolEbr)?.label || rolEbr;
}

const FORM_VACIO = {
  codigo: '', nombre: '', apellido: '', pin: '', rol: 'muestreador',
  rolEbr: '', activoEbr: true, forzarCambioPin: true,
};

export default function UsuariosPage() {
  const { user } = useAuth();
  const navigate = useNavigate();

  const [usuarios, setUsuarios] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [successMsg, setSuccessMsg] = useState('');

  const [mostrarForm, setMostrarForm] = useState(false);
  const [editandoId, setEditandoId] = useState(null);
  const [form, setForm] = useState(FORM_VACIO);
  const [guardando, setGuardando] = useState(false);
  const [formError, setFormError] = useState('');

  const [resetPinId, setResetPinId] = useState(null);
  const [pinNuevo, setPinNuevo] = useState('');
  const [pinConfirmar, setPinConfirmar] = useState('');
  const [pinForzarCambio, setPinForzarCambio] = useState(true);
  const [pinError, setPinError] = useState('');
  const [pinGuardando, setPinGuardando] = useState(false);

  function cargar() {
    setLoading(true);
    authApi
      .listarUsuarios()
      .then(setUsuarios)
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

  function abrirEdicion(u) {
    setEditandoId(u.id_usuario);
    setForm({
      codigo: u.codigo, nombre: u.nombre, apellido: u.apellido, pin: '', rol: u.rol,
      rolEbr: u.rol_ebr || '', activoEbr: u.rol_ebr ? u.activo_ebr : true,
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
    if (!form.nombre.trim() || !form.apellido.trim() || (!editandoId && !form.codigo.trim())) {
      setFormError('Completá todos los campos obligatorios');
      return;
    }
    if (!editandoId && !/^\d{4,6}$/.test(form.pin)) {
      setFormError('El PIN inicial debe tener entre 4 y 6 dígitos');
      return;
    }

    setFormError('');
    setGuardando(true);
    try {
      const rolEbr = form.rolEbr || null;
      const activoEbr = rolEbr ? form.activoEbr : false;
      if (editandoId) {
        await authApi.editarUsuario(editandoId, {
          nombre: form.nombre.trim(),
          apellido: form.apellido.trim(),
          rol: form.rol,
          rol_ebr: rolEbr,
          activo_ebr: activoEbr,
        });
        setSuccessMsg('Usuario actualizado correctamente');
      } else {
        await authApi.crearUsuario({
          codigo: form.codigo.trim().toUpperCase(),
          nombre: form.nombre.trim(),
          apellido: form.apellido.trim(),
          pin: form.pin,
          rol: form.rol,
          rol_ebr: rolEbr,
          activo_ebr: activoEbr,
          forzar_cambio_pin: form.forzarCambioPin,
        });
        setSuccessMsg('Usuario creado correctamente');
      }
      cerrarForm();
      cargar();
    } catch (err) {
      setFormError(err instanceof ApiError ? err.message : 'No se pudo guardar el usuario');
    } finally {
      setGuardando(false);
    }
  }

  async function toggleEstado(u) {
    if (u.activo && !window.confirm(`¿Desactivar al usuario "${u.codigo}"?`)) return;
    try {
      await authApi.cambiarEstadoUsuario(u.id_usuario, !u.activo);
      cargar();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'No se pudo cambiar el estado');
    }
  }

  function abrirResetPin(u) {
    setResetPinId(u.id_usuario);
    setPinNuevo('');
    setPinConfirmar('');
    setPinForzarCambio(true);
    setPinError('');
  }

  function cerrarResetPin() {
    setResetPinId(null);
  }

  async function handleResetPin(e) {
    e.preventDefault();
    if (!/^\d{4,6}$/.test(pinNuevo)) {
      setPinError('El PIN debe tener entre 4 y 6 dígitos');
      return;
    }
    if (pinNuevo !== pinConfirmar) {
      setPinError('Los PIN no coinciden');
      return;
    }
    setPinError('');
    setPinGuardando(true);
    try {
      await authApi.resetearPin(resetPinId, pinNuevo, pinForzarCambio);
      setSuccessMsg('PIN reseteado correctamente');
      cerrarResetPin();
    } catch (err) {
      setPinError(err instanceof ApiError ? err.message : 'No se pudo resetear el PIN');
    } finally {
      setPinGuardando(false);
    }
  }

  return (
    <div className="screen">
      <TopBar titulo="Usuarios" subtitulo="Administración" onBack={() => navigate(-1)} />
      <div className="screen-content">
        <button className="btn btn-primary" style={{ marginBottom: 'var(--sp-4)' }} onClick={() => (mostrarForm ? cerrarForm() : abrirNuevo())}>
          {mostrarForm ? 'Cancelar' : '+ Nuevo usuario'}
        </button>

        {successMsg && <div className="alert alert-ok" style={{ marginBottom: 'var(--sp-4)' }}>{successMsg}</div>}

        {mostrarForm && (
          <form onSubmit={handleSubmit} className="card" style={{ marginBottom: 'var(--sp-5)' }}>
            <h2 style={{ fontSize: 'var(--fs-lg)', marginBottom: 'var(--sp-3)' }}>
              {editandoId ? 'Editar usuario' : 'Nuevo usuario'}
            </h2>

            <div className="field">
              <label className="field-label" htmlFor="codigo">Código</label>
              {editandoId ? (
                <input id="codigo" className="field-input" value={form.codigo} disabled />
              ) : (
                <input
                  id="codigo"
                  className="field-input"
                  placeholder="Ej. JPEREZ"
                  value={form.codigo}
                  onChange={(e) => actualizarCampo('codigo', e.target.value)}
                  disabled={guardando}
                />
              )}
            </div>

            <div className="field">
              <label className="field-label" htmlFor="nombre">Nombre</label>
              <input id="nombre" className="field-input" value={form.nombre} onChange={(e) => actualizarCampo('nombre', e.target.value)} disabled={guardando} />
            </div>

            <div className="field">
              <label className="field-label" htmlFor="apellido">Apellido</label>
              <input id="apellido" className="field-input" value={form.apellido} onChange={(e) => actualizarCampo('apellido', e.target.value)} disabled={guardando} />
            </div>

            {!editandoId && (
              <div className="field">
                <label className="field-label" htmlFor="pin">PIN inicial (4-6 dígitos)</label>
                <input
                  id="pin"
                  className="field-input"
                  type="password"
                  inputMode="numeric"
                  maxLength={6}
                  value={form.pin}
                  onChange={(e) => actualizarCampo('pin', e.target.value.replace(/\D/g, ''))}
                  disabled={guardando}
                />
              </div>
            )}

            {!editandoId && (
              <label style={{ display: 'flex', alignItems: 'center', gap: 'var(--sp-2)', marginBottom: 'var(--sp-3)', cursor: 'pointer' }}>
                <input
                  type="checkbox"
                  checked={form.forzarCambioPin}
                  onChange={(e) => actualizarCampo('forzarCambioPin', e.target.checked)}
                  disabled={guardando}
                />
                <span className="field-label" style={{ marginBottom: 0 }}>Forzar cambio de PIN en el próximo ingreso</span>
              </label>
            )}

            <div className="field">
              <label className="field-label" htmlFor="rol">Rol</label>
              <select id="rol" className="field-input" value={form.rol} onChange={(e) => actualizarCampo('rol', e.target.value)} disabled={guardando}>
                {ROLES.map((r) => (
                  <option key={r.value} value={r.value}>{r.label}</option>
                ))}
              </select>
            </div>

            <h3 style={{ fontSize: 'var(--fs-sm)', color: 'var(--ink-2)', margin: 'var(--sp-4) 0 var(--sp-2)' }}>
              Acceso al sistema eBR
            </h3>

            <div className="field" style={{ marginBottom: form.rolEbr ? 'var(--sp-3)' : 0 }}>
              <label className="field-label" htmlFor="rolEbr">Rol en eBR</label>
              <select
                id="rolEbr"
                className="field-input"
                value={form.rolEbr}
                onChange={(e) => actualizarCampo('rolEbr', e.target.value)}
                disabled={guardando}
              >
                {ROLES_EBR.map((r) => (
                  <option key={r.value} value={r.value}>{r.label}</option>
                ))}
              </select>
            </div>

            {form.rolEbr && (
              <label style={{ display: 'flex', alignItems: 'center', gap: 'var(--sp-2)', marginBottom: 0, cursor: 'pointer' }}>
                <input
                  type="checkbox"
                  checked={form.activoEbr}
                  onChange={(e) => actualizarCampo('activoEbr', e.target.checked)}
                  disabled={guardando}
                />
                <span className="field-label" style={{ marginBottom: 0 }}>Activo en eBR</span>
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
        ) : usuarios.length === 0 ? (
          <div className="state-block"><span className="state-block-title">Sin usuarios</span></div>
        ) : (
          <div className="table-scroll">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Código</th>
                  <th>Nombre</th>
                  <th>Apellido</th>
                  <th>Rol</th>
                  <th>Rol eBR</th>
                  <th>Estado</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {usuarios.map((u) => (
                  <tr key={u.id_usuario}>
                    <td style={{ fontFamily: 'var(--font-mono)' }}>{u.codigo}</td>
                    <td>{u.nombre}</td>
                    <td>{u.apellido}</td>
                    <td><span className={`badge ${BADGE_ROL[u.rol] || 'badge-neutral'}`}>{labelRol(u.rol)}</span></td>
                    <td>
                      {u.rol_ebr
                        ? <span className={`badge ${BADGE_ROL_EBR[u.rol_ebr] || 'badge-neutral'}`}>{labelRolEbr(u.rol_ebr)}</span>
                        : '—'}
                    </td>
                    <td><span className={u.activo ? 'badge badge-ok' : 'badge badge-danger'}>{u.activo ? 'Activo' : 'Inactivo'}</span></td>
                    <td style={{ display: 'flex', gap: 'var(--sp-2)', flexWrap: 'wrap' }}>
                      <button className="btn btn-ghost" onClick={() => abrirEdicion(u)}>Editar</button>
                      <button className="btn btn-ghost" onClick={() => abrirResetPin(u)}>Resetear PIN</button>
                      {u.id_usuario !== user?.id_usuario && (
                        <button className="btn btn-ghost" onClick={() => toggleEstado(u)}>
                          {u.activo ? 'Desactivar' : 'Activar'}
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

      {resetPinId && (
        <div
          style={{
            position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.5)',
            display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 100,
          }}
          onClick={cerrarResetPin}
        >
          <form
            onSubmit={handleResetPin}
            className="card"
            style={{ width: '90%', maxWidth: 360 }}
            onClick={(e) => e.stopPropagation()}
          >
            <h2 style={{ fontSize: 'var(--fs-lg)', marginBottom: 'var(--sp-3)' }}>Resetear PIN</h2>

            <div className="field">
              <label className="field-label" htmlFor="pinNuevo">Nuevo PIN (4-6 dígitos)</label>
              <input
                id="pinNuevo"
                className="field-input"
                type="password"
                inputMode="numeric"
                maxLength={6}
                value={pinNuevo}
                onChange={(e) => setPinNuevo(e.target.value.replace(/\D/g, ''))}
                disabled={pinGuardando}
                autoFocus
              />
            </div>

            <div className="field" style={{ marginBottom: 0 }}>
              <label className="field-label" htmlFor="pinConfirmar">Confirmar PIN</label>
              <input
                id="pinConfirmar"
                className="field-input"
                type="password"
                inputMode="numeric"
                maxLength={6}
                value={pinConfirmar}
                onChange={(e) => setPinConfirmar(e.target.value.replace(/\D/g, ''))}
                disabled={pinGuardando}
              />
            </div>

            <label style={{ display: 'flex', alignItems: 'center', gap: 'var(--sp-2)', marginTop: 'var(--sp-3)', marginBottom: 0, cursor: 'pointer' }}>
              <input
                type="checkbox"
                checked={pinForzarCambio}
                onChange={(e) => setPinForzarCambio(e.target.checked)}
                disabled={pinGuardando}
              />
              <span className="field-label" style={{ marginBottom: 0 }}>Forzar cambio de PIN en el próximo ingreso</span>
            </label>

            {pinError && <div className="alert alert-danger" style={{ marginTop: 'var(--sp-3)' }}>{pinError}</div>}

            <div style={{ display: 'flex', gap: 'var(--sp-3)', marginTop: 'var(--sp-4)' }}>
              <button type="button" className="btn btn-ghost" onClick={cerrarResetPin} disabled={pinGuardando}>Cancelar</button>
              <button type="submit" className="btn btn-primary" disabled={pinGuardando}>
                {pinGuardando ? <span className="spinner" /> : 'Guardar'}
              </button>
            </div>
          </form>
        </div>
      )}
    </div>
  );
}
