import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import TopBar from '../components/TopBar';
import { muestrasApi } from '../api/muestras';
import { solicitudesMuestreoApi } from '../api/solicitudesMuestreo';
import { ApiError } from '../api/client';

const LABEL_ETIQUETA = {
  muestra: 'Muestra',
  cuarentena: 'Cuarentena',
  aprobado: 'Aprobado',
};

const BADGE_ESTADO = {
  pendiente: 'badge-warn',
  ejecutada: 'badge-ok',
  pendiente_envio: 'badge-warn',
  en_análisis: 'badge-info',
  aprobado: 'badge-ok',
  rechazado: 'badge-danger',
  cuarentena: 'badge-warn',
};

// Cada acción de impresión llama a un endpoint distinto según el tipo de
// etiqueta y de dónde sale el id (solicitud para cuarentena, muestra para
// el resto) -- un solo lugar para no repetir esta correspondencia en el JSX.
function llamarImprimir(item, tipoEtiqueta, idImpresora) {
  if (tipoEtiqueta === 'cuarentena') return solicitudesMuestreoApi.imprimirCuarentena(item.id, idImpresora);
  if (tipoEtiqueta === 'aprobado') return muestrasApi.imprimirAprobado(item.id, idImpresora);
  return muestrasApi.imprimirDirecto(item.id, idImpresora);
}

