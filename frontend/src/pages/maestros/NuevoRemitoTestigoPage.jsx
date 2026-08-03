import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import TopBar from '../../components/TopBar';
import { muestrasApi } from '../../api/muestras';
import { maestrosApi } from '../../api/maestros';
import { testigosRemitosApi } from '../../api/testigosRemitos';
import { ApiError, abrirPdfConAuth } from '../../api/client';

function hoyISO() {
  const hoy = new Date();
  const mes = String(hoy.getMonth() + 1).padStart(2, '0');
  const dia = String(hoy.getDate()).padStart(2, '0');
  return `${hoy.getFullYear()}-${mes}-${dia}`;
}

export default function NuevoRemitoTestigoPage() {
  const navigate = useNavigate();

  const [laboratorios, setLaboratorios] = useState([]);
  const [testigos, setTestigos] = useState([]);
  const [cargando, setCargando] = useState(true);
  const [error, setError] = useState('');

  const [idLaboratorio, setIdLaboratorio] = useState('');
  const [contactos, setContactos] = useState([]);
  const [idContacto, setIdContacto] = useState('');
  const [fechaEnvio, setFechaEnvio] = useState(hoyISO());
  const [observaciones, setObservaciones] = useState('');
  const [idsSeleccionados, setIdsSeleccionados] = useState([]);
  const [cantidades, setCantidades] = useState({});
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

  function toggleTestigo(idTestigo) {
    setIdsSeleccionados((prev) =>
      prev.includes(idTestigo) ? prev.filter((i) => i !== idTestigo) : [...prev, idTestigo]
    );
  }

  async function handleSubmit(e) {
    e.preventDefault();
    setError('');

    if (!idLaboratorio) {
      setError('Seleccioná un laboratorio');
      return;
    }
    if (idsSeleccionados.length === 0) {
      setError('Seleccioná al menos un testigo');
      return;
    }

    const items = [];
    for (const idTestigo of idsSeleccionados) {
      const testigo = testigos.find((t) => t.id_testigo === idTestigo);
      const cantidad = Number(cantidades[idTestigo]);
      if (!cantidades[idTestigo] || Number.isNaN(cantidad) || cantidad <= 0) {
        setError(`Indicá una cantidad válida para "${testigo.nombre}"`);
        return;
      }
      if (cantidad > testigo.stock_actual) {
        setError(`La cantidad para "${testigo.nombre}" supera el stock disponible (${testigo.stock_actual})`);
        return;
      }
      items.push({ id_testigo: idTestigo, cantidad_enviada: cantidad, unidad: testigo.unidad_medida || 'u' });
    }

    setGuardando(true);
    try {
      const remito = await testigosRemitosApi.crearRemito({
        id_laboratorio: Number(idLaboratorio),
        id_contacto: idContacto ? Number(idContacto) : null,
        fecha_envio: fechaEnvio,
        observaciones: observaciones.trim() || null,
        testigos: items,
      });

      try {
        await abrirPdfConAuth(`/api/testigos/remitos/${remito.id_remito}/pdf`);
      } catch {
        // el remito ya se generó igual; si falla la descarga del PDF no bloqueamos la navegación
      }

      navigate('/maestros/testigos/remitos', { replace: true });
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'No se pudo generar el remito');
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
      <TopBar titulo="Nuevo remito de testigos" subtitulo="Datos Maestros" onBack={() => navigate(-1)} />
      <div className="screen-content">
        <form onSubmit={handleSubmit}>
          <div className="card" style={{ marginBottom: 'var(--sp-5)' }}>
            <div className="field">
              <label className="field-label" htmlFor="laboratorio">Laboratorio</label>
              <select id="laboratorio" className="field-input" value={idLaboratorio} onChange={(e) => setIdLaboratorio(e.target.value)} disabled={guardando}>
                <option value="">Seleccioná un laboratorio...</option>
                {laboratorios.map((l) => (
                  <option key={l.id_laboratorio} value={l.id_laboratorio}>{l.nombre}</option>
                ))}
              </select>
            </div>

            {contactos.length > 0 && (
              <div className="field">
                <label className="field-label" htmlFor="contacto">Dirigido a (opcional)</label>
                <select id="contacto" className="field-input" value={idContacto} onChange={(e) => setIdContacto(e.target.value)} disabled={guardando}>
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
              <label className="field-label" htmlFor="fechaEnvio">Fecha de envío</label>
              <input
                id="fechaEnvio"
                className="field-input"
                type="date"
                value={fechaEnvio}
                onChange={(e) => setFechaEnvio(e.target.value)}
                disabled={guardando}
              />
            </div>

            <div className="field" style={{ marginBottom: 0 }}>
              <label className="field-label" htmlFor="observaciones">Observaciones (opcional)</label>
              <input
                id="observaciones"
                className="field-input"
                value={observaciones}
                onChange={(e) => setObservaciones(e.target.value)}
                disabled={guardando}
              />
            </div>
          </div>

          <div className="card" style={{ marginBottom: 'var(--sp-5)' }}>
            <h2 style={{ fontSize: 'var(--fs-lg)', marginBottom: 'var(--sp-3)' }}>Testigos disponibles</h2>
            {testigos.length === 0 ? (
              <p style={{ color: 'var(--ink-2)' }}>No hay testigos activos cargados.</p>
            ) : (
              <div className="table-scroll">
                <table className="data-table">
                  <thead>
                    <tr>
                      <th></th>
                      <th>N° IR</th>
                      <th>Nombre</th>
                      <th>Lote</th>
                      <th>Stock disponible</th>
                      <th>Vencimiento</th>
                      <th>Cantidad a enviar</th>
                    </tr>
                  </thead>
                  <tbody>
                    {testigos.map((t) => {
                      const elegido = idsSeleccionados.includes(t.id_testigo);
                      return (
                        <tr key={t.id_testigo}>
                          <td>
                            <input type="checkbox" checked={elegido} onChange={() => toggleTestigo(t.id_testigo)} disabled={guardando} />
                          </td>
                          <td>{t.nro_ir || '—'}</td>
                          <td>{t.nombre}</td>
                          <td>{t.nro_lote}</td>
                          <td className="num">{t.stock_actual} {t.unidad_medida || ''}</td>
                          <td>{t.fecha_vencimiento || '—'}</td>
                          <td>
                            {elegido && (
                              <input
                                className="field-input"
                                type="number"
                                step="any"
                                min="0"
                                max={t.stock_actual}
                                style={{ maxWidth: 120 }}
                                value={cantidades[t.id_testigo] || ''}
                                onChange={(e) => setCantidades((prev) => ({ ...prev, [t.id_testigo]: e.target.value }))}
                                disabled={guardando}
                              />
                            )}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </div>

          {error && <div className="alert alert-danger" style={{ marginBottom: 'var(--sp-4)' }}>{error}</div>}

          <button type="submit" className="btn btn-primary btn-block btn-lg" disabled={guardando}>
            {guardando ? <span className="spinner" /> : 'Generar remito y PDF →'}
          </button>
        </form>
      </div>
    </div>
  );
}
