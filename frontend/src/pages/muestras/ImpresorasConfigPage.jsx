import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../../context/AuthContext';
import TopBar from '../../components/TopBar';
import { muestrasApi } from '../../api/muestras';
import { ApiError } from '../../api/client';

const FORM_VACIO = {
  nombre: '', modelo: '', tipo_conexion: 'compartida', ruta_red: '',
  ip_directa: '', puerto_directo: 9100,
  resolucion_dpi: 203, ancho_mm: 100, alto_mm: 85, activa: true,
};

export default function ImpresorasConfigPage() {
  const navigate = useNavigate();
  const { user } = useAuth();
  const puedeGestionar = ['analista_qc', 'qa', 'admin'].includes(user?.rol);

  const [impresoras, setImpresoras] = useState([]);
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
      .listarImpresoras(null)
      .then(setImpresoras)
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

  function abrirEdicion(imp) {
    setEditandoId(imp.id_impresora);
    setForm({
      nombre: imp.nombre || '', modelo: imp.modelo || '',
      tipo_conexion: imp.tipo_conexion || 'compartida',
      ruta_red: imp.ruta_red || '', ip_directa: imp.ip_directa || '', puerto_directo: imp.puerto_directo || 9100,
      resolucion_dpi: imp.resolucion_dpi, ancho_mm: imp.ancho_mm, alto_mm: imp.alto_mm,
      activa: imp.activa,
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
    if (!form.nombre.trim() || !form.modelo.trim()) {
      setFormError('Nombre y modelo son obligatorios');
      return;
    }
    if (form.tipo_conexion === 'compartida' && !form.ruta_red.trim()) {
      setFormError('La ruta de red es obligatoria para una impresora compartida');
      return;
    }
    if (form.tipo_conexion === 'red_directa' && !form.ip_directa.trim()) {
      setFormError('La IP es obligatoria para una impresora de red directa');
      return;
    }
    setFormError('');
    setGuardando(true);
    try {
      const datos = {
        nombre: form.nombre.trim(),
        modelo: form.modelo.trim(),
        tipo_conexion: form.tipo_conexion,
        ruta_red: form.tipo_conexion === 'compartida' ? form.ruta_red.trim() : null,
        ip_directa: form.tipo_conexion === 'red_directa' ? form.ip_directa.trim() : null,
        puerto_directo: Number(form.puerto_directo) || 9100,
        resolucion_dpi: Number(form.resolucion_dpi),
        ancho_mm: Number(form.ancho_mm),
        alto_mm: Number(form.alto_mm),
      };
      if (editandoId) {
        await muestrasApi.editarImpresora(editandoId, { ...datos, activa: form.activa });
        setSuccessMsg('Impresora actualizada correctamente');
      } else {
        await muestrasApi.crearImpresora(datos);
        setSuccessMsg('Impresora creada correctamente');
      }
      cerrarForm();
      cargar();
    } catch (err) {
      setFormError(err instanceof ApiError ? err.message : 'No se pudo guardar la impresora');
    } finally {
      setGuardando(false);
    }
  }

  async function toggleEstado(imp) {
    try {
      await muestrasApi.cambiarEstadoImpresora(imp.id_impresora, !imp.activa);
      cargar();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'No se pudo cambiar el estado');
    }
  }

  return (
    <div className="screen">
      <TopBar titulo="Impresoras de Etiquetas" subtitulo="Muestras" onBack={() => navigate(-1)} />
      <div className="screen-content">
        <p style={{ color: 'var(--ink-2)', marginBottom: 'var(--sp-4)' }}>
          Impresoras SATO para impresión directa de etiquetas por SBPL, sin pasar por el software del fabricante --
          ver "Imprimir directo" en la pantalla de etiquetas de cada muestra. Compartida: conectada por USB a una PC
          y compartida en red (formato de ruta: <code>\\NOMBREPC\NombreCompartido</code>). Red directa: impresora con
          IP propia en la LAN, se le escribe directo por socket TCP.
        </p>

        {puedeGestionar && (
          <button className="btn btn-primary" style={{ marginBottom: 'var(--sp-4)' }} onClick={() => (mostrarForm ? cerrarForm() : abrirNuevo())}>
            {mostrarForm ? 'Cancelar' : '+ Nueva impresora'}
          </button>
        )}

        {successMsg && <div className="alert alert-ok" style={{ marginBottom: 'var(--sp-4)' }}>{successMsg}</div>}

        {puedeGestionar && mostrarForm && (
          <form onSubmit={handleSubmit} className="card" style={{ marginBottom: 'var(--sp-5)' }}>
            <h2 style={{ fontSize: 'var(--fs-lg)', marginBottom: 'var(--sp-3)' }}>
              {editandoId ? 'Editar impresora' : 'Nueva impresora'}
            </h2>
            <div className="field">
              <label className="field-label" htmlFor="nombre">Nombre</label>
              <input id="nombre" className="field-input" placeholder="Ej. SATO Muestreo" value={form.nombre} onChange={(e) => actualizarCampo('nombre', e.target.value)} disabled={guardando} />
            </div>
            <div className="field">
              <label className="field-label" htmlFor="modelo">Modelo</label>
              <input id="modelo" className="field-input" placeholder="Ej. CG40TT, WS408TT" value={form.modelo} onChange={(e) => actualizarCampo('modelo', e.target.value)} disabled={guardando} />
            </div>
            <div className="field">
              <label className="field-label" htmlFor="tipoConexion">Tipo de conexión</label>
              <select
                id="tipoConexion"
                className="field-input"
                value={form.tipo_conexion}
                onChange={(e) => actualizarCampo('tipo_conexion', e.target.value)}
                disabled={guardando}
              >
                <option value="compartida">Compartida (USB, en red desde una PC)</option>
                <option value="red_directa">Red directa (IP propia)</option>
              </select>
            </div>
            {form.tipo_conexion === 'compartida' ? (
              <div className="field">
                <label className="field-label" htmlFor="rutaRed">Ruta de red</label>
                <input id="rutaRed" className="field-input" placeholder="\\NOMBREPC\NombreCompartido" value={form.ruta_red} onChange={(e) => actualizarCampo('ruta_red', e.target.value)} disabled={guardando} />
              </div>
            ) : (
              <div style={{ display: 'flex', gap: 'var(--sp-3)' }}>
                <div className="field" style={{ flex: 2 }}>
                  <label className="field-label" htmlFor="ipDirecta">IP</label>
                  <input id="ipDirecta" className="field-input" placeholder="192.168.1.20" value={form.ip_directa} onChange={(e) => actualizarCampo('ip_directa', e.target.value)} disabled={guardando} />
                </div>
                <div className="field" style={{ flex: 1 }}>
                  <label className="field-label" htmlFor="puertoDirecto">Puerto</label>
                  <input id="puertoDirecto" className="field-input" type="number" value={form.puerto_directo} onChange={(e) => actualizarCampo('puerto_directo', e.target.value)} disabled={guardando} />
                </div>
              </div>
            )}
            <div style={{ display: 'flex', gap: 'var(--sp-3)' }}>
              <div className="field" style={{ flex: 1 }}>
                <label className="field-label" htmlFor="dpi">Resolución (DPI)</label>
                <input id="dpi" className="field-input" type="number" value={form.resolucion_dpi} onChange={(e) => actualizarCampo('resolucion_dpi', e.target.value)} disabled={guardando} />
              </div>
              <div className="field" style={{ flex: 1 }}>
                <label className="field-label" htmlFor="anchoMm">Ancho (mm)</label>
                <input id="anchoMm" className="field-input" type="number" value={form.ancho_mm} onChange={(e) => actualizarCampo('ancho_mm', e.target.value)} disabled={guardando} />
              </div>
              <div className="field" style={{ flex: 1 }}>
                <label className="field-label" htmlFor="altoMm">Alto (mm)</label>
                <input id="altoMm" className="field-input" type="number" value={form.alto_mm} onChange={(e) => actualizarCampo('alto_mm', e.target.value)} disabled={guardando} />
              </div>
            </div>
            {editandoId && (
              <label style={{ display: 'flex', alignItems: 'center', gap: 'var(--sp-2)', marginBottom: 'var(--sp-4)' }}>
                <input
                  type="checkbox"
                  checked={form.activa}
                  onChange={(e) => actualizarCampo('activa', e.target.checked)}
                  disabled={guardando}
                />
                Activa
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
        ) : impresoras.length === 0 ? (
          <div className="state-block"><span className="state-block-title">Sin impresoras configuradas</span></div>
        ) : (
          <div className="table-scroll">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Nombre</th>
                  <th>Modelo</th>
                  <th>Conexión</th>
                  <th>DPI</th>
                  <th>Tamaño (mm)</th>
                  <th>Estado</th>
                  {puedeGestionar && <th></th>}
                </tr>
              </thead>
              <tbody>
                {impresoras.map((imp) => (
                  <tr key={imp.id_impresora}>
                    <td>{imp.nombre}</td>
                    <td>{imp.modelo}</td>
                    <td style={{ fontFamily: 'var(--font-mono)' }}>
                      {imp.tipo_conexion === 'red_directa' ? `${imp.ip_directa}:${imp.puerto_directo}` : imp.ruta_red}
                    </td>
                    <td className="num">{imp.resolucion_dpi}</td>
                    <td className="num">{imp.ancho_mm} x {imp.alto_mm}</td>
                    <td><span className={imp.activa ? 'badge badge-ok' : 'badge badge-neutral'}>{imp.activa ? 'Activa' : 'Inactiva'}</span></td>
                    {puedeGestionar && (
                      <td style={{ display: 'flex', gap: 'var(--sp-2)', whiteSpace: 'nowrap' }}>
                        <button className="btn btn-ghost" onClick={() => abrirEdicion(imp)}>Editar</button>
                        <button className="btn btn-ghost" onClick={() => toggleEstado(imp)}>
                          {imp.activa ? 'Desactivar' : 'Activar'}
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
