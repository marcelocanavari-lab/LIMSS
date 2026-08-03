import { useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import TopBar from '../../components/TopBar';
import { maestrosApi } from '../../api/maestros';
import { materialesApi } from '../../api/materiales';
import { ApiError } from '../../api/client';

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
  const [versionActual, setVersionActual] = useState('');
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
        setVersionActual(esp.version);
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

  async function handleSubmit(e) {
    e.preventDefault();
    if (!esRevision && !tipoMaterial) {
      setError('Elegí el tipo de material');
      return;
    }
    if (!esRevision && !articulo) {
      setError('Seleccioná un artículo del ERP');
      return;
    }
    setError('');
    setGuardando(true);
    try {
      let resultado;
      if (esRevision) {
        resultado = await maestrosApi.revisarEspecificacion(id);
      } else {
        resultado = await maestrosApi.crearEspecificacion({
          erp_IdM21: articulo.IdM21,
          erp_CODART: articulo.CODART,
          erp_DESART: articulo.DESART,
          tipo_material: tipoMaterial,
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

  // En modo "crear" el formulario recién se muestra en el paso 3 (tipo +
  // artículo ya elegidos). En "revisar" siempre se muestra: el tipo y el
  // artículo ya vienen fijos de la especificación vigente.
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
              {esRevision && <span className="badge badge-neutral" style={{ marginLeft: 'var(--sp-2)' }}>Versión actual: {versionActual}</span>}

              {esRevision && (
                <p style={{ color: 'var(--ink-2)', fontSize: 'var(--fs-sm)', marginTop: 'var(--sp-3)', marginBottom: 0 }}>
                  La nueva versión arranca con una copia de los ensayos de la versión actual. Los vas a poder
                  agregar, editar o quitar desde la ficha de la especificación una vez creada.
                </p>
              )}
            </div>
          )}

          {error && <div className="alert alert-danger" style={{ marginBottom: 'var(--sp-4)' }}>{error}</div>}

          {mostrarFormulario && (
            <button type="submit" className="btn btn-primary btn-block btn-lg" disabled={guardando}>
              {guardando ? <span className="spinner" /> : esRevision ? 'Confirmar nueva versión' : 'Crear especificación'}
            </button>
          )}
        </form>
      </div>
    </div>
  );
}
