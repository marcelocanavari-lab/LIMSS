import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import TopBar from '../../components/TopBar';
import { muestrasApi } from '../../api/muestras';
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

export default function MuestraNuevaPage() {
  const navigate = useNavigate();

  const [paso, setPaso] = useState(1);
  const [tipo, setTipo] = useState('');
  const [referencia, setReferencia] = useState('');
  const [lineas, setLineas] = useState(null);
  const [linea, setLinea] = useState(null);
  const [observaciones, setObservaciones] = useState('');
  const [buscando, setBuscando] = useState(false);
  const [guardando, setGuardando] = useState(false);
  const [error, setError] = useState('');

  const esMateriaPrima = tipo === 'materia_prima';

  function elegirTipo(valor) {
    setTipo(valor);
    setReferencia('');
    setLineas(null);
    setLinea(null);
    setPaso(2);
  }

  function cambiarTipo() {
    setTipo('');
    setReferencia('');
    setLineas(null);
    setLinea(null);
    setPaso(1);
  }

  function cambiarMaterial() {
    setLinea(null);
    setPaso(2);
  }

  async function handleBuscar(e) {
    e.preventDefault();
    if (!referencia.trim()) return;
    setError('');
    setLinea(null);
    setLineas(null);
    setBuscando(true);
    try {
      const data = await muestrasApi.buscarMaterial(tipo, referencia.trim());
      setLineas(data);
      if (data.length === 1) {
        setLinea(data[0]);
        setPaso(3);
      }
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'No se pudo buscar el material');
    } finally {
      setBuscando(false);
    }
  }

  async function handleSubmit(e) {
    e.preventDefault();
    if (!linea) {
      setError('Seleccioná el material encontrado');
      return;
    }
    setError('');
    setGuardando(true);
    try {
      const muestra = await muestrasApi.crearMuestra({
        tipo_referencia: esMateriaPrima ? 'ir' : 'lote',
        nro_referencia: linea.referencia,
        erp_IdM21: linea.IdM21,
        erp_CODART: linea.CODART,
        erp_DESART: linea.DESART,
        erp_cantidad_lote: linea.cantidad,
        erp_proveedor: linea.proveedor || null,
        observaciones: observaciones.trim() || null,
      });
      navigate(`/muestras/${muestra.id_muestra}`, { replace: true });
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'No se pudo crear la muestra');
    } finally {
      setGuardando(false);
    }
  }

  return (
    <div className="screen">
      <TopBar titulo="Nueva muestra" subtitulo="Muestras" onBack={() => navigate('/muestras')} />
      <div className="screen-content">
        {paso === 1 && (
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

        {paso === 2 && (
          <div className="card" style={{ marginBottom: 'var(--sp-5)' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 'var(--sp-3)' }}>
              <h2 style={{ fontSize: 'var(--fs-lg)' }}>
                Paso 2: {esMateriaPrima ? 'Número de IR' : 'Número de Lote'} ({labelTipo(tipo)})
              </h2>
              <button type="button" className="btn btn-ghost" onClick={cambiarTipo}>Cambiar tipo</button>
            </div>
            <form onSubmit={handleBuscar} style={{ display: 'flex', gap: 'var(--sp-3)' }}>
              <input
                className="field-input"
                style={{ flex: 1 }}
                placeholder={esMateriaPrima ? 'Ej. 262/20' : 'Ej. LOTE-2026-001'}
                value={referencia}
                onChange={(e) => setReferencia(e.target.value)}
                disabled={buscando}
                autoFocus
              />
              <button type="submit" className="btn btn-secondary" disabled={buscando}>
                {buscando ? <span className="spinner" /> : 'Buscar'}
              </button>
            </form>

            {lineas && lineas.length > 1 && (
              <div className="select-list" style={{ marginTop: 'var(--sp-4)' }}>
                {lineas.map((l) => (
                  <button
                    key={l.IdM21}
                    type="button"
                    className="select-item"
                    onClick={() => {
                      setLinea(l);
                      setPaso(3);
                    }}
                  >
                    <span className="select-item-main">
                      <span className="select-item-title">{l.DESART}</span>
                      <span className="select-item-sub">{l.CODART} — {l.cantidad} {l.unidad || ''}</span>
                    </span>
                  </button>
                ))}
              </div>
            )}
          </div>
        )}

        {paso === 3 && linea && (
          <form onSubmit={handleSubmit}>
            <div className="card" style={{ marginBottom: 'var(--sp-5)' }}>
              <h2 style={{ fontSize: 'var(--fs-lg)', marginBottom: 'var(--sp-3)' }}>Datos del material</h2>
              <table className="data-table">
                <tbody>
                  <tr><td>Material</td><td style={{ textAlign: 'left' }}>{linea.DESART} ({linea.CODART})</td></tr>
                  <tr><td>Cantidad</td><td className="num" style={{ textAlign: 'left' }}>{linea.cantidad ?? '—'} {linea.unidad || ''}</td></tr>
                  {linea.proveedor && (
                    <tr><td>Proveedor</td><td style={{ textAlign: 'left' }}>{linea.proveedor}</td></tr>
                  )}
                </tbody>
              </table>
              <button type="button" className="btn btn-ghost" onClick={cambiarMaterial} style={{ marginTop: 'var(--sp-2)' }}>
                Cambiar material
              </button>
            </div>

            <div className="card" style={{ marginBottom: 'var(--sp-5)' }}>
              <div className="field">
                <label className="field-label" htmlFor="observaciones">Observaciones (opcional)</label>
                <input
                  id="observaciones"
                  className="field-input"
                  value={observaciones}
                  onChange={(e) => setObservaciones(e.target.value)}
                  disabled={guardando}
                />
              </div>
            </div>

            {error && <div className="alert alert-danger" style={{ marginBottom: 'var(--sp-4)' }}>{error}</div>}

            <button type="submit" className="btn btn-primary btn-block btn-lg" disabled={guardando}>
              {guardando ? <span className="spinner" /> : 'Crear muestra'}
            </button>
          </form>
        )}

        {error && paso !== 3 && <div className="alert alert-danger" style={{ marginTop: 'var(--sp-4)' }}>{error}</div>}
      </div>
    </div>
  );
}
