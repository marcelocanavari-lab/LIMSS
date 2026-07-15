import { useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import TopBar from '../../components/TopBar';
import { muestrasApi } from '../../api/muestras';
import { ApiError } from '../../api/client';

export default function RemitoImprimirPage() {
  const { id } = useParams();
  const navigate = useNavigate();

  const [remito, setRemito] = useState(null);
  const [error, setError] = useState('');

  useEffect(() => {
    muestrasApi
      .obtenerRemito(id)
      .then(setRemito)
      .catch((err) => setError(err instanceof ApiError ? err.message : 'No se pudo cargar el remito'));
  }, [id]);

  return (
    <div className="screen">
      <TopBar titulo="Remito de envío" subtitulo="Muestras" onBack={() => navigate(`/muestras/${id}`)} />
      <div className="screen-content">
        <button className="btn btn-primary no-print" style={{ marginBottom: 'var(--sp-4)' }} onClick={() => window.print()}>
          Imprimir →
        </button>

        {error && <div className="alert alert-danger no-print" style={{ marginBottom: 'var(--sp-4)' }}>{error}</div>}

        {!remito ? (
          !error && <div className="state-block no-print"><span className="spinner" /><span>Cargando...</span></div>
        ) : (
          <div className="printable">
            <h1 style={{ fontFamily: 'var(--font-mono)' }}>{remito.codigo_muestra}</h1>

            <div className="card" style={{ marginBottom: 'var(--sp-4)' }}>
              <div style={{ display: 'flex', gap: 'var(--sp-5)', flexWrap: 'wrap' }}>
                <span><b>{remito.tipo_referencia === 'ir' ? 'IR' : 'Lote'}:</b> {remito.nro_referencia}</span>
                <span><b>Material:</b> {remito.erp_CODART} — {remito.erp_DESART}</span>
                <span><b>Fecha de muestreo:</b> {new Date(remito.fecha_muestreo).toLocaleString()}</span>
              </div>
            </div>

            <div className="card" style={{ marginBottom: 'var(--sp-4)' }}>
              <h2>Laboratorio destino</h2>
              <p><b>{remito.laboratorio_nombre}</b></p>
              {remito.laboratorio_direccion && <p>{remito.laboratorio_direccion}</p>}
            </div>

            <div className="card" style={{ marginBottom: 'var(--sp-4)' }}>
              <h2>Datos del envío</h2>
              <table className="data-table">
                <tbody>
                  <tr><td>Fecha de despacho</td><td style={{ textAlign: 'left' }}>{new Date(remito.fecha_despacho).toLocaleString()}</td></tr>
                  <tr><td>Número de remito</td><td style={{ textAlign: 'left' }}>{remito.nro_remito || '—'}</td></tr>
                  <tr><td>Transportista</td><td style={{ textAlign: 'left' }}>{remito.transportista || '—'}</td></tr>
                  <tr><td>Temperatura de transporte</td><td style={{ textAlign: 'left' }}>{remito.temperatura_transporte || '—'}</td></tr>
                  <tr><td>Análisis solicitados</td><td style={{ textAlign: 'left' }}>{remito.analisis_solicitados || '—'}</td></tr>
                  <tr><td>Protocolo a utilizar</td><td style={{ textAlign: 'left' }}>{remito.protocolo_utilizar || '—'}</td></tr>
                </tbody>
              </table>
            </div>

            {remito.testigo_codigo && (
              <div className="card" style={{ marginBottom: 'var(--sp-4)' }}>
                <h2>Testigo enviado</h2>
                <p>{remito.testigo_codigo} — {remito.testigo_nombre} ({remito.cantidad_testigo})</p>
              </div>
            )}

            <div style={{ marginTop: 'var(--sp-6)', borderTop: '1px solid #ddd', paddingTop: 'var(--sp-4)' }}>
              Firma: ______________________
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
