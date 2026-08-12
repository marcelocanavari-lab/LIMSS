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

  return (
    <div className="screen">
      <TopBar titulo={esReimpresion ? 'Reimprimir etiqueta' : 'Imprimir etiqueta'} subtitulo="Muestras" onBack={() => navigate(-1)} />
      <div className="screen-content">
        {error && <div className="alert alert-danger" style={{ marginBottom: 'var(--sp-4)' }}>{error}</div>}

        {registrando ? (
          <div className="state-block"><span className="spinner" /><span>Registrando impresión...</span></div>
        ) : (
          <button className="btn btn-primary" onClick={abrirPdf} disabled={abriendo}>
            {abriendo ? <span className="spinner" /> : `${esReimpresion ? 'Reimprimir' : 'Imprimir'} etiquetas (PDF) →`}
          </button>
        )}
      </div>
    </div>
  );
}
