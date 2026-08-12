import { Fragment, useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import TopBar from '../../components/TopBar';
import { facturasApi } from '../../api/facturas';
import { muestrasApi } from '../../api/muestras';
import { ApiError } from '../../api/client';

const MONEDAS = ['ARS', 'USD', 'EUR'];

export default function FacturaFormPage({ modo }) {
  const esEdicion = modo === 'editar';
  const { id } = useParams();
  const navigate = useNavigate();

  const [laboratorios, setLaboratorios] = useState([]);
  const [idLaboratorio, setIdLaboratorio] = useState('');
  const [nroFactura, setNroFactura] = useState('');
  const [fechaFactura, setFechaFactura] = useState('');
  const [fechaRecepcion, setFechaRecepcion] = useState('');
  const [monto, setMonto] = useState('');
  const [moneda, setMoneda] = useState('ARS');
  const [descripcion, setDescripcion] = useState('');

  const [enviosDisponibles, setEnviosDisponibles] = useState([]);
  const [idsSeleccionados, setIdsSeleccionados] = useState([]);
  const [cargandoEnvios, setCargandoEnvios] = useState(false);
  const [importes, setImportes] = useState({});

  const [loading, setLoading] = useState(esEdicion);
  const [guardando, setGuardando] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    muestrasApi.listarLaboratorios(true).then(setLaboratorios).catch(() => {});
  }, []);

  useEffect(() => {
    if (!esEdicion) return;
    facturasApi
      .obtenerFactura(id)
      .then((f) => {
        setIdLaboratorio(String(f.id_laboratorio));
        setNroFactura(f.nro_factura);
        setFechaFactura(f.fecha_factura);
        setFechaRecepcion(f.fecha_recepcion || '');
        setMonto(String(f.monto));
        setMoneda(f.moneda);
        setDescripcion(f.descripcion || '');
        setIdsSeleccionados(f.envios.map((e) => e.id_envio));
      })
      .catch((err) => setError(err instanceof ApiError ? err.message : 'No se pudo cargar la factura'))
      .finally(() => setLoading(false));
  }, [esEdicion, id]);

  // Al elegir (o cambiar de) laboratorio, cargar sus envíos sin facturar. En
  // edición, además hay que incluir los que ya están vinculados a ESTA
  // factura (que ya no figuran como "sin facturar") para que sigan
  // apareciendo tildados en la lista.
  useEffect(() => {
    if (!idLaboratorio) {
      setEnviosDisponibles([]);
      return;
    }
    setCargandoEnvios(true);
    Promise.all([
      facturasApi.enviosSinFacturar(idLaboratorio),
      esEdicion ? facturasApi.obtenerFactura(id) : Promise.resolve(null),
    ])
      .then(([sinFacturar, facturaActual]) => {
        const vinculadosActuales = facturaActual
          ? facturaActual.envios.map((e) => ({
              id_envio: e.id_envio, nro_remito: e.nro_remito, codigo_muestra: e.codigo_muestra,
              fecha_despacho: e.fecha_despacho, id_laboratorio: facturaActual.id_laboratorio,
              laboratorio_nombre: facturaActual.laboratorio_nombre,
              erp_CODART: e.erp_CODART, erp_DESART: e.erp_DESART, erp_nro_ir: e.erp_nro_ir,
              lote_proveedor: e.lote_proveedor,
              cantidad_ensayos: e.cantidad_ensayos, ensayos: e.ensayos || [],
            }))
          : [];
        const combinados = [...vinculadosActuales];
        for (const env of sinFacturar) {
          if (!combinados.some((e) => e.id_envio === env.id_envio)) combinados.push(env);
        }
        setEnviosDisponibles(combinados);

        // Los importes ya guardados (edición) se precargan para poder
        // modificarlos; los envíos nuevos arrancan sin importe cargado.
        const seed = {};
        for (const env of vinculadosActuales) {
          for (const ens of env.ensayos || []) {
            if (ens.importe != null) seed[ens.id_envio_ensayo] = String(ens.importe);
          }
        }
        if (Object.keys(seed).length > 0) {
          setImportes((prev) => ({ ...seed, ...prev }));
        }
      })
      .catch(() => setEnviosDisponibles([]))
      .finally(() => setCargandoEnvios(false));
  }, [idLaboratorio, esEdicion, id]);

  function toggleEnvio(idEnvio) {
    setIdsSeleccionados((prev) =>
      prev.includes(idEnvio) ? prev.filter((i) => i !== idEnvio) : [...prev, idEnvio]
    );
  }

  function handleImporteChange(idEnvioEnsayo, valor) {
    setImportes((prev) => ({ ...prev, [idEnvioEnsayo]: valor }));
  }

  // Ensayos de los envíos actualmente elegidos -- determina qué se manda al
  // guardar y qué se suma en el total desglosado (los importes cargados para
  // un envío que se desmarcó después no se incluyen).
  const ensayosSeleccionados = enviosDisponibles
    .filter((en) => idsSeleccionados.includes(en.id_envio))
    .flatMap((en) => en.ensayos || []);

  const totalDesglosado = ensayosSeleccionados.reduce(
    (acc, ens) => acc + (Number(importes[ens.id_envio_ensayo]) || 0), 0
  );

  const totalNoCoincide = monto !== '' && Math.abs(totalDesglosado - Number(monto)) > 0.01;

  async function handleSubmit(e) {
    e.preventDefault();
    setError('');

    if (!esEdicion && !idLaboratorio) {
      setError('Seleccioná un laboratorio');
      return;
    }
    if (!nroFactura.trim() || !fechaFactura || !monto) {
      setError('Completá todos los campos obligatorios');
      return;
    }

    const body = {
      nro_factura: nroFactura.trim(),
      fecha_factura: fechaFactura,
      fecha_recepcion: fechaRecepcion || null,
      monto: Number(monto),
      moneda,
      descripcion: descripcion.trim() || null,
      id_envios: idsSeleccionados,
      detalle_ensayos: ensayosSeleccionados
        .filter((ens) => importes[ens.id_envio_ensayo] !== undefined && importes[ens.id_envio_ensayo] !== '')
        .map((ens) => ({ id_envio_ensayo: ens.id_envio_ensayo, importe: Number(importes[ens.id_envio_ensayo]) })),
    };

    setGuardando(true);
    try {
      if (esEdicion) {
        await facturasApi.editarFactura(id, body);
        navigate(`/facturas/${id}`, { replace: true });
      } else {
        const factura = await facturasApi.crearFactura({ ...body, id_laboratorio: Number(idLaboratorio) });
        navigate(`/facturas/${factura.id_factura}`, { replace: true });
      }
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'No se pudo guardar la factura');
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

  return (
    <div className="screen">
      <TopBar
        titulo={esEdicion ? 'Editar factura' : 'Nueva factura'}
        subtitulo="Facturación de Laboratorios"
        onBack={() => navigate(-1)}
      />
      <div className="screen-content">
        <form onSubmit={handleSubmit}>
          <div className="card" style={{ marginBottom: 'var(--sp-5)' }}>
            <div className="field">
              <label className="field-label" htmlFor="laboratorio">Laboratorio</label>
              {esEdicion ? (
                <input
                  id="laboratorio"
                  className="field-input"
                  value={laboratorios.find((l) => String(l.id_laboratorio) === idLaboratorio)?.nombre || ''}
                  disabled
                />
              ) : (
                <select
                  id="laboratorio"
                  className="field-input"
                  value={idLaboratorio}
                  onChange={(e) => { setIdLaboratorio(e.target.value); setIdsSeleccionados([]); setImportes({}); }}
                  disabled={guardando}
                >
                  <option value="">Seleccioná un laboratorio...</option>
                  {laboratorios.map((l) => (
                    <option key={l.id_laboratorio} value={l.id_laboratorio}>{l.nombre}</option>
                  ))}
                </select>
              )}
            </div>

            <div className="field">
              <label className="field-label" htmlFor="nroFactura">N° de factura</label>
              <input
                id="nroFactura"
                className="field-input"
                value={nroFactura}
                onChange={(e) => setNroFactura(e.target.value)}
                disabled={guardando}
              />
            </div>

            <div style={{ display: 'flex', gap: 'var(--sp-3)' }}>
              <div className="field" style={{ flex: 1 }}>
                <label className="field-label" htmlFor="fechaFactura">Fecha de factura</label>
                <input
                  id="fechaFactura"
                  className="field-input"
                  type="date"
                  value={fechaFactura}
                  onChange={(e) => setFechaFactura(e.target.value)}
                  disabled={guardando}
                />
              </div>
              <div className="field" style={{ flex: 1 }}>
                <label className="field-label" htmlFor="fechaRecepcion">Fecha de recepción (opcional)</label>
                <input
                  id="fechaRecepcion"
                  className="field-input"
                  type="date"
                  value={fechaRecepcion}
                  onChange={(e) => setFechaRecepcion(e.target.value)}
                  disabled={guardando}
                />
              </div>
            </div>

            <div style={{ display: 'flex', gap: 'var(--sp-3)' }}>
              <div className="field" style={{ flex: 1 }}>
                <label className="field-label" htmlFor="monto">Monto</label>
                <input
                  id="monto"
                  className="field-input"
                  type="number"
                  step="any"
                  min="0"
                  value={monto}
                  onChange={(e) => setMonto(e.target.value)}
                  disabled={guardando}
                />
              </div>
              <div className="field" style={{ flex: '0 0 120px' }}>
                <label className="field-label" htmlFor="moneda">Moneda</label>
                <select id="moneda" className="field-input" value={moneda} onChange={(e) => setMoneda(e.target.value)} disabled={guardando}>
                  {MONEDAS.map((m) => (
                    <option key={m} value={m}>{m}</option>
                  ))}
                </select>
              </div>
            </div>

            <div className="field" style={{ marginBottom: 0 }}>
              <label className="field-label" htmlFor="descripcion">Descripción (opcional)</label>
              <textarea
                id="descripcion"
                className="field-input"
                rows={3}
                value={descripcion}
                onChange={(e) => setDescripcion(e.target.value)}
                disabled={guardando}
              />
            </div>
          </div>

          <div className="card" style={{ marginBottom: 'var(--sp-5)' }}>
            <h2 style={{ fontSize: 'var(--fs-lg)', marginBottom: 'var(--sp-3)' }}>Envíos vinculados</h2>
            {!idLaboratorio ? (
              <p style={{ color: 'var(--ink-2)' }}>Seleccioná un laboratorio para ver sus envíos.</p>
            ) : cargandoEnvios ? (
              <div className="state-block"><span className="spinner" /></div>
            ) : enviosDisponibles.length === 0 ? (
              <p style={{ color: 'var(--ink-2)' }}>Este laboratorio no tiene envíos sin facturar.</p>
            ) : (
              <div className="table-scroll">
                <table className="data-table">
                  <thead>
                    <tr>
                      <th></th>
                      <th>N° Remito</th>
                      <th>Muestra</th>
                      <th>IR</th>
                      <th>Lote</th>
                      <th>Material</th>
                      <th>Fecha</th>
                      <th>Ensayos</th>
                    </tr>
                  </thead>
                  <tbody>
                    {enviosDisponibles.map((en) => {
                      const elegido = idsSeleccionados.includes(en.id_envio);
                      return (
                        <Fragment key={en.id_envio}>
                          <tr>
                            <td>
                              <input type="checkbox" checked={elegido} onChange={() => toggleEnvio(en.id_envio)} disabled={guardando} />
                            </td>
                            <td style={{ fontFamily: 'var(--font-mono)' }}>{en.nro_remito || '—'}</td>
                            <td>{en.codigo_muestra || '—'}</td>
                            <td>{en.erp_nro_ir || '—'}</td>
                            <td>{en.lote_proveedor || '—'}</td>
                            <td>{en.erp_DESART ? `${en.erp_DESART}${en.erp_CODART ? ` (${en.erp_CODART})` : ''}` : '—'}</td>
                            <td>{new Date(en.fecha_despacho).toLocaleDateString()}</td>
                            <td className="num">{en.cantidad_ensayos}</td>
                          </tr>
                          {elegido && en.ensayos && en.ensayos.length > 0 && (
                            <tr>
                              <td></td>
                              <td colSpan={7} style={{ paddingTop: 0 }}>
                                <table className="data-table" style={{ marginBottom: 'var(--sp-2)' }}>
                                  <thead>
                                    <tr>
                                      <th>Ensayo</th>
                                      <th style={{ width: 160 }}>Importe</th>
                                    </tr>
                                  </thead>
                                  <tbody>
                                    {en.ensayos.map((ens) => (
                                      <tr key={ens.id_envio_ensayo}>
                                        <td>{ens.analito ? `${ens.nombre_ensayo} — ${ens.analito}` : ens.nombre_ensayo}</td>
                                        <td>
                                          <input
                                            className="field-input"
                                            type="number"
                                            step="any"
                                            min="0"
                                            placeholder="0.00"
                                            value={importes[ens.id_envio_ensayo] ?? ''}
                                            onChange={(e) => handleImporteChange(ens.id_envio_ensayo, e.target.value)}
                                            disabled={guardando}
                                          />
                                        </td>
                                      </tr>
                                    ))}
                                  </tbody>
                                </table>
                              </td>
                            </tr>
                          )}
                        </Fragment>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}

            {ensayosSeleccionados.length > 0 && (
              <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 'var(--sp-2)', marginTop: 'var(--sp-3)', fontSize: 'var(--fs-sm)' }}>
                <span style={{ color: 'var(--ink-2)' }}>Total desglosado:</span>
                <strong>{moneda} {totalDesglosado.toFixed(2)}</strong>
              </div>
            )}
            {totalNoCoincide && (
              <div className="alert alert-warn" style={{ marginTop: 'var(--sp-3)' }}>
                El total desglosado ({moneda} {totalDesglosado.toFixed(2)}) no coincide con el monto de la factura ({moneda} {Number(monto).toFixed(2)}).
              </div>
            )}
          </div>

          {error && <div className="alert alert-danger" style={{ marginBottom: 'var(--sp-4)' }}>{error}</div>}

          <button type="submit" className="btn btn-primary btn-block btn-lg" disabled={guardando}>
            {guardando ? <span className="spinner" /> : esEdicion ? 'Guardar cambios' : 'Crear factura'}
          </button>
        </form>
      </div>
    </div>
  );
}