export default function ImpresionEtiquetasPage() {
  const navigate = useNavigate();

  const [buscar, setBuscar] = useState('');
  const [resultados, setResultados] = useState(null);
  const [buscando, setBuscando] = useState(false);
  const [error, setError] = useState('');

  // ── Modal: imprimir (cualquiera de los 3 tipos, sobre cualquier item) ──
  const [imprimiendoItem, setImprimiendoItem] = useState(null); // { item, tipoEtiqueta }
  const [impresoras, setImpresoras] = useState([]);
  const [idImpresora, setIdImpresora] = useState('');
  const [enviando, setEnviando] = useState(false);
  const [mensaje, setMensaje] = useState(null); // { tipo: 'ok'|'error', texto }

  async function handleBuscar(e) {
    e.preventDefault();
    if (!buscar.trim()) return;
    setError('');
    setBuscando(true);
    try {
      const data = await muestrasApi.buscarParaEtiquetas(buscar.trim());
      setResultados(data);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'No se pudo buscar');
    } finally {
      setBuscando(false);
    }
  }

  function abrirImprimir(item, tipoEtiqueta) {
    setImprimiendoItem({ item, tipoEtiqueta });
    setMensaje(null);
    if (impresoras.length === 0) {
      muestrasApi
        .listarImpresoras(true)
        .then((data) => {
          setImpresoras(data);
          if (data.length === 1) setIdImpresora(String(data[0].id_impresora));
        })
        .catch(() => setMensaje({ tipo: 'error', texto: 'No se pudo cargar el listado de impresoras' }));
    }
  }

  function cerrarImprimir() {
    setImprimiendoItem(null);
  }

  async function confirmarImprimir() {
    if (!idImpresora || !imprimiendoItem) return;
    setEnviando(true);
    setMensaje(null);
    try {
      const resp = await llamarImprimir(imprimiendoItem.item, imprimiendoItem.tipoEtiqueta, Number(idImpresora));
      setMensaje({ tipo: 'ok', texto: resp.mensaje });
    } catch (err) {
      setMensaje({ tipo: 'error', texto: err instanceof ApiError ? err.message : 'No se pudo imprimir la etiqueta' });
    } finally {
      setEnviando(false);
    }
  }

  return (
    <div className="screen">
      <TopBar titulo="Impresión de Etiquetas" subtitulo="Dashboard" onBack={() => navigate('/menu')} />
      <div className="screen-content">
        <p style={{ fontSize: 'var(--fs-sm)', color: 'var(--ink-2)', marginBottom: 'var(--sp-3)' }}>
          Buscá una solicitud o muestra por número, código o artículo, y elegí qué etiqueta imprimir según su estado --
          acceso rápido sin entrar a la pantalla específica de cada una.
        </p>

        <form onSubmit={handleBuscar} style={{ display: 'flex', gap: 'var(--sp-3)', marginBottom: 'var(--sp-4)' }}>
          <input
            className="field-input"
            style={{ flex: 1 }}
            placeholder="N° de solicitud, código de muestra, artículo..."
            value={buscar}
            onChange={(e) => setBuscar(e.target.value)}
            disabled={buscando}
            autoFocus
          />
          <button type="submit" className="btn btn-secondary" disabled={buscando || !buscar.trim()}>
            {buscando ? <span className="spinner" /> : 'Buscar'}
          </button>
        </form>

        {error && <div className="alert alert-danger" style={{ marginBottom: 'var(--sp-4)' }}>{error}</div>}

        {resultados && (
          resultados.length === 0 ? (
            <div className="state-block">
              <span className="state-block-title">Sin resultados</span>
              <span>No se encontró ninguna solicitud ni muestra con ese criterio</span>
            </div>
          ) : (
            <div className="select-list">
              {resultados.map((item) => (
                <div
                  key={`${item.tipo}-${item.id}`}
                  className="select-item"
                  style={{ flexDirection: 'column', alignItems: 'stretch', cursor: 'default' }}
                >
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 'var(--sp-3)', flexWrap: 'wrap' }}>
                    <span className="select-item-main">
                      <span className="select-item-title">{item.identificador}</span>
                      <span className="select-item-sub">{item.erp_DESART} ({item.erp_CODART})</span>
                    </span>
                    <span className={`badge ${BADGE_ESTADO[item.estado] || 'badge-neutral'}`}>{item.estado}</span>
                  </div>
                  <div style={{ display: 'flex', gap: 'var(--sp-2)', marginTop: 'var(--sp-2)', flexWrap: 'wrap' }}>
                    {item.etiquetas_disponibles.map((tipoEtiqueta) => (
                      <button
                        key={tipoEtiqueta}
                        type="button"
                        className="btn btn-ghost"
                        onClick={() => abrirImprimir(item, tipoEtiqueta)}
                      >
                        Imprimir {LABEL_ETIQUETA[tipoEtiqueta] || tipoEtiqueta}
                      </button>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          )
        )}
      </div>

      {imprimiendoItem && (
        <div
          style={{
            position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.5)',
            display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 100, padding: 'var(--sp-4)',
          }}
          onClick={cerrarImprimir}
        >
          <div className="card" style={{ width: '90%', maxWidth: 400 }} onClick={(e) => e.stopPropagation()}>
            <h2 style={{ fontSize: 'var(--fs-lg)', marginBottom: 'var(--sp-3)' }}>
              Imprimir {LABEL_ETIQUETA[imprimiendoItem.tipoEtiqueta] || imprimiendoItem.tipoEtiqueta} -- {imprimiendoItem.item.identificador}
            </h2>

            {impresoras.length === 0 && !mensaje ? (
              <div className="state-block"><span className="spinner" /></div>
            ) : impresoras.length === 0 ? null : (
              <div className="field">
                <label className="field-label" htmlFor="impresora">Impresora</label>
                <select
                  id="impresora"
                  className="field-input"
                  value={idImpresora}
                  onChange={(e) => setIdImpresora(e.target.value)}
                  disabled={enviando}
                >
                  <option value="">Seleccioná una impresora...</option>
                  {impresoras.map((imp) => (
                    <option key={imp.id_impresora} value={imp.id_impresora}>{imp.nombre} ({imp.modelo})</option>
                  ))}
                </select>
              </div>
            )}

            {mensaje && (
              <div className={`alert ${mensaje.tipo === 'ok' ? 'alert-ok' : 'alert-danger'}`} style={{ marginBottom: 'var(--sp-3)' }}>
                {mensaje.texto}
              </div>
            )}

            <div style={{ display: 'flex', gap: 'var(--sp-3)' }}>
              <button type="button" className="btn btn-ghost" onClick={cerrarImprimir} disabled={enviando}>Cerrar</button>
              <button
                type="button"
                className="btn btn-primary"
                onClick={confirmarImprimir}
                disabled={enviando || !idImpresora}
              >
                {enviando ? <span className="spinner" /> : 'Imprimir'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
