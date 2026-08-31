import { useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import TopBar from '../../components/TopBar';
import { equiposApi } from '../../api/equipos';
import { ApiError } from '../../api/client';

const FORM_VACIO = {
  codigo: '', nombre: '', grupo: '', unidad_medida: '',
  limite_inferior: '', limite_superior: '', orden: '', activo: true,
};

// ABM de Variables de un Equipo (lims_equipo_variables) -- mismo motivo que
// EquiposPage.jsx: antes solo se podía agregar/editar una variable (o
// ajustar sus límites) por SQL directo.
export default function EquipoVariablesPage() {
  const { id } = useParams();
  const navigate = useNavigate();

  const [equipo, setEquipo] = useState(null);
  const [variables, setVariables] = useState([]);
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
    setError('');
    Promise.all([
      equiposApi.listar(null).then((data) => {
        const eq = data.find((e) => String(e.id_equipo) === id);
        if (!eq) throw new ApiError(404, 'Equipo no encontrado');
        setEquipo(eq);
      }),
      equiposApi.listarVariables(id, null).then(setVariables),
    ])
      .catch((err) => setError(err instanceof ApiError ? err.message : 'No se pudo cargar el equipo'))
      .finally(() => setLoading(false));
  }

  useEffect(cargar, [id]);

  function actualizarCampo(campo, valor) {
    setForm((prev) => ({ ...prev, [campo]: valor }));
  }

  function abrirNuevo() {
    setEditandoId(null);
    const proximoOrden = variables.length > 0 ? Math.max(...variables.map((v) => v.orden)) + 1 : 1;
    setForm({ ...FORM_VACIO, orden: String(proximoOrden) });
    setFormError('');
    setMostrarForm(true);
  }

  function abrirEdicion(v) {
    setEditandoId(v.id_variable);
    setForm({
      codigo: v.codigo || '', nombre: v.nombre, grupo: v.grupo || '', unidad_medida: v.unidad_medida || '',
      limite_inferior: v.limite_inferior ?? '', limite_superior: v.limite_superior ?? '',
      orden: String(v.orden), activo: v.activo,
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
    if (!form.nombre.trim() || form.orden === '') {
      setFormError('Completá nombre y orden');
      return;
    }

    const cuerpo = {
      codigo: form.codigo.trim() || null,
      nombre: form.nombre.trim(),
      grupo: form.grupo.trim() || null,
      unidad_medida: form.unidad_medida.trim() || null,
      limite_inferior: form.limite_inferior === '' ? null : Number(form.limite_inferior),
      limite_superior: form.limite_superior === '' ? null : Number(form.limite_superior),
      orden: Number(form.orden),
    };

    setFormError('');
    setGuardando(true);
    try {
      if (editandoId) {
        await equiposApi.editarVariable(id, editandoId, { ...cuerpo, activo: form.activo });
        setSuccessMsg('Variable actualizada correctamente');
      } else {
        await equiposApi.crearVariable(id, cuerpo);
        setSuccessMsg('Variable creada correctamente');
      }
      cerrarForm();
      cargar();
    } catch (err) {
      setFormError(err instanceof ApiError ? err.message : 'No se pudo guardar la variable');
    } finally {
      setGuardando(false);
    }
  }

  async function toggleEstado(v) {
    try {
      await equiposApi.editarVariable(id, v.id_variable, {
        codigo: v.codigo, nombre: v.nombre, grupo: v.grupo, unidad_medida: v.unidad_medida,
        limite_inferior: v.limite_inferior, limite_superior: v.limite_superior, orden: v.orden,
        activo: !v.activo,
      });
      cargar();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'No se pudo cambiar el estado');
    }
  }

  return (
    <div className="screen">
      <TopBar titulo={equipo ? `Variables -- ${equipo.nombre}` : 'Variables'} subtitulo="Datos Maestros" onBack={() => navigate(-1)} />
      <div className="screen-content">
        <button className="btn btn-primary" style={{ marginBottom: 'var(--sp-4)' }} onClick={() => (mostrarForm ? cerrarForm() : abrirNuevo())}>
          {mostrarForm ? 'Cancelar' : '+ Nueva variable'}
        </button>

        {successMsg && <div className="alert alert-ok" style={{ marginBottom: 'var(--sp-4)' }}>{successMsg}</div>}

        {mostrarForm && (
          <form onSubmit={handleSubmit} className="card" style={{ marginBottom: 'var(--sp-5)', maxWidth: 640 }}>
            <h2 style={{ fontSize: 'var(--fs-lg)', marginBottom: 'var(--sp-3)' }}>
              {editandoId ? 'Editar variable' : 'Nueva variable'}
            </h2>

            <div style={{ display: 'flex', gap: 'var(--sp-3)', flexWrap: 'wrap' }}>
              <div className="field" style={{ flex: '1 1 160px' }}>
                <label className="field-label" htmlFor="codigo">Código (opcional)</label>
                <input id="codigo" className="field-input" placeholder="Ej. PI-08" value={form.codigo} onChange={(e) => actualizarCampo('codigo', e.target.value)} disabled={guardando} />
              </div>
              <div className="field" style={{ flex: '2 1 220px' }}>
                <label className="field-label" htmlFor="nombre">Nombre</label>
                <input id="nombre" className="field-input" value={form.nombre} onChange={(e) => actualizarCampo('nombre', e.target.value)} disabled={guardando} />
              </div>
              <div className="field" style={{ flex: '1 1 160px' }}>
                <label className="field-label" htmlFor="grupo">Grupo (opcional)</label>
                <input id="grupo" className="field-input" placeholder="Ej. Presión de" value={form.grupo} onChange={(e) => actualizarCampo('grupo', e.target.value)} disabled={guardando} />
              </div>
            </div>

            <div style={{ display: 'flex', gap: 'var(--sp-3)', flexWrap: 'wrap' }}>
              <div className="field" style={{ flex: '1 1 140px' }}>
                <label className="field-label" htmlFor="unidad">Unidad (opcional)</label>
                <input id="unidad" className="field-input" placeholder="Ej. bares" value={form.unidad_medida} onChange={(e) => actualizarCampo('unidad_medida', e.target.value)} disabled={guardando} />
              </div>
              <div className="field" style={{ flex: '1 1 140px' }}>
                <label className="field-label" htmlFor="limInf">Límite inferior (opcional)</label>
                <input id="limInf" className="field-input" type="number" step="any" value={form.limite_inferior} onChange={(e) => actualizarCampo('limite_inferior', e.target.value)} disabled={guardando} />
              </div>
              <div className="field" style={{ flex: '1 1 140px' }}>
                <label className="field-label" htmlFor="limSup">Límite superior (opcional)</label>
                <input id="limSup" className="field-input" type="number" step="any" value={form.limite_superior} onChange={(e) => actualizarCampo('limite_superior', e.target.value)} disabled={guardando} />
              </div>
              <div className="field" style={{ flex: '1 1 100px' }}>
                <label className="field-label" htmlFor="orden">Orden</label>
                <input id="orden" className="field-input" type="number" value={form.orden} onChange={(e) => actualizarCampo('orden', e.target.value)} disabled={guardando} />
              </div>
            </div>

            {editandoId && (
              <label style={{ display: 'flex', alignItems: 'center', gap: 'var(--sp-2)', marginBottom: 0, cursor: 'pointer' }}>
                <input type="checkbox" checked={form.activo} onChange={(e) => actualizarCampo('activo', e.target.checked)} disabled={guardando} />
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
        ) : variables.length === 0 ? (
          <div className="state-block"><span className="state-block-title">Este equipo todavía no tiene variables</span></div>
        ) : (
          <div className="table-scroll">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Orden</th>
                  <th>Código</th>
                  <th>Nombre</th>
                  <th>Grupo</th>
                  <th>Unidad</th>
                  <th>Límite inf.</th>
                  <th>Límite sup.</th>
                  <th>Estado</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {variables.map((v) => (
                  <tr key={v.id_variable}>
                    <td className="num">{v.orden}</td>
                    <td style={{ fontFamily: 'var(--font-mono)' }}>{v.codigo || '—'}</td>
                    <td>{v.nombre}</td>
                    <td>{v.grupo || '—'}</td>
                    <td>{v.unidad_medida || '—'}</td>
                    <td className="num">{v.limite_inferior ?? '—'}</td>
                    <td className="num">{v.limite_superior ?? '—'}</td>
                    <td><span className={v.activo ? 'badge badge-ok' : 'badge badge-neutral'}>{v.activo ? 'Activa' : 'Inactiva'}</span></td>
                    <td style={{ display: 'flex', gap: 'var(--sp-2)', flexWrap: 'wrap' }}>
                      <button className="btn btn-ghost" onClick={() => abrirEdicion(v)}>Editar</button>
                      <button className="btn btn-ghost" onClick={() => toggleEstado(v)}>
                        {v.activo ? 'Desactivar' : 'Activar'}
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
