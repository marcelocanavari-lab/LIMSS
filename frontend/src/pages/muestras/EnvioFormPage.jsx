import { useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { useAuth } from '../../context/AuthContext';
import TopBar from '../../components/TopBar';
import { muestrasApi } from '../../api/muestras';
import { maestrosApi } from '../../api/maestros';
import { ApiError } from '../../api/client';

export default function EnvioFormPage() {
  const { id } = useParams();
  const navigate = useNavigate();
  const { user } = useAuth();
  const esAdminQa = ['admin', 'qa'].includes(user?.rol);

  const [laboratorios, setLaboratorios] = useState([]);
  const [testigos, setTestigos] = useState([]);
  const [cargando, setCargando] = useState(true);
  const [error, setError] = useState('');

  const [idLaboratorio, setIdLaboratorio] = useState('');
  const [idTestigo, setIdTestigo] = useState('');
  const [cantidadTestigo, setCantidadTestigo] = useState('');
  const [temperatura, setTemperatura] = useState('');
  const [nroRemito, setNroRemito] = useState('');
  const [transportista, setTransportista] = useState('');
  const [analisis, setAnalisis] = useState('');
  const [protocolo, setProtocolo] = useState('');
  const [guardando, setGuardando] = useState(false);

  useEffect(() => {
    Promise.all([muestrasApi.listarLaboratorios(true), maestrosApi.listarTestigos({ activo: true })])
      .then(([labs, tests]) => {
        setLaboratorios(labs);
        setTestigos(tests);
      })
      .catch((err) => setError(err instanceof ApiError ? err.message : 'No se pudieron cargar los datos'))
      .finally(() => setCargando(false));
  }, []);

  const testigoSeleccionado = testigos.find((t) => String(t.id_testigo) === String(idTestigo));

  async function handleSubmit(e) {
    e.preventDefault();
    setError('');

    if (!idLaboratorio) {
      setError('Seleccioná un laboratorio');
      return;
    }
    if (testigoSeleccionado?.vencido) {
      setError(`El testigo "${testigoSeleccionado.codigo}" está vencido — no se puede enviar`);
      return;
    }
    if (idTestigo && !cantidadTestigo) {
      setError('Indicá la cantidad de testigo a enviar');
      return;
    }

    setGuardando(true);
    try {
      const resultado = await muestrasApi.confirmarEnvio(id, {
        id_laboratorio: Number(idLaboratorio),
        id_testigo: idTestigo ? Number(idTestigo) : null,
        cantidad_testigo: idTestigo ? Number(cantidadTestigo) : null,
        temperatura_transporte: temperatura.trim() || null,
        nro_remito: nroRemito.trim() || null,
        transportista: transportista.trim() || null,
        analisis_solicitados: analisis.trim() || null,
        protocolo_utilizar: protocolo.trim() || null,
      });

      if (resultado.alerta_testigo_por_vencer) {
        window.alert('Atención: el testigo enviado vence en menos de 30 días.');
      }
      if (resultado.alerta_reorden) {
        window.alert('Atención: el stock del testigo quedó por debajo del mínimo. Se recomienda reabastecer.');
      }

      navigate(`/muestras/${id}/remito`, { replace: true });
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'No se pudo confirmar el envío');
    } finally {
      setGuardando(false);
    }
  }

  if (cargando) {
    return (
      <div className="screen" style={{ alignItems: 'center', justifyContent: 'center' }}>
        <span className="spinner" />
      </div>
    );
  }

  return (
    <div className="screen">
      <TopBar titulo="Confirmar envío" subtitulo="Muestras" onBack={() => navigate(`/muestras/${id}`)} />
      <div className="screen-content">
        <form onSubmit={handleSubmit}>
          <div className="card" style={{ marginBottom: 'var(--sp-5)' }}>
            <div className="field">
              <label className="field-label" htmlFor="laboratorio">Laboratorio externo</label>
              <select id="laboratorio" className="field-input" value={idLaboratorio} onChange={(e) => setIdLaboratorio(e.target.value)}>
                <option value="">Seleccioná un laboratorio...</option>
                {laboratorios.map((l) => (
                  <option key={l.id_laboratorio} value={l.id_laboratorio}>{l.nombre}</option>
                ))}
              </select>
              {esAdminQa && (
                <button type="button" className="btn btn-ghost" style={{ alignSelf: 'flex-start', padding: 0 }} onClick={() => navigate('/muestras/laboratorios')}>
                  + Agregar laboratorio
                </button>
              )}
            </div>

            <div className="field">
              <label className="field-label" htmlFor="nroRemito">Número de remito</label>
              <input id="nroRemito" className="field-input" value={nroRemito} onChange={(e) => setNroRemito(e.target.value)} />
            </div>

            <div className="field">
              <label className="field-label" htmlFor="transportista">Transportista</label>
              <input id="transportista" className="field-input" value={transportista} onChange={(e) => setTransportista(e.target.value)} />
            </div>

            <div className="field">
              <label className="field-label" htmlFor="temperatura">Temperatura de transporte</label>
              <input id="temperatura" className="field-input" placeholder="Ej. 2-8°C, ambiente..." value={temperatura} onChange={(e) => setTemperatura(e.target.value)} />
            </div>

            <div className="field">
              <label className="field-label" htmlFor="analisis">Análisis a realizar</label>
              <input id="analisis" className="field-input" value={analisis} onChange={(e) => setAnalisis(e.target.value)} />
            </div>

            <div className="field">
              <label className="field-label" htmlFor="protocolo">Protocolo a utilizar</label>
              <input id="protocolo" className="field-input" value={protocolo} onChange={(e) => setProtocolo(e.target.value)} />
            </div>
          </div>

          <div className="card" style={{ marginBottom: 'var(--sp-5)' }}>
            <h2 style={{ fontSize: 'var(--fs-lg)', marginBottom: 'var(--sp-3)' }}>Testigo (opcional)</h2>
            <div className="field">
              <label className="field-label" htmlFor="testigo">Testigo a enviar</label>
              <select id="testigo" className="field-input" value={idTestigo} onChange={(e) => setIdTestigo(e.target.value)}>
                <option value="">Sin testigo</option>
                {testigos.map((t) => (
                  <option key={t.id_testigo} value={t.id_testigo}>
                    {t.codigo} — {t.nombre} {t.vencido ? '(VENCIDO)' : t.por_vencer ? '(vence pronto)' : ''}
                  </option>
                ))}
              </select>
            </div>

            {testigoSeleccionado?.vencido && (
              <div className="alert alert-danger">
                El testigo "{testigoSeleccionado.codigo}" está VENCIDO ({testigoSeleccionado.fecha_vencimiento}). No se puede confirmar el envío con este testigo.
              </div>
            )}
            {!testigoSeleccionado?.vencido && testigoSeleccionado?.por_vencer && (
              <div className="alert alert-warn">
                El testigo "{testigoSeleccionado.codigo}" vence en menos de 30 días ({testigoSeleccionado.fecha_vencimiento}).
              </div>
            )}

            {idTestigo && (
              <div className="field">
                <label className="field-label" htmlFor="cantidadTestigo">
                  Cantidad a enviar (stock disponible: {testigoSeleccionado?.stock_actual} {testigoSeleccionado?.unidad_medida || ''})
                </label>
                <input
                  id="cantidadTestigo"
                  className="field-input"
                  type="number"
                  step="any"
                  min="0"
                  value={cantidadTestigo}
                  onChange={(e) => setCantidadTestigo(e.target.value)}
                />
              </div>
            )}
          </div>

          {error && <div className="alert alert-danger" style={{ marginBottom: 'var(--sp-4)' }}>{error}</div>}

          <button type="submit" className="btn btn-primary btn-block btn-lg" disabled={guardando || testigoSeleccionado?.vencido}>
            {guardando ? <span className="spinner" /> : 'Confirmar envío'}
          </button>
        </form>
      </div>
    </div>
  );
}
