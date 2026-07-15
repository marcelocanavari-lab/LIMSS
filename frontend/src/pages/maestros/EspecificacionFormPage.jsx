import { useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import TopBar from '../../components/TopBar';
import { maestrosApi } from '../../api/maestros';
import { materialesApi } from '../../api/materiales';
import { ApiError } from '../../api/client';

const ENSAYO_VACIO = {
  orden: 1,
  nombre_ensayo: '',
  metodologia: '',
  tipo_dato: 'numerico',
  limite_inferior: '',
  limite_superior: '',
  unidad_medida: '',
  valor_requerido: '',
  obligatorio: true,
  observaciones: '',
};

const TIPOS_MATERIAL = [
  { value: 'materia_prima', label: 'Materia Prima' },
  { value: 'granel', label: 'Granel' },
  { value: 'semi_elaborado', label: 'Semi-Elaborado' },
  { value: 'producto_terminado', label: 'Producto Terminado' },
];

function labelTipo(valor) {
  return TIPOS_MATERIAL.find((t) => t.value === valor)?.label || valor;
}

export default function EspecificacionFormPage({ modo }) {
  const { id } = useParams();
  const navigate = useNavigate();
  const esRevision = modo === 'revisar';

  // Wizard de selección (solo aplica en modo "crear"; en "revisar" el
  // artículo y el tipo ya vienen fijos de la especificación existente).
  const [paso, setPaso] = useState(1);

  const [articuloBuscar, setArticuloBuscar] = useState('');
  const [articulos, setArticulos] = useState([]);
  const [articulo, setArticulo] = useState(null);
  const [tipoMaterial, setTipoMaterial] = useState('');
  const [ensayos, setEnsayos] = useState([{ ...ENSAYO_VACIO }]);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(esRevision);
  const [guardando, setGuardando] = useState(false);

  useEffect(() => {
    if (!esRevision) return;
    maestrosApi
      .obtenerEspecificacion(id)
      .then((esp) => {
        setArticulo({ IdM21: esp.erp_IdM21, CODART: esp.erp_CODART, DESART: esp.erp_DESART });
        setTipoMaterial(esp.tipo_material);
        setEnsayos(
          esp.ensayos.map((en) => ({
            orden: en.orden,
            nombre_ensayo: en.nombre_ensayo,
            metodologia: en.metodologia || '',
            tipo_dato: en.tipo_dato,
            limite_inferior: en.limite_inferior ?? '',
            limite_superior: en.limite_superior ?? '',
            unidad_medida: en.unidad_medida || '',
            valor_requerido: en.valor_requerido || '',
            obligatorio: en.obligatorio,
            observaciones: en.observaciones || '',
          }))
        );
      })
      .catch((err) => setError(err instanceof ApiError ? err.message : 'No se pudo cargar la especificación'))
      .finally(() => setLoading(false));
  }, [esRevision, id]);

  useEffect(() => {
    if (esRevision || paso !== 2 || articuloBuscar.trim().length < 2) {
      setArticulos([]);
      return;
    }
    const timer = setTimeout(() => {
      materialesApi
        .buscarMateriales(tipoMaterial, articuloBuscar)
        .then(setArticulos)
        .catch(() => setArticulos([]));
    }, 300);
    return () => clearTimeout(timer);
  }, [articuloBuscar, esRevision, paso, tipoMaterial]);

  function elegirTipo(valor) {
    setTipoMaterial(valor);
    setArticulo(null);
    setArticuloBuscar('');
    setArticulos([]);
    setPaso(2);
  }

  function cambiarTipo() {
    setTipoMaterial('');
    setArticulo(null);
    setArticuloBuscar('');
    setArticulos([]);
    setPaso(1);
  }

  function cambiarArticulo() {
    setArticulo(null);
    setArticuloBuscar('');
    setArticulos([]);
    setPaso(2);
  }

  function actualizarEnsayo(idx, campo, valor) {
    setEnsayos((prev) => prev.map((en, i) => (i === idx ? { ...en, [campo]: valor } : en)));
  }

  function agregarEnsayo() {
    setEnsayos((prev) => [...prev, { ...ENSAYO_VACIO, orden: prev.length + 1 }]);
  }

  function quitarEnsayo(idx) {
    setEnsayos((prev) => prev.filter((_, i) => i !== idx).map((en, i) => ({ ...en, orden: i + 1 })));
  }

  function validar() {
    if (!esRevision && !tipoMaterial) return 'Elegí el tipo de material';
    if (!esRevision && !articulo) return 'Seleccioná un artículo del ERP';
    if (ensayos.length === 0) return 'Agregá al menos un ensayo';
    for (const en of ensayos) {
      if (!en.nombre_ensayo.trim()) return 'Todos los ensayos necesitan un nombre';
      if (en.tipo_dato === 'numerico' && en.limite_inferior === '' && en.limite_superior === '') {
        return `El ensayo "${en.nombre_ensayo}" necesita al menos un límite (inferior o superior)`;
      }
      if (en.tipo_dato === 'cualitativo' && !en.valor_requerido.trim()) {
        return `El ensayo "${en.nombre_ensayo}" necesita el valor cualitativo requerido`;
      }
    }
    return '';
  }

  function ensayosParaEnviar() {
    return ensayos.map((en) => ({
      orden: en.orden,
      nombre_ensayo: en.nombre_ensayo.trim(),
      metodologia: en.metodologia.trim() || null,
      tipo_dato: en.tipo_dato,
      limite_inferior: en.tipo_dato === 'numerico' && en.limite_inferior !== '' ? Number(en.limite_inferior) : null,
      limite_superior: en.tipo_dato === 'numerico' && en.limite_superior !== '' ? Number(en.limite_superior) : null,
      unidad_medida: en.unidad_medida.trim() || null,
      valor_requerido: en.tipo_dato === 'cualitativo' ? en.valor_requerido.trim() : null,
      obligatorio: en.obligatorio,
      observaciones: en.observaciones.trim() || null,
    }));
  }

  async function handleSubmit(e) {
    e.preventDefault();
    const msg = validar();
    if (msg) {
      setError(msg);
      return;
    }
    setError('');
    setGuardando(true);
    try {
      let resultado;
      if (esRevision) {
        resultado = await maestrosApi.revisarEspecificacion(id, ensayosParaEnviar());
      } else {
        resultado = await maestrosApi.crearEspecificacion({
          erp_IdM21: articulo.IdM21,
          erp_CODART: articulo.CODART,
          erp_DESART: articulo.DESART,
          tipo_material: tipoMaterial,
          ensayos: ensayosParaEnviar(),
        });
      }
      navigate(`/maestros/especificaciones/${resultado.id_especificacion}`, { replace: true });
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'No se pudo guardar la especificación');
    } finally {
      setGuardando(false);
    }
  }

  if (loading) {
    return (
      <div className="screen" style={{ alignItems: 'center', justifyContent: 'center' }}>
        <span className="spinner" />
      </div>
    );
  }

  // En modo "crear" el formulario de ensayos recién se muestra en el paso 3
  // (tipo + artículo ya elegidos). En "revisar" siempre se muestra: el tipo y
  // el artículo ya vienen fijos de la especificación vigente.
  const mostrarFormulario = esRevision || paso === 3;

  return (
    <div className="screen">
      <TopBar
        titulo={esRevision ? 'Revisar especificación' : 'Nueva especificación'}
        subtitulo="Datos Maestros"
        onBack={() => navigate(-1)}
      />
      <div className="screen-content">
        {!esRevision && paso === 1 && (
          <div className="card" style={{ marginBottom: 'var(--sp-5)' }}>
            <h2 style={{ fontSize: 'var(--fs-lg)', marginBottom: 'var(--sp-3)' }}>Paso 1: Tipo de material</h2>
            <div className="select-list">
              {TIPOS_MATERIAL.map((t) => (
                <button key={t.value} type="button" className="select-item" onClick={() => elegirTipo(t.value)}>
                  <span className="select-item-title">{t.label}</span>
                  <span style={{ color: 'var(--accent)' }}>→</span>
                </button>
              ))}
            </div>
          </div>
        )}

        {!esRevision && paso === 2 && (
          <div className="card" style={{ marginBottom: 'var(--sp-5)' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 'var(--sp-3)' }}>
              <h2 style={{ fontSize: 'var(--fs-lg)' }}>Paso 2: Buscar artículo ({labelTipo(tipoMaterial)})</h2>
              <button type="button" className="btn btn-ghost" onClick={cambiarTipo}>Cambiar tipo</button>
            </div>
            <input
              className="field-input"
              placeholder="Buscar por código o descripción..."
              value={articuloBuscar}
              onChange={(e) => setArticuloBuscar(e.target.value)}
              style={{ marginBottom: 'var(--sp-2)' }}
              autoFocus
            />
            {articulos.length > 0 && (
              <div className="select-list">
                {articulos.slice(0, 8).map((a) => (
                  <button
                    type="button"
                    key={a.IdM21}
                    className="select-item"
                    onClick={() => {
                      setArticulo(a);
                      setArticulos([]);
                      setArticuloBuscar('');
                      setPaso(3);
                    }}
                  >
                    <span className="select-item-main">
                      <span className="select-item-title">{a.DESART}</span>
                      <span className="select-item-sub">{a.CODART}</span>
                    </span>
                  </button>
                ))}
              </div>
            )}
          </div>
        )}

        <form onSubmit={handleSubmit}>
          {mostrarFormulario && (
            <div className="card" style={{ marginBottom: 'var(--sp-5)' }}>
              <h2 style={{ fontSize: 'var(--fs-lg)', marginBottom: 'var(--sp-3)' }}>Artículo</h2>

              <div className="select-item select-item-active" style={{ marginBottom: 'var(--sp-3)' }}>
                <span className="select-item-main">
                  <span className="select-item-title">{articulo?.DESART}</span>
                  <span className="select-item-sub">{articulo?.CODART}</span>
                </span>
                {!esRevision && (
                  <button type="button" className="btn btn-ghost" onClick={cambiarArticulo}>
                    Cambiar
                  </button>
                )}
              </div>

              <span className="badge badge-neutral">{labelTipo(tipoMaterial)}</span>
            </div>
          )}

          {mostrarFormulario && (
            <div className="card" style={{ marginBottom: 'var(--sp-5)' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 'var(--sp-3)' }}>
                <h2 style={{ fontSize: 'var(--fs-lg)' }}>Ensayos</h2>
                <button type="button" className="btn btn-secondary" onClick={agregarEnsayo}>
                  + Agregar ensayo
                </button>
              </div>

              {ensayos.map((en, idx) => (
                <div key={idx} className="card" style={{ marginBottom: 'var(--sp-3)', background: 'var(--surf-2)' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 'var(--sp-2)' }}>
                    <span style={{ fontWeight: 600 }}>Ensayo {idx + 1}</span>
                    {ensayos.length > 1 && (
                      <button type="button" className="btn btn-ghost" style={{ color: 'var(--danger)' }} onClick={() => quitarEnsayo(idx)}>
                        Quitar
                      </button>
                    )}
                  </div>

                  <div className="field">
                    <label className="field-label">Nombre del ensayo</label>
                    <input
                      className="field-input"
                      placeholder="Ej. pH, Aspecto, Valoración"
                      value={en.nombre_ensayo}
                      onChange={(e) => actualizarEnsayo(idx, 'nombre_ensayo', e.target.value)}
                    />
                  </div>

                  <div className="field">
                    <label className="field-label">Metodología</label>
                    <input
                      className="field-input"
                      placeholder="Ej. USP, PE, Interna M-04"
                      value={en.metodologia}
                      onChange={(e) => actualizarEnsayo(idx, 'metodologia', e.target.value)}
                    />
                  </div>

                  <div className="field">
                    <label className="field-label">Tipo de dato</label>
                    <select
                      className="field-input"
                      value={en.tipo_dato}
                      onChange={(e) => actualizarEnsayo(idx, 'tipo_dato', e.target.value)}
                    >
                      <option value="numerico">Numérico</option>
                      <option value="cualitativo">Cualitativo</option>
                    </select>
                  </div>

                  {en.tipo_dato === 'numerico' ? (
                    <div style={{ display: 'flex', gap: 'var(--sp-3)' }}>
                      <div className="field" style={{ flex: 1 }}>
                        <label className="field-label">Límite inferior</label>
                        <input
                          className="field-input"
                          type="number"
                          step="any"
                          value={en.limite_inferior}
                          onChange={(e) => actualizarEnsayo(idx, 'limite_inferior', e.target.value)}
                        />
                      </div>
                      <div className="field" style={{ flex: 1 }}>
                        <label className="field-label">Límite superior</label>
                        <input
                          className="field-input"
                          type="number"
                          step="any"
                          value={en.limite_superior}
                          onChange={(e) => actualizarEnsayo(idx, 'limite_superior', e.target.value)}
                        />
                      </div>
                      <div className="field" style={{ flex: 1 }}>
                        <label className="field-label">Unidad</label>
                        <input
                          className="field-input"
                          placeholder="%, g/mL, pH..."
                          value={en.unidad_medida}
                          onChange={(e) => actualizarEnsayo(idx, 'unidad_medida', e.target.value)}
                        />
                      </div>
                    </div>
                  ) : (
                    <div className="field">
                      <label className="field-label">Valor exacto requerido</label>
                      <input
                        className="field-input"
                        placeholder='Ej. "Polvo cristalino blanco"'
                        value={en.valor_requerido}
                        onChange={(e) => actualizarEnsayo(idx, 'valor_requerido', e.target.value)}
                      />
                    </div>
                  )}

                  <label style={{ display: 'flex', alignItems: 'center', gap: 'var(--sp-2)', marginTop: 'var(--sp-2)', marginBottom: 'var(--sp-3)' }}>
                    <input
                      type="checkbox"
                      checked={en.obligatorio}
                      onChange={(e) => actualizarEnsayo(idx, 'obligatorio', e.target.checked)}
                    />
                    Obligatorio
                  </label>

                  <div className="field" style={{ marginBottom: 0 }}>
                    <label className="field-label">Observaciones</label>
                    <input
                      className="field-input"
                      placeholder="Notas adicionales (opcional)"
                      value={en.observaciones}
                      onChange={(e) => actualizarEnsayo(idx, 'observaciones', e.target.value)}
                    />
                  </div>
                </div>
              ))}
            </div>
          )}

          {error && <div className="alert alert-danger" style={{ marginBottom: 'var(--sp-4)' }}>{error}</div>}

          {mostrarFormulario && (
            <button type="submit" className="btn btn-primary btn-block btn-lg" disabled={guardando}>
              {guardando ? <span className="spinner" /> : esRevision ? 'Guardar nueva versión' : 'Crear especificación'}
            </button>
          )}
        </form>
      </div>
    </div>
  );
}
