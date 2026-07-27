import { useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { useAuth } from '../../context/AuthContext';
import TopBar from '../../components/TopBar';
import { muestrasApi } from '../../api/muestras';
import { enviosApi } from '../../api/envios';
import { ApiError } from '../../api/client';

function hoyISO() {
  return new Date().toISOString().slice(0, 10);
}

export default function RemitoImprimirPage() {
  const { id, idEnvio } = useParams();
  const navigate = useNavigate();
  const { user } = useAuth();
  const puedeGenerarRemito = ['analista_qc', 'qa', 'admin'].includes(user?.rol);

  const [remito, setRemito] = useState(null);
  const [error, setError] = useState('');

  const [remitoPdf, setRemitoPdf] = useState(null); // { blob, numero, fecha } | null
  const [buscandoPdf, setBuscandoPdf] = useState(true);
  const [generando, setGenerando] = useState(false);
  const [pdfError, setPdfError] = useState('');

  // Constancia de recepción (copia firmada por el laboratorio)
  const [mostrarFormRecepcion, setMostrarFormRecepcion] = useState(false);
  const [fechaRecepcion, setFechaRecepcion] = useState(hoyISO());
  const [recibidoPor, setRecibidoPor] = useState('');
  const [archivoFirmado, setArchivoFirmado] = useState(null);
  const [guardandoRecepcion, setGuardandoRecepcion] = useState(false);
  const [errorRecepcion, setErrorRecepcion] = useState('');

  function cargarRemito() {
    muestrasApi
      .obtenerRemito(id, idEnvio)
      .then((r) => {
        setRemito(r);
        setMostrarFormRecepcion(!r.tiene_copia_firmada);
      })
      .catch((err) => setError(err instanceof ApiError ? err.message : 'No se pudo cargar el remito'));
  }

  useEffect(cargarRemito, [id, idEnvio]);

  useEffect(() => {
    if (!remito?.id_envio) return;
    setBuscandoPdf(true);
    enviosApi
      .obtenerRemitoPdf(remito.id_envio)
      .then(setRemitoPdf)
      .catch((err) => {
        if (err instanceof ApiError && err.status === 404) {
          setRemitoPdf(null);
        } else {
          setPdfError(err instanceof ApiError ? err.message : 'No se pudo verificar el remito PDF');
        }
      })
      .finally(() => setBuscandoPdf(false));
  }, [remito?.id_envio]);

  async function handleGenerar() {
    setPdfError('');
    setGenerando(true);
    try {
      await enviosApi.generarRemitoPdf(remito.id_envio);
      const actualizado = await enviosApi.obtenerRemitoPdf(remito.id_envio);
      setRemitoPdf(actualizado);
    } catch (err) {
      setPdfError(err instanceof ApiError ? err.message : 'No se pudo generar el remito');
    } finally {
      setGenerando(false);
    }
  }

  function verPdf() {
    if (!remitoPdf) return;
    const url = URL.createObjectURL(remitoPdf.blob);
    window.open(url, '_blank');
  }

  function descargarPdf() {
    if (!remitoPdf) return;
    const url = URL.createObjectURL(remitoPdf.blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `LIMSS_${remitoPdf.numero || 'remito'}.pdf`;
    document.body.appendChild(a);
    a.click();
    a.remove();
  }

  async function verCopiaFirmada() {
    try {
      const blob = await enviosApi.descargarCopiaFirmada(remito.id_envio);
      window.open(URL.createObjectURL(blob), '_blank');
    } catch (err) {
      setErrorRecepcion(err instanceof ApiError ? err.message : 'No se pudo descargar la copia firmada');
    }
  }

  function abrirReemplazoRecepcion() {
    setFechaRecepcion(hoyISO());
    setRecibidoPor('');
    setArchivoFirmado(null);
    setErrorRecepcion('');
    setMostrarFormRecepcion(true);
  }

  async function handleSubmitRecepcion(e) {
    e.preventDefault();
    if (!fechaRecepcion || !recibidoPor.trim()) {
      setErrorRecepcion('Completá la fecha de recepción y quién la recibió');
      return;
    }
    if (!archivoFirmado) {
      setErrorRecepcion('Adjuntá el PDF escaneado de la copia firmada');
      return;
    }
    if (archivoFirmado.type !== 'application/pdf') {
      setErrorRecepcion('El archivo debe ser un PDF');
      return;
    }

    setErrorRecepcion('');
    setGuardandoRecepcion(true);
    try {
      const formData = new FormData();
      formData.append('fecha_recepcion', fechaRecepcion);
      formData.append('recibido_por', recibidoPor.trim());
      formData.append('pdf_copia_firmada', archivoFirmado);
      await enviosApi.adjuntarCopiaFirmada(remito.id_envio, formData);
      cargarRemito();
    } catch (err) {
      setErrorRecepcion(err instanceof ApiError ? err.message : 'No se pudo adjuntar la copia firmada');
    } finally {
      setGuardandoRecepcion(false);
    }
  }

  return (
    <div className="screen">
      <TopBar titulo="Remito de envío" subtitulo="Envío de Muestras" onBack={() => navigate(`/envios/muestras/${id}`)} />
      <div className="screen-content">
        <button className="btn btn-primary no-print" style={{ marginBottom: 'var(--sp-4)' }} onClick={() => window.print()}>
          Imprimir →
        </button>

        {error && <div className="alert alert-danger no-print" style={{ marginBottom: 'var(--sp-4)' }}>{error}</div>}

        {remito && (
          <div className="card no-print" style={{ marginBottom: 'var(--sp-4)' }}>
            <h2 style={{ fontSize: 'var(--fs-lg)', marginBottom: 'var(--sp-3)' }}>Remito en PDF</h2>

            {buscandoPdf ? (
              <div className="state-block"><span className="spinner" /></div>
            ) : remitoPdf ? (
              <>
                <p>
                  Remito <b style={{ fontFamily: 'var(--font-mono)' }}>{remitoPdf.numero}</b> generado el{' '}
                  {remitoPdf.fecha ? new Date(remitoPdf.fecha).toLocaleString() : '—'}.
                </p>
                <div style={{ display: 'flex', gap: 'var(--sp-3)', flexWrap: 'wrap' }}>
                  <button className="btn btn-secondary" onClick={verPdf}>Ver PDF</button>
                  <button className="btn btn-secondary" onClick={descargarPdf}>Descargar PDF</button>
                  {puedeGenerarRemito && (
                    <button className="btn btn-ghost" onClick={handleGenerar} disabled={generando}>
                      {generando ? <span className="spinner" /> : 'Generar uno nuevo →'}
                    </button>
                  )}
                </div>
              </>
            ) : (
              <>
                <p style={{ color: 'var(--ink-2)', marginBottom: 'var(--sp-3)' }}>
                  Todavía no se generó el remito en PDF para este envío.
                </p>
                {puedeGenerarRemito && (
                  <button className="btn btn-primary" onClick={handleGenerar} disabled={generando}>
                    {generando ? <span className="spinner" /> : 'Generar Remito →'}
                  </button>
                )}
              </>
            )}

            {pdfError && <div className="alert alert-danger" style={{ marginTop: 'var(--sp-3)' }}>{pdfError}</div>}
          </div>
        )}

        {remito && remitoPdf && (
          <div className="card no-print" style={{ marginBottom: 'var(--sp-4)' }}>
            <h2 style={{ fontSize: 'var(--fs-lg)', marginBottom: 'var(--sp-3)' }}>Constancia de recepción</h2>

            {remito.tiene_copia_firmada && !mostrarFormRecepcion ? (
              <>
                <table className="data-table" style={{ marginBottom: 'var(--sp-4)' }}>
                  <tbody>
                    <tr><td>Fecha de recepción</td><td style={{ textAlign: 'left' }}>{new Date(remito.fecha_recepcion).toLocaleDateString()}</td></tr>
                    <tr><td>Recibido por</td><td style={{ textAlign: 'left' }}>{remito.recibido_por}</td></tr>
                  </tbody>
                </table>
                <div style={{ display: 'flex', gap: 'var(--sp-3)' }}>
                  <button type="button" className="btn btn-secondary" onClick={verCopiaFirmada}>
                    Ver copia firmada
                  </button>
                  {puedeGenerarRemito && (
                    <button type="button" className="btn btn-ghost" onClick={abrirReemplazoRecepcion}>
                      Reemplazar
                    </button>
                  )}
                </div>
              </>
            ) : puedeGenerarRemito ? (
              <form onSubmit={handleSubmitRecepcion}>
                {!remito.tiene_copia_firmada && (
                  <p style={{ color: 'var(--ink-2)', marginBottom: 'var(--sp-3)' }}>
                    Este remito todavía no tiene la copia firmada por el laboratorio adjunta.
                  </p>
                )}
                <div className="field">
                  <label className="field-label" htmlFor="fechaRecepcion">Fecha de recepción</label>
                  <input
                    id="fechaRecepcion"
                    className="field-input"
                    type="date"
                    value={fechaRecepcion}
                    onChange={(e) => setFechaRecepcion(e.target.value)}
                    disabled={guardandoRecepcion}
                  />
                </div>
                <div className="field">
                  <label className="field-label" htmlFor="recibidoPor">Recibido por</label>
                  <input
                    id="recibidoPor"
                    className="field-input"
                    placeholder="Nombre de quien firmó la recepción"
                    value={recibidoPor}
                    onChange={(e) => setRecibidoPor(e.target.value)}
                    disabled={guardandoRecepcion}
                  />
                </div>
                <div className="field" style={{ marginBottom: 0 }}>
                  <label className="field-label" htmlFor="pdfCopiaFirmada">Copia firmada (PDF escaneado)</label>
                  <input
                    id="pdfCopiaFirmada"
                    className="field-input"
                    type="file"
                    accept="application/pdf"
                    onChange={(e) => setArchivoFirmado(e.target.files?.[0] || null)}
                    disabled={guardandoRecepcion}
                  />
                </div>

                {errorRecepcion && <div className="alert alert-danger" style={{ marginTop: 'var(--sp-3)' }}>{errorRecepcion}</div>}

                <div style={{ display: 'flex', gap: 'var(--sp-3)', marginTop: 'var(--sp-4)' }}>
                  {remito.tiene_copia_firmada && (
                    <button type="button" className="btn btn-ghost" onClick={() => setMostrarFormRecepcion(false)} disabled={guardandoRecepcion}>
                      Cancelar
                    </button>
                  )}
                  <button type="submit" className="btn btn-primary" disabled={guardandoRecepcion}>
                    {guardandoRecepcion ? <span className="spinner" /> : 'Adjuntar copia firmada'}
                  </button>
                </div>
              </form>
            ) : (
              <p style={{ color: 'var(--ink-2)' }}>Todavía no se adjuntó la copia firmada por el laboratorio.</p>
            )}
          </div>
        )}

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
                <span><b>Muestreador:</b> {remito.usuario_muestreo_nombre}</span>
                {remito.cantidad_enviada != null && (
                  <span><b>Cantidad enviada:</b> {remito.cantidad_enviada} {remito.unidad_enviada || ''}</span>
                )}
              </div>
            </div>

            <div className="card" style={{ marginBottom: 'var(--sp-4)' }}>
              <h2>Laboratorio destino</h2>
              <p><b>{remito.laboratorio_nombre}</b></p>
              {remito.laboratorio_direccion && <p>{remito.laboratorio_direccion}</p>}
              {remito.laboratorio_contacto && <p>Contacto: {remito.laboratorio_contacto}</p>}
            </div>

            <div className="card" style={{ marginBottom: 'var(--sp-4)' }}>
              <h2>Datos del envío</h2>
              <table className="data-table">
                <tbody>
                  <tr><td>Fecha de despacho</td><td style={{ textAlign: 'left' }}>{new Date(remito.fecha_despacho).toLocaleString()}</td></tr>
                  <tr><td>Número de remito/guía externo</td><td style={{ textAlign: 'left' }}>{remito.nro_remito || '—'}</td></tr>
                  <tr><td>Transportista</td><td style={{ textAlign: 'left' }}>{remito.transportista || '—'}</td></tr>
                  <tr><td>Temperatura de transporte</td><td style={{ textAlign: 'left' }}>{remito.temperatura_transporte || '—'}</td></tr>
                  <tr><td>Análisis solicitados</td><td style={{ textAlign: 'left' }}>{remito.analisis_solicitados || '—'}</td></tr>
                  <tr><td>Protocolo a utilizar</td><td style={{ textAlign: 'left' }}>{remito.protocolo_utilizar || '—'}</td></tr>
                </tbody>
              </table>
            </div>

            {remito.ensayos_solicitados.length > 0 && (
              <div className="card" style={{ marginBottom: 'var(--sp-4)' }}>
                <h2>Ensayos solicitados</h2>
                <ul style={{ margin: 0, paddingLeft: '1.2em' }}>
                  {remito.ensayos_solicitados.map((e) => (
                    <li key={e.id_espec_ensayo}>
                      {e.nombre_ensayo} {!e.requerido_por_defecto && <span className="badge badge-neutral">Opcional</span>}
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {remito.testigo_codigo && (
              <div className="card" style={{ marginBottom: 'var(--sp-4)' }}>
                <h2>Testigo enviado</h2>
                <table className="data-table">
                  <tbody>
                    <tr><td>Código</td><td style={{ textAlign: 'left' }}>{remito.testigo_codigo}</td></tr>
                    <tr><td>Nombre</td><td style={{ textAlign: 'left' }}>{remito.testigo_nombre}</td></tr>
                    <tr><td>Lote</td><td style={{ textAlign: 'left' }}>{remito.testigo_nro_lote || '—'}</td></tr>
                    <tr><td>Vencimiento</td><td style={{ textAlign: 'left' }}>{remito.testigo_fecha_vencimiento || '—'}</td></tr>
                    <tr><td>Cantidad enviada</td><td style={{ textAlign: 'left' }}>{remito.cantidad_testigo}</td></tr>
                  </tbody>
                </table>
              </div>
            )}

            {remitoPdf && (
              <p style={{ fontSize: 'var(--fs-xs)', color: '#666' }}>Remito N° {remitoPdf.numero}</p>
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
