import { useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { useAuth } from '../../context/AuthContext';
import TopBar from '../../components/TopBar';
import { muestrasApi } from '../../api/muestras';
import { maestrosApi } from '../../api/maestros';
import { testigosRemitosApi } from '../../api/testigosRemitos';
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
  const [sinTestigosEnviados, setSinTestigosEnviados] = useState(false);
  const [error, setError] = useState('');

  const [idLaboratorio, setIdLaboratorio] = useState('');
  const [contactos, setContactos] = useState([]);
  const [idContacto, setIdContacto] = useState('');
  const [temperatura, setTemperatura] = useState('');
  const [transportista, setTransportista] = useState('');
  const [guardando, setGuardando] = useState(false);

  const [advertenciasStock, setAdvertenciasStock] = useState([]);
  const [mostrarAdvertencias, setMostrarAdvertencias] = useState(false);

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

  useEffect(() => {
    if (!idLaboratorio) {
      setSinTestigosEnviados(false);
      return;
    }
    testigosRemitosApi
      .listarRemitos({ idLaboratorio })
      .then((remitos) => setSinTestigosEnviados(remitos.length === 0))
      .catch(() => setSinTestigosEnviados(false));
  }, [idLaboratorio]);

  useEffect(() => {
    setIdContacto('');
    if (!idLaboratorio) {
      setContactos([]);
      return;
    }
    muestrasApi
      .listarContactos(idLaboratorio)
      .then(setContactos)
      .catch(() => setContactos([]));
  }, [idLaboratorio]);

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

  const sinEnsayosLab = !!idLaboratorio && !cargandoEnsayos && ensayosEspec.length === 0;

  // Advertencias no bloqueantes sobre el stock de los testigos elegidos --
  // se calculan con los datos ya cargados en pantalla (laboratorios[] y
  // stock_bajo ya vienen en la lista de testigos), sin pegarle de nuevo al
  // backend.
  function calcularAdvertenciasStock() {
    const laboratorioNombre = laboratorios.find((l) => l.id_laboratorio === Number(idLaboratorio))?.nombre || 'este laboratorio';
    const advertencias = [];
    for (const idTestigo of idsTestigoElegidos) {
      const t = detalleTestigo(idTestigo);
      if (!t) continue;

      const asignacion = (t.laboratorios || []).find((l) => l.id_laboratorio === Number(idLaboratorio));
      if (!asignacion || asignacion.consumo_estimado == null) {
        advertencias.push(
          `El testigo ${t.nombre} no tiene consumo estimado configurado para ${laboratorioNombre} — el stock no se descontará automáticamente al confirmar este envío.`
        );
      }
      if (t.stock_bajo) {
        advertencias.push(
          `El testigo ${t.nombre} está en stock crítico (${t.stock_actual} ${t.unidad_medida || ''}, mínimo ${t.stock_minimo}).`
        );
      }
    }
    return advertencias;
  }

  function handleSubmit(e) {
    e.preventDefault();
    setError('');

    if (!idLaboratorio) {
      setError('Seleccioná un laboratorio');
      return;
    }
    if (sinEnsayosLab) {
      setError('El laboratorio seleccionado no tiene ensayos asignados para este producto. Verificá la configuración en Datos Maestros.');
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

    const advertencias = calcularAdvertenciasStock();
    if (advertencias.length > 0) {
      setAdvertenciasStock(advertencias);
      setMostrarAdvertencias(true);
      return;
    }

    confirmarEnvioReal();
  }

  async function confirmarEnvioReal() {
    setMostrarAdvertencias(false);
    setGuardando(true);
    try {
      const resultado = await muestrasApi.confirmarEnvio(id, {
        id_laboratorio: Number(idLaboratorio),
        id_contacto: idContacto ? Number(idContacto) : null,
        testigos: idsTestigoElegidos.map((idT) => ({ id_testigo: idT })),
        temperatura_transporte: temperatura.trim() || null,
        transportista: transportista.trim() || null,
        id_espec_ensayo: idsEnsayoElegidos,
      });

      if (resultado.alerta_testigo_por_vencer) {
        window.alert('Atención: el testigo enviado vence en menos de 30 días.');
      }
      if (resultado.alerta_reorden) {
        window.alert('Atención: el stock del testigo quedó bajo (o negativo) tras descontar el consumo de este envío. Hay que reponerlo.');
      }

      navigate(`/muestras/${id}/envios/${resultado.id_envio}/remito`, { replace: true });
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
      <TopBar titulo="Nuevo envío" subtitulo="Envío de Muestras" onBack={() => navigate(-1)} />
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
              {idLaboratorio && sinTestigosEnviados && (
                <div className="alert alert-warn" style={{ marginTop: 'var(--sp-2)' }}>
                  Este laboratorio no tiene testigos enviados registrados. Verificá antes de continuar.
                </div>
              )}
            </div>

            {idLaboratorio && contactos.length > 0 && (
              <div className="field">
                <label className="field-label" htmlFor="contacto">Dirigido a (opcional)</label>
                <select id="contacto" className="field-input" value={idContacto} onChange={(e) => setIdContacto(e.target.value)}>
                  <option value="">Sin especificar</option>
                  {contactos.map((c) => (
                    <option key={c.id_contacto} value={c.id_contacto}>
                      {c.nombre}{c.cargo ? ` — ${c.cargo}` : ''}
                    </option>
                  ))}
                </select>
              </div>
            )}

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
              ) : sinEnsayosLab ? (
                <div className="alert alert-danger">
                  El laboratorio seleccionado no tiene ensayos asignados para este producto. Verificá la configuración en Datos Maestros.
                </div>
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

          <button
            type="submit"
            className="btn btn-primary btn-block btn-lg"
            disabled={guardando || !idLaboratorio || sinEnsayosLab || testigosVencidosElegidos.length > 0}
          >
            {guardando ? <span className="spinner" /> : 'Confirmar envío'}
          </button>
        </form>
      </div>

      {mostrarAdvertencias && (
        <div
          style={{
            position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.5)',
            display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 100, padding: 'var(--sp-4)',
          }}
          onClick={() => setMostrarAdvertencias(false)}
        >
          <div className="card" style={{ width: '90%', maxWidth: 480 }} onClick={(e) => e.stopPropagation()}>
            <h2 style={{ fontSize: 'var(--fs-lg)', marginBottom: 'var(--sp-3)' }}>Antes de confirmar</h2>

            {advertenciasStock.map((texto, i) => (
              <div key={i} className="alert alert-warn" style={{ marginBottom: 'var(--sp-3)' }}>{texto}</div>
            ))}

            <p style={{ color: 'var(--ink-2)', fontSize: 'var(--fs-sm)', marginBottom: 'var(--sp-4)' }}>
              Podés continuar igual y generar el remito, o volver y revisar los testigos.
            </p>

            <div style={{ display: 'flex', gap: 'var(--sp-3)' }}>
              <button type="button" className="btn btn-ghost" onClick={() => setMostrarAdvertencias(false)} disabled={guardando}>
                Volver
              </button>
              <button type="button" className="btn btn-primary" onClick={confirmarEnvioReal} disabled={guardando}>
                {guardando ? <span className="spinner" /> : 'Continuar y confirmar envío'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
