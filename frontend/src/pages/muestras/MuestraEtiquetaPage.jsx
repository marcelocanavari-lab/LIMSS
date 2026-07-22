import { useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { QRCodeSVG } from 'qrcode.react';
import TopBar from '../../components/TopBar';
import { muestrasApi } from '../../api/muestras';
import { ApiError } from '../../api/client';

export default function MuestraEtiquetaPage() {
  const { id } = useParams();
  const navigate = useNavigate();

  const [etiqueta, setEtiqueta] = useState(null);
  const [error, setError] = useState('');

  useEffect(() => {
    muestrasApi
      .generarEtiqueta(id)
      .then(setEtiqueta)
      .catch((err) => setError(err instanceof ApiError ? err.message : 'No se pudo generar la etiqueta'));
  }, [id]);

  return (
    <div className="screen">
      <TopBar titulo="Etiqueta de muestra" subtitulo="Muestras" onBack={() => navigate(`/muestras/${id}`)} />
      <div className="screen-content">
        <button className="btn btn-primary no-print" style={{ marginBottom: 'var(--sp-4)' }} onClick={() => window.print()}>
          Imprimir →
        </button>

        {error && <div className="alert alert-danger no-print" style={{ marginBottom: 'var(--sp-4)' }}>{error}</div>}

        {!etiqueta ? (
          !error && <div className="state-block no-print"><span className="spinner" /><span>Generando etiqueta...</span></div>
        ) : (
          <div className="printable-label">
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <div>
                <div className="label-codigo">{etiqueta.codigo_muestra}</div>
                <div className="label-row"><span>{etiqueta.tipo_referencia === 'ir' ? 'IR' : 'Lote'}</span><span>{etiqueta.nro_referencia}</span></div>
              </div>
              <QRCodeSVG value={etiqueta.codigo_muestra} size={56} />
            </div>
            <div className="label-row"><span>Material</span><span>{etiqueta.erp_CODART}</span></div>
            <div style={{ fontSize: '0.65rem', lineHeight: 1.3 }}>{etiqueta.erp_DESART}</div>
            <div className="label-row"><span>Fecha de muestreo</span><span>{new Date(etiqueta.fecha_muestreo).toLocaleDateString()}</span></div>
            <div className="label-row"><span>Muestreador</span><span>{etiqueta.usuario_muestreo_nombre}</span></div>
          </div>
        )}
      </div>
    </div>
  );
}
