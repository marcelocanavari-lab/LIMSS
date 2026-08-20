import { useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import TopBar from '../../components/TopBar';
import { muestrasApi } from '../../api/muestras';
import { ApiError, abrirPdfConAuth } from '../../api/client';

// El PDF de etiquetas se arma en el backend con la misma función que usa
// "Descargar etiquetas" en Solicitudes de Muestreo (ver
// generar_pdf_etiquetas_de_solicitud en solicitudes_muestreo.py), para que
// sea idéntico sin importar desde dónde se imprima. Esta pantalla solo
// registra la impresión/reimpresión (lims_etiquetas) y da el botón para
// abrir ese PDF.
export default function MuestraEtiquetaPage() {
  const { id } = useParams();
  const navigate = useNavigate();

  const [esReimpresion, setEsReimpresion] = useState(false);
  const [registrando, setRegistrando] = useState(true);
  const [error, setError] = useState('');
  const [abriendo, setAbriendo] = useState(false);

  // Impresión directa (SATO/SBPL) -- alternativa al PDF, no lo reemplaza.
  const [impresoras, setImpresoras] = useState([]);
  const [idImpresora, setIdImpresora] = useState('');
  const [mostrarImprimirDirecto, setMostrarImprimirDirecto] = useState(false);
  const [imprimiendo, setImprimiendo] = useState(false);
  const [mensajeDirecto, setMensajeDirecto] = useState(null); // { tipo: 'ok'|'error', texto }

  useEffect(() => {
    muestrasApi
      .generarEtiqueta(id)
      .then((etiqueta) => setEsReimpresion(Boolean(etiqueta.es_reimpresion)))
      .catch((err) => setError(err instanceof ApiError ? err.message : 'No se pudo registrar la impresión de la etiqueta'))
      .finally(() => setRegistrando(false));
  }, [id]);

  async function abrirPdf() {
    setAbriendo(true);
    try {
      await abrirPdfConAuth(`/api/muestras/${id}/etiquetas-pdf`);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'No se pudo generar el PDF de etiquetas');
    } finally {
      setAbriendo(false);
    }
  }

  function abrirImprimirDirecto() {
    setMensajeDirecto(null);
    setMostrarImprimirDirecto(true);
    if (impresoras.length === 0) {
      muestrasApi
        .listarImpresoras(true)
        .then((data) => {
          setImpresoras(data);
          if (data.length === 1) setIdImpresora(String(data[0].id_impresora));
        })
        .catch(() => setMensajeDirecto({ tipo: 'error', texto: 'No se pudo cargar el listado de impresoras' }));
    }
  }

  async function confirmarImprimirDirecto() {
    if (!idImpresora) return;
    setImprimiendo(true);
    setMensajeDirecto(null);
    try {
      const resp = await muestrasApi.imprimirDirecto(id, Number(idImpresora));
      setMensajeDirecto({ tipo: 'ok', texto: resp.mensaje });
    } catch (err) {
      setMensajeDirecto({ tipo: 'error', texto: err instanceof ApiError ? err.message : 'No se pudo imprimir la etiqueta' });
    } finally {
      setImprimiendo(false);
    }
  }

  return (
    <div className="screen">
      <TopBar titulo={esReimpresion ? 'Reimprimir etiqueta' : 'Imprimir etiqueta'} subtitulo="Muestras" onBack={() => navigate(-1)} />
      <div className="screen-content">
        {error && <div className="alert alert-danger" style={{ marginBottom: 'var(--sp-4)' }}>{error}</div>}

        {registrando ? (
          <div className="state-block"><span className="spinner" /><span>Registrando impresión...</span></div>
        ) : (
          <>
            <button className="btn btn-primary" style={{ marginBottom: 'var(--sp-3)' }} onClick={abrirPdf} disabled={abriendo}>
              {abriendo ? <span className="spinner" /> : `${esReimpresion ? 'Reimprimir' : 'Imprimir'} etiquetas (PDF) →`}
            </button>

            {!mostrarImprimirDirecto ? (
              <button className="btn btn-secondary" onClick={abrirImprimirDirecto}>
                Imprimir directo (impresora SATO) →
              </button>
            ) : (
              <div className="card">
                <h2 style={{ fontSize: 'var(--fs-lg)', marginBottom: 'var(--sp-3)' }}>Imprimir directo</h2>
                {impresoras.length === 0 && !mensajeDirecto ? (
                  <div className="state-block"><span className="spinner" /></div>
                ) : impresoras.length === 0 ? null : (
                  <div className="field">
                    <label className="field-label" htmlFor="impresora">Impresora</label>
                    <select
                      id="impresora"
                      className="field-input"
                      value={idImpresora}
                      onChange={(e) => setIdImpresora(e.target.value)}
                      disabled={imprimiendo}
                    >
                      <option value="">Seleccioná una impresora...</option>
                      {impresoras.map((imp) => (
                        <option key={imp.id_impresora} value={imp.id_impresora}>{imp.nombre} ({imp.modelo})</option>
                      ))}
                    </select>
                  </div>
                )}

                {mensajeDirecto && (
                  <div className={`alert ${mensajeDirecto.tipo === 'ok' ? 'alert-ok' : 'alert-danger'}`} style={{ marginBottom: 'var(--sp-3)' }}>
                    {mensajeDirecto.texto}
                  </div>
                )}

                <div style={{ display: 'flex', gap: 'var(--sp-3)' }}>
                  <button type="button" className="btn btn-ghost" onClick={() => setMostrarImprimirDirecto(false)} disabled={imprimiendo}>
                    Cancelar
                  </button>
                  <button
                    type="button"
                    className="btn btn-primary"
                    onClick={confirmarImprimirDirecto}
                    disabled={imprimiendo || !idImpresora}
                  >
                    {imprimiendo ? <span className="spinner" /> : 'Imprimir'}
                  </button>
                </div>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}
