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
  const esAdminQa = ['analista_qc', 'admin', 'qa'].includes(user?.rol);

  const [laboratorios, setLaboratorios] = useState([]);
  const [testigos, setTestigos] = useState([]);
  const [testigosEspec, setTestigosEspec] = useState([]);
  const [ensayosEspec, setEnsayosEspec] = useState([]);
  const [idsEnsayoElegidos, setIdsEnsayoElegidos] = useState([]);
  const [idsTestigoElegidos, setIdsTestigoElegidos] = useState([]);
  const [cargando, setCargando] = useState(true);
  const [cargandoEnsayos, setCargandoEnsayos] = useState(false);
  const [error, setError] = useState('');

  const [idLaboratorio, setIdLaboratorio] = useState('');
  const [temperatura, setTemperatura] = useState('');
  const [transportista, setTransportista] = useState('');
  const [guardando, setGuardando] = useState(false);

  useEffect(() => {
    Promise.all([muestrasApi.listarLaboratorios(true), maestrosApi.listarTestigos({ activo: true }), muestrasApi.obtenerMuestra(id)])
      .then(([labs, tests, muestra]) => {
        setLaboratorios(labs);
        setTestigos(tests);
        if (muestra.id_especificacion) {
          return maestrosApi.listarTestigosEspecificacion(muestra.id_especificacion).then(setTestigosEspec);
        }
      })
      .catch((err) => setError(err instanceof ApiError ? err.message : 'No se pudieron cargar los datos'))
      .finally(() => setCargando(false));
  }, [id]);

  useEffect(() => {
    if (!idLaboratorio) {
      setEnsayosEspec([]);
      setIdsEnsayoElegidos([]);
      return;
    }
    setCargandoEnsayos(true);
    muestrasApi
      .ensayosParaEnvio(id, idLaboratorio)
      .then((es) => {
        setEnsayosEspec(es);
        setIdsEnsayoElegidos(es.map((e) => e.id_espec_ensayo));
      })
      .catch((err) => setError(err instanceof ApiError ? err.message : 'No se pudieron cargar los ensayos'))
      .finally(() => setCargandoEnsayos(false));
  }, [id, idLaboratorio]);

  function toggleEnsayo(idEnsayo) {
    setIdsEnsayoElegidos((prev) =>
      prev.includes(idEnsayo) ? prev.filter((i) => i !== idEnsayo) : [...prev, idEnsayo]
    );
  }

  function toggleTestigo(idTestigo) {
    setIdsTestigoElegidos((prev) =>
      prev.includes(idTestigo) ? prev.filter((i) => i !== idTestigo) : [...prev, idTestigo]
    );
  }

  function detalleTestigo(idTestigo) {
    return testigos.find((t) => t.id_testigo === idTestigo);
  }

  const testigosVencidosElegidos = idsTestigoElegidos
    .map(detalleTestigo)
    .filter((t) => t?.vencido);

  async function handleSubmit(e) {
    e.preventDefault();
    setError('');

    if (!idLaboratorio) {
      setError('Seleccioná un laboratorio');
      return;
    }
    if (testigosVencidosElegidos.length > 0) {
      setError(`El testigo "${testigosVencidosElegidos[0].codigo}" está vencido — no se puede enviar`);
      return;
    }
    if (ensayosEspec.length > 0 && idsEnsayoElegidos.length === 0) {
      setError('Seleccioná al menos un ensayo');
      return;
    }

    setGuardando(true);
    try {
      const resultado = await muestrasApi.confirmarEnvio(id, {
        id_laboratorio: Number(idLaboratorio),
        testigos: idsTestigoElegidos.map((idT) => ({ id_testigo: idT })),
        temperatura_transporte: temperatura.trim() || null,
        transportista: transportista.trim() || null,
        id_espec_ensayo: idsEnsayoElegidos,
      });

      if (resultado.alerta_testigo_por_vencer) {
        window.alert('Atención: el testigo enviado vence en menos de 30 días.');
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
              <label className="field-label" htmlFor="laboratorio">Laboratorio</label>
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
              <label className="field-label" htmlFor="transportista">Transportista</label>
              <input id="transportista" className="field-input" value={transportista} onChange={(e) => setTransportista(e.target.value)} />
            </div>

            <div className="field">
              <label className="field-label" htmlFor="temperatura">Temperatura de transporte</label>
              <input id="temperatura" className="field-input" placeholder="Ej. 2-8°C, ambiente..." value={temperatura} onChange={(e) => setTemperatura(e.target.value)} />
            </div>
          </div>

          {idLaboratorio && (
            <div className="card" style={{ marginBottom: 'var(--sp-5)' }}>
              <h2 style={{ fontSize: 'var(--fs-lg)', marginBottom: 'var(--sp-3)' }}>Ensayos solicitados</h2>
              {cargandoEnsayos ? (
                <span className="spinner" />
              ) : ensayosEspec.length === 0 ? (
                <p style={{ color: 'var(--ink-2)' }}>Este laboratorio no tiene ensayos asignados en la especificación de la muestra.</p>
              ) : (
                ensayosEspec.map((en) => (
                  <label key={en.id_espec_ensayo} style={{ display: 'flex', alignItems: 'center', gap: 'var(--sp-2)', marginBottom: 'var(--sp-2)' }}>
                    <input
                      type="checkbox"
                      checked={idsEnsayoElegidos.includes(en.id_espec_ensayo)}
                      onChange={() => toggleEnsayo(en.id_espec_ensayo)}
                    />
                    {en.nombre_ensayo}
                  </label>
                ))
              )}
            </div>
          )}

          <div className="card" style={{ marginBottom: 'var(--sp-5)' }}>
            <h2 style={{ fontSize: 'var(--fs-lg)', marginBottom: 'var(--sp-3)' }}>Testigos (opcional)</h2>
            {testigosEspec.length === 0 && (
              <p style={{ color: 'var(--ink-2)' }}>La especificación de este material no tiene testigos asociados.</p>
            )}
            {testigosEspec.map((te) => {
              const t = detalleTestigo(te.id_testigo);
              const elegido = idsTestigoElegidos.includes(te.id_testigo);
              return (
                <div key={te.id_testigo} style={{ marginBottom: 'var(--sp-3)' }}>
                  <label style={{ display: 'flex', alignItems: 'center', gap: 'var(--sp-2)' }}>
                    <input type="checkbox" checked={elegido} onChange={() => toggleTestigo(te.id_testigo)} />
                    Incluir testigo en este envío: {te.codigo} — {te.nombre}
                    {t?.vencido && <span className="badge badge-danger">VENCIDO</span>}
                    {!t?.vencido && t?.por_vencer && <span className="badge badge-warn">vence pronto</span>}
                  </label>

                  {elegido && (
                    <table className="data-table" style={{ marginTop: 'var(--sp-2)' }}>
                      <tbody>
                        <tr><td>N° IR</td><td style={{ textAlign: 'left' }}>{t?.nro_ir || '—'}</td></tr>
                        <tr><td>Lote</td><td style={{ textAlign: 'left' }}>{t?.nro_lote || '—'}</td></tr>
                        <tr><td>Vencimiento</td><td style={{ textAlign: 'left' }}>{t?.fecha_vencimiento || '—'}</td></tr>
                      </tbody>
                    </table>
                  )}

                  {elegido && t?.vencido && (
                    <div className="alert alert-danger">
                      El testigo "{t.codigo}" está VENCIDO ({t.fecha_vencimiento}). No se puede confirmar el envío con este testigo.
                    </div>
                  )}
                  {elegido && !t?.vencido && t?.por_vencer && (
                    <div className="alert alert-warn">
                      El testigo "{t.codigo}" vence en menos de 30 días ({t.fecha_vencimiento}).
                    </div>
                  )}
                </div>
              );
            })}
          </div>

          {error && <div className="alert alert-danger" style={{ marginBottom: 'var(--sp-4)' }}>{error}</div>}

          <button type="submit" className="btn btn-primary btn-block btn-lg" disabled={guardando || testigosVencidosElegidos.length > 0}>
            {guardando ? <span className="spinner" /> : 'Confirmar envío'}
          </button>
        </form>
      </div>
    </div>
  );
}
