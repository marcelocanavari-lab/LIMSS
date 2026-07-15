import { useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { QRCodeSVG } from 'qrcode.react';
import TopBar from '../../components/TopBar';
import { muestrasApi } from '../../api/muestras';
import { ApiError } from '../../api/client';

export default function MuestraEtiquetaPage() {
  const { id } = useParams();
  const navigate = useNavigate();

  const [muestra, setMuestra] = useState(null);
  const [error, setError] = useState('');

  useEffect(() => {
    muestrasApi
      .obtenerMuestra(id)
      .then(setMuestra)
      .catch((err) => setError(err instanceof ApiError ? err.message : 'No se pudo cargar la muestra'));
  }, [id]);

  return (
    <div className="screen">
      <TopBar titulo="Etiqueta de muestra" subtitulo="Muestras" onBack={() => navigate(`/muestras/${id}`)} />
      <div className="screen-content">
        <button className="btn btn-primary no-print" style={{ marginBottom: 'var(--sp-4)' }} onClick={() => window.print()}>
          Imprimir →
        </button>

        {error && <div className="alert alert-danger no-print" style={{ marginBottom: 'var(--sp-4)' }}>{error}</div>}

        {!muestra ? (
          <div className="state-block no-print"><span className="spinner" /><span>Cargando...</span></div>
        ) : (
          <div className="printable-label">
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <div>
                <div className="label-codigo">{muestra.codigo_muestra}</div>
                <div className="label-row"><span>{muestra.tipo_referencia === 'ir' ? 'IR' : 'Lote'}</span><span>{muestra.nro_referencia}</span></div>
              </div>
              <QRCodeSVG value={muestra.codigo_muestra} size={80} />
            </div>
            <div className="label-row"><span>Material</span><span>{muestra.erp_CODART}</span></div>
            <div style={{ fontSize: 'var(--fs-sm)' }}>{muestra.erp_DESART}</div>
            <div className="label-row"><span>Fecha de muestreo</span><span>{new Date(muestra.fecha_muestreo).toLocaleDateString()}</span></div>
            <div className="label-row"><span>Muestreador</span><span>{muestra.usuario_muestreo_nombre}</span></div>
          </div>
        )}
      </div>
    </div>
  );
}
