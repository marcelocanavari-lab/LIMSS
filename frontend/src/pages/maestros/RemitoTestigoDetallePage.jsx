import { useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { useAuth } from '../../context/AuthContext';
import TopBar from '../../components/TopBar';
import { testigosRemitosApi } from '../../api/testigosRemitos';
import { ApiError, abrirPdfConAuth } from '../../api/client';

function hoyISO() {
  return new Date().toISOString().slice(0, 10);
}

// new Date('YYYY-MM-DD') interpreta la fecha en UTC -- en huso horario
// negativo (Argentina, UTC-3) se corre un día para atrás al mostrarla con
// toLocaleDateString() (que usa la zona LOCAL). Se arma con las partes
// sueltas, sin pasar por Date, mismo criterio que en Equipos.
function formatearFecha(fechaISO) {
  const [anio, mes, dia] = fechaISO.split('-');
  return `${dia}/${mes}/${anio}`;
}

export default function RemitoTestigoDetallePage() {
  const { id } = useParams();
  const navigate = useNavigate();
  const { user } = useAuth();
  const puedeGestionar = ['analista_qc', 'qa', 'admin'].includes(user?.rol);

  const [remito, setRemito] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const [mostrarForm, setMostrarForm] = useState(false);
  const [fechaRecepcion, setFechaRecepcion] = useState(hoyISO());
  const [recibidoPor, setRecibidoPor] = useState('');
  const [archivo, setArchivo] = useState(null);
  const [guardando, setGuardando] = useState(false);
  const [errorForm, setErrorForm] = useState('');

  function cargar() {
    setLoading(true);
    testigosRemitosApi
      .obtenerRemito(id)
      .then((r) => {
        setRemito(r);
        setMostrarForm(!r.tiene_copia_firmada);
      })
      .catch((err) => setError(err instanceof ApiError ? err.message : 'No se pudo cargar el remito'))
      .finally(() => setLoading(false));
  }

  useEffect(cargar, [id]);

  async function verPdf() {
    try {
      await abrirPdfConAuth(`/api/testigos/remitos/${id}/pdf`);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'No se pudo descargar el PDF');
    }
  }

  async function verCopiaFirmada() {
    try {
      await abrirPdfConAuth(`/api/testigos/remitos/${id}/copia-firmada`);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'No se pudo descargar la copia firmada');
    }
  }

  function abrirReemplazo() {
    setFechaRecepcion(hoyISO());
    setRecibidoPor('');
    setArchivo(null);
    setErrorForm('');
    setMostrarForm(true);
  }

  async function handleSubmit(e) {
    e.preventDefault();
    if (!fechaRecepcion || !recibidoPor.trim()) {
      setErrorForm('Completá la fecha de recepción y quién la recibió');
      return;
    }
    if (!archivo) {
      setErrorForm('Adjuntá el PDF escaneado de la copia firmada');
      return;
    }
    if (archivo.type !== 'application/pdf') {
      setErrorForm('El archivo debe ser un PDF');
      return;
    }

    setErrorForm('');
    setGuardando(true);
    try {
      const formData = new FormData();
      formData.append('fecha_recepcion', fechaRecepcion);
      formData.append('recibido_por', recibidoPor.trim());
      formData.append('pdf_copia_firmada', archivo);
      const actualizado = await testigosRemitosApi.adjuntarCopiaFirmada(id, formData);
      setRemito(actualizado);
      setMostrarForm(false);
    } catch (err) {
      setErrorForm(err instanceof ApiError ? err.message : 'No se pudo adjuntar la copia firmada');
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

  if (error || !remito) {
    return (
      <div className="screen">
        <TopBar titulo="Remito" subtitulo="Remitos de Testigos" onBack={() => navigate(-1)} />
        <div className="screen-content">
          <div className="alert alert-danger">{error || 'No encontrado'}</div>
        </div>
      </div>
    );
  }

  return (
    <div className="screen">
      <TopBar titulo={remito.nro_remito} subtitulo="Remitos de Testigos" onBack={() => navigate(-1)} />
      <div className="screen-content">
        <div className="card" style={{ marginBottom: 'var(--sp-5)' }}>
          <h2 style={{ fontSize: 'var(--fs-lg)', marginBottom: 'var(--sp-3)' }}>Datos del remito</h2>
          <table className="data-table">
            <tbody>
              <tr><td>Laboratorio</td><td style={{ textAlign: 'left' }}>{remito.laboratorio_nombre}</td></tr>
              <tr><td>Fecha de envío</td><td style={{ textAlign: 'left' }}>{formatearFecha(remito.fecha_envio)}</td></tr>
              <tr><td>Generado por</td><td style={{ textAlign: 'left' }}>{remito.usuario_nombre}</td></tr>
              {remito.observaciones && (
                <tr><td>Observaciones</td><td style={{ textAlign: 'left' }}>{remito.observaciones}</td></tr>
              )}
            </tbody>
          </table>
          <button type="button" className="btn btn-secondary" style={{ marginTop: 'var(--sp-3)' }} onClick={verPdf}>
            Ver PDF del remito
          </button>
        </div>

        <h2 style={{ fontSize: 'var(--fs-lg)', marginBottom: 'var(--sp-3)' }}>
          Testigos enviados ({remito.testigos.length})
        </h2>
        <table className="data-table" style={{ marginBottom: 'var(--sp-5)' }}>
          <thead>
            <tr>
              <th>Código</th>
              <th>Nombre</th>
              <th>Lote</th>
              <th>Cantidad</th>
            </tr>
          </thead>
          <tbody>
            {remito.testigos.map((t) => (
              <tr key={t.id_testigo}>
                <td style={{ textAlign: 'left', fontFamily: 'var(--font-mono)' }}>{t.codigo}</td>
                <td style={{ textAlign: 'left' }}>{t.nombre}</td>
                <td style={{ textAlign: 'left' }}>{t.nro_lote}</td>
                <td className="num">{t.cantidad_enviada} {t.unidad}</td>
              </tr>
            ))}
          </tbody>
        </table>

        <h2 style={{ fontSize: 'var(--fs-lg)', marginBottom: 'var(--sp-3)' }}>Constancia de recepción</h2>
        <div className="card" style={{ marginBottom: 'var(--sp-5)' }}>
          {remito.tiene_copia_firmada && !mostrarForm ? (
            <>
              <table className="data-table" style={{ marginBottom: 'var(--sp-4)' }}>
                <tbody>
                  <tr><td>Fecha de recepción</td><td style={{ textAlign: 'left' }}>{formatearFecha(remito.fecha_recepcion)}</td></tr>
                  <tr><td>Recibido por</td><td style={{ textAlign: 'left' }}>{remito.recibido_por}</td></tr>
                </tbody>
              </table>
              <div style={{ display: 'flex', gap: 'var(--sp-3)' }}>
                <button type="button" className="btn btn-secondary" onClick={verCopiaFirmada}>
                  Ver copia firmada
                </button>
                {puedeGestionar && (
                  <button type="button" className="btn btn-ghost" onClick={abrirReemplazo}>
                    Reemplazar
                  </button>
                )}
              </div>
            </>
          ) : puedeGestionar ? (
            <form onSubmit={handleSubmit}>
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
                  disabled={guardando}
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
                  disabled={guardando}
                />
              </div>
              <div className="field" style={{ marginBottom: 0 }}>
                <label className="field-label" htmlFor="pdfCopiaFirmada">Copia firmada (PDF escaneado)</label>
                <input
                  id="pdfCopiaFirmada"
                  className="field-input"
                  type="file"
                  accept="application/pdf"
                  onChange={(e) => setArchivo(e.target.files?.[0] || null)}
                  disabled={guardando}
                />
              </div>

              {errorForm && <div className="alert alert-danger" style={{ marginTop: 'var(--sp-3)' }}>{errorForm}</div>}

              <div style={{ display: 'flex', gap: 'var(--sp-3)', marginTop: 'var(--sp-4)' }}>
                {remito.tiene_copia_firmada && (
                  <button type="button" className="btn btn-ghost" onClick={() => setMostrarForm(false)} disabled={guardando}>
                    Cancelar
                  </button>
                )}
                <button type="submit" className="btn btn-primary" disabled={guardando}>
                  {guardando ? <span className="spinner" /> : 'Adjuntar copia firmada'}
                </button>
              </div>
            </form>
          ) : (
            <p style={{ color: 'var(--ink-2)' }}>Todavía no se adjuntó la copia firmada por el laboratorio.</p>
          )}
        </div>
      </div>
    </div>
  );
}
