import { useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import TopBar from '../../components/TopBar';
import ChecklistMuestreo from '../../components/ChecklistMuestreo';
import { solicitudesMuestreoApi } from '../../api/solicitudesMuestreo';
import { maestrosApi } from '../../api/maestros';
import { muestrasApi } from '../../api/muestras';
import { ApiError, abrirPdfConAuth } from '../../api/client';

const CAMPO_FISICO_VACIO = {
  identificacion_contenedor: '', fecha_vencimiento_real: '', sin_vencimiento_confirmado: false,
  fecha_reanalisis_real: '',
  aspecto_mp: '', materias_extranas: '', olor: '', color: '',
  observaciones_muestreo: '', nro_bultos_muestreados: '',
};

const BADGE_TIPO_MUESTRA = {
  analisis: 'badge-info',
  contramuestra: 'badge-warn',
  testigo: 'badge-ok',
};

const LABEL_TIPO_MUESTRA = {
  analisis: 'Análisis',
  contramuestra: 'Contramuestra',
  testigo: 'Testigo',
};

let contadorAdHoc = 0;
function nuevaMuestraAdHoc() {
  contadorAdHoc += 1;
  return { key: `adhoc-${contadorAdHoc}`, tipo_muestra: '', cantidad_real: '', unidad: '' };
}

export default function CargaResultadosOrdenTrabajoPage() {
  const { idSolicitud } = useParams();
  const navigate = useNavigate();

  const [datos, setDatos] = useState(null);
  const [camposFisicos, setCamposFisicos] = useState(CAMPO_FISICO_VACIO);
  const [checklist, setChecklist] = useState([]); // [{ id_espec_ensayo, orden, nombre_ensayo, especificacion_texto, valor_cualitativo }]
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [guardando, setGuardando] = useState(false);
  const [resultado, setResultado] = useState(null); // OrdenTrabajoDigitalResponse tras confirmar
  const [codigoMuestraReadOnly, setCodigoMuestraReadOnly] = useState(null);
  const [idMuestraReadOnly, setIdMuestraReadOnly] = useState(null);
  const [descargando, setDescargando] = useState('');

  // "Muestras a tomar" -- confirmación al Ejecutar Muestreo, común a
  // solicitudes manuales y del agente (antes solo se pedía al crear una
  // solicitud manual). muestrasEspec son las definidas en la especificación
  // del producto; muestrasAdhoc son filas agregadas a mano solo para esta
  // solicitud puntual (no modifican la especificación).
  const [muestrasEspec, setMuestrasEspec] = useState([]);
  const [muestrasConfirmadas, setMuestrasConfirmadas] = useState({});
  const [muestrasAdhoc, setMuestrasAdhoc] = useState([]);

  // Recepción del proveedor (Libro de Ingresos) -- se carga en este mismo
  // momento, junto con el resto de Ejecutar Muestreo (ver
  // OrdenTrabajoDigitalBody en el backend).
  const [recepcion, setRecepcion] = useState({
    fecha_factura_proveedor: '', numero_factura_proveedor: '',
    id_usuario_recibio: '', id_usuario_rotulo: '',
  });
  const [usuariosActivos, setUsuariosActivos] = useState([]);

  // Impresión directa (SATO/SBPL) de las etiquetas generadas -- alternativa
  // al PDF, mismo patrón que MuestraEtiquetaPage.jsx.
  const [impresoras, setImpresoras] = useState([]);
  const [idImpresora, setIdImpresora] = useState('');
  const [mostrarImprimirDirecto, setMostrarImprimirDirecto] = useState(false);
  const [imprimiendo, setImprimiendo] = useState(false);
  const [mensajeDirecto, setMensajeDirecto] = useState(null); // { tipo: 'ok'|'error', texto }

  useEffect(() => {
    solicitudesMuestreoApi.listarUsuariosActivos().then(setUsuariosActivos).catch(() => {});
  }, []);

  useEffect(() => {
    solicitudesMuestreoApi
      .obtenerEnsayosParaOrden(idSolicitud)
      .then(async (data) => {
        setDatos(data);
        const df = data.datos_fisicos || {};
        // Precarga con el vencimiento que ya trae el ERP (resuelto al crear
        // la solicitud) como valor sugerido/editable -- pero NUNCA pisa un
        // valor que la persona ya haya confirmado a mano en una carga
        // anterior de esta misma pantalla (df.fecha_vencimiento_real). Si
        // el ERP no tenía nada (sentinel o NULL, ya viene limpio) y tampoco
        // hay nada confirmado todavía, el campo arranca vacío -- hay que
        // revisarlo y decidir, no queda con un valor puesto sin que nadie
        // lo haya mirado.
        setCamposFisicos({
          identificacion_contenedor: df.identificacion_contenedor || '',
          fecha_vencimiento_real: df.fecha_vencimiento_real || data.fecha_vencimiento_sugerida || '',
          sin_vencimiento_confirmado: !!df.sin_vencimiento_confirmado,
          fecha_reanalisis_real: df.fecha_reanalisis_real || '',
          aspecto_mp: df.aspecto_mp || '',
          materias_extranas: df.materias_extranas || '',
          olor: df.olor || '',
          color: df.color || '',
          observaciones_muestreo: df.observaciones_muestreo || '',
          nro_bultos_muestreados: df.nro_bultos_muestreados ?? '',
        });
        setChecklist(data.checklist_muestreo || []);

        if (data.id_especificacion) {
          try {
            const muestrasDeEspec = await maestrosApi.listarMuestrasEspecificacion(data.id_especificacion);
            setMuestrasEspec(muestrasDeEspec);
            const confirmadasIniciales = {};
            muestrasDeEspec.forEach((m) => {
              confirmadasIniciales[m.id] = { confirmada: m.genera_etiqueta, cantidad_real: String(m.cantidad) };
            });
            setMuestrasConfirmadas(confirmadasIniciales);
          } catch {
            setMuestrasEspec([]);
          }
        }

        if (data.estado !== 'pendiente') {
          try {
            const solicitud = await solicitudesMuestreoApi.obtener(idSolicitud);
            if (solicitud.id_muestra) {
              setIdMuestraReadOnly(solicitud.id_muestra);
              const muestra = await muestrasApi.obtenerMuestra(solicitud.id_muestra);
              setCodigoMuestraReadOnly(muestra.codigo_muestra);
            }
          } catch {
            // si falla, se muestra igual la vista de solo lectura sin el código
          }
        }
      })
      .catch((err) => setError(err instanceof ApiError ? err.message : 'No se pudo cargar la solicitud'))
      .finally(() => setLoading(false));
  }, [idSolicitud]);

  const soloLectura = (datos && datos.estado !== 'pendiente') || !!resultado;

  function actualizarCampoFisico(campo, valor) {
    setCamposFisicos((prev) => ({ ...prev, [campo]: valor }));
  }

  function actualizarRecepcion(campo, valor) {
    setRecepcion((prev) => ({ ...prev, [campo]: valor }));
  }

  function actualizarChecklist(idEspecEnsayo, valor) {
    setChecklist((prev) => prev.map((it) => (
      it.id_espec_ensayo === idEspecEnsayo ? { ...it, valor_cualitativo: valor } : it
    )));
  }

  function toggleMuestraConfirmada(idMuestra) {
    setMuestrasConfirmadas((prev) => ({
      ...prev,
      [idMuestra]: { ...prev[idMuestra], confirmada: !prev[idMuestra]?.confirmada },
    }));
  }

  function actualizarCantidadRealMuestra(idMuestra, valor) {
    setMuestrasConfirmadas((prev) => ({
      ...prev,
      [idMuestra]: { ...prev[idMuestra], cantidad_real: valor },
    }));
  }

  function agregarMuestraAdhoc() {
    setMuestrasAdhoc((prev) => [...prev, nuevaMuestraAdHoc()]);
  }

  function actualizarMuestraAdhoc(key, campo, valor) {
    setMuestrasAdhoc((prev) => prev.map((m) => (m.key === key ? { ...m, [campo]: valor } : m)));
  }

  function quitarMuestraAdhoc(key) {
    setMuestrasAdhoc((prev) => prev.filter((m) => m.key !== key));
  }

  async function handleSubmit(e) {
    e.preventDefault();
    setError('');

    for (const m of muestrasEspec) {
      const conf = muestrasConfirmadas[m.id];
      if (conf?.confirmada && !(Number(conf.cantidad_real) > 0)) {
        setError('La cantidad real de las muestras confirmadas tiene que ser mayor a 0');
        return;
      }
    }
    for (const m of muestrasAdhoc) {
      if (!m.tipo_muestra || !m.unidad.trim() || !(Number(m.cantidad_real) > 0)) {
        setError('Completá tipo, unidad y cantidad (mayor a 0) de todas las muestras ad-hoc agregadas (o quitá la fila)');
        return;
      }
    }
    if (!camposFisicos.fecha_vencimiento_real && !camposFisicos.sin_vencimiento_confirmado) {
      setError('Confirmá la fecha de vencimiento del material (revisá el envase físico) o marcá que no tiene vencimiento.');
      return;
    }

    setGuardando(true);
    try {
      const muestrasBody = [
        ...muestrasEspec.map((m) => ({
          id_espec_muestra: m.id,
          cantidad_real: Number(muestrasConfirmadas[m.id]?.cantidad_real || m.cantidad),
          confirmada: !!muestrasConfirmadas[m.id]?.confirmada,
        })),
        ...muestrasAdhoc.map((m) => ({
          id_espec_muestra: null,
          tipo_muestra: m.tipo_muestra,
          unidad: m.unidad.trim() || null,
          cantidad_real: Number(m.cantidad_real),
          confirmada: true,
        })),
      ];
      const resp = await solicitudesMuestreoApi.confirmarOrdenTrabajo(idSolicitud, {
        datos_fisicos: {
          identificacion_contenedor: camposFisicos.identificacion_contenedor.trim() || null,
          fecha_vencimiento_real: camposFisicos.fecha_vencimiento_real || null,
          sin_vencimiento_confirmado: camposFisicos.sin_vencimiento_confirmado,
          fecha_reanalisis_real: camposFisicos.fecha_reanalisis_real || null,
          aspecto_mp: camposFisicos.aspecto_mp.trim() || null,
          materias_extranas: camposFisicos.materias_extranas.trim() || null,
          olor: camposFisicos.olor.trim() || null,
          color: camposFisicos.color.trim() || null,
          observaciones_muestreo: camposFisicos.observaciones_muestreo.trim() || null,
          nro_bultos_muestreados: camposFisicos.nro_bultos_muestreados !== '' ? Number(camposFisicos.nro_bultos_muestreados) : null,
        },
        checklist_muestreo: checklist
          .filter((it) => it.valor_cualitativo)
          .map((it) => ({ id_espec_ensayo: it.id_espec_ensayo, valor_cualitativo: it.valor_cualitativo })),
        muestras: muestrasBody,
        fecha_factura_proveedor: recepcion.fecha_factura_proveedor || null,
        numero_factura_proveedor: recepcion.numero_factura_proveedor.trim() || null,
        id_usuario_recibio: recepcion.id_usuario_recibio ? Number(recepcion.id_usuario_recibio) : null,
        id_usuario_rotulo: recepcion.id_usuario_rotulo ? Number(recepcion.id_usuario_rotulo) : null,
      });
      setResultado(resp);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'No se pudo confirmar el muestreo');
    } finally {
      setGuardando(false);
    }
  }

  function abrirImprimirDirecto() {
    setMensajeDirecto(null);
    setMostrarImprimirDirecto(true);
    if (impresoras.length === 0) {
      muestrasApi
        .listarImpresoras(true)
        .then((data) => {
          setImpresoras(data);
          if (data.length === 1) setIdImpresora(String(data[0].id_impresora));
        })
        .catch(() => setMensajeDirecto({ tipo: 'error', texto: 'No se pudo cargar el listado de impresoras' }));
    }
  }

  async function confirmarImprimirDirecto(idMuestra) {
    if (!idImpresora) return;
    setImprimiendo(true);
    setMensajeDirecto(null);
    try {
      const resp = await muestrasApi.imprimirDirecto(idMuestra, Number(idImpresora));
      setMensajeDirecto({ tipo: 'ok', texto: resp.mensaje });
    } catch (err) {
      setMensajeDirecto({ tipo: 'error', texto: err instanceof ApiError ? err.message : 'No se pudo imprimir la etiqueta' });
    } finally {
      setImprimiendo(false);
    }
  }

  async function handleDescargar(tipo, path) {
    setDescargando(tipo);
    try {
      await abrirPdfConAuth(path);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'No se pudo descargar el PDF');
    } finally {
      setDescargando('');
    }
  }

  if (loading) {
    return (
      <div className="screen" style={{ alignItems: 'center', justifyContent: 'center' }}>
        <span className="spinner" />
      </div>
    );
  }

  if (error && !datos) {
    return (
      <div className="screen">
        <TopBar titulo="Orden de Trabajo" subtitulo="Ejecutar muestreo" onBack={() => navigate(-1)} />
        <div className="screen-content">
          <div className="alert alert-danger">{error}</div>
        </div>
      </div>
    );
  }

  const codigoMuestra = resultado?.codigo_muestra || codigoMuestraReadOnly;
  const idMuestraConfirmada = resultado?.id_muestra || idMuestraReadOnly;

  if (soloLectura && codigoMuestra) {
    return (
      <div className="screen">
        <TopBar titulo={datos.nro_solicitud} subtitulo="Muestreo confirmado" onBack={() => navigate(-1)} />
        <div className="screen-content">
          <div className="card" style={{ maxWidth: 480, margin: '0 auto', textAlign: 'center' }}>
            <div style={{ fontSize: 32, marginBottom: 'var(--sp-3)' }}>✓</div>
            <h2 style={{ fontSize: 'var(--fs-lg)', marginBottom: 'var(--sp-3)' }}>
              Muestra {codigoMuestra} creada correctamente
            </h2>
            <button
              className="btn btn-primary btn-block"
              style={{ marginBottom: 'var(--sp-2)' }}
              onClick={() => handleDescargar('etiquetas', `/api/solicitudes-muestreo/${idSolicitud}/etiquetas`)}
              disabled={!!descargando}
            >
              {descargando === 'etiquetas' ? <span className="spinner" /> : 'Descargar etiquetas (PDF)'}
            </button>
            {idMuestraConfirmada && !mostrarImprimirDirecto && (
              <button
                className="btn btn-secondary btn-block"
                style={{ marginBottom: 'var(--sp-2)' }}
                onClick={abrirImprimirDirecto}
              >
                Imprimir directo (impresora SATO) →
              </button>
            )}
            {idMuestraConfirmada && mostrarImprimirDirecto && (
              <div className="card" style={{ marginBottom: 'var(--sp-3)', textAlign: 'left' }}>
                <h2 style={{ fontSize: 'var(--fs-lg)', marginBottom: 'var(--sp-3)' }}>Imprimir directo</h2>
                {impresoras.length === 0 && !mensajeDirecto ? (
                  <div className="state-block"><span className="spinner" /></div>
                ) : impresoras.length === 0 ? null : (
                  <div className="field">
                    <label className="field-label" htmlFor="impresora">Impresora</label>
                    <select
                      id="impresora"
                      className="field-input"
                      value={idImpresora}
                      onChange={(e) => setIdImpresora(e.target.value)}
                      disabled={imprimiendo}
                    >
                      <option value="">Seleccioná una impresora...</option>
                      {impresoras.map((imp) => (
                        <option key={imp.id_impresora} value={imp.id_impresora}>{imp.nombre} ({imp.modelo})</option>
                      ))}
                    </select>
                  </div>
                )}

                {mensajeDirecto && (
                  <div className={`alert ${mensajeDirecto.tipo === 'ok' ? 'alert-ok' : 'alert-danger'}`} style={{ marginBottom: 'var(--sp-3)' }}>
                    {mensajeDirecto.texto}
                  </div>
                )}

                <div style={{ display: 'flex', gap: 'var(--sp-3)' }}>
                  <button type="button" className="btn btn-ghost" onClick={() => setMostrarImprimirDirecto(false)} disabled={imprimiendo}>
                    Cancelar
                  </button>
                  <button
                    type="button"
                    className="btn btn-primary"
                    onClick={() => confirmarImprimirDirecto(idMuestraConfirmada)}
                    disabled={imprimiendo || !idImpresora}
                  >
                    {imprimiendo ? <span className="spinner" /> : 'Imprimir'}
                  </button>
                </div>
              </div>
            )}
            <button
              className="btn btn-secondary btn-block"
              style={{ marginBottom: 'var(--sp-2)' }}
              onClick={() => handleDescargar('orden', `/api/solicitudes-muestreo/${idSolicitud}/orden-trabajo`)}
              disabled={!!descargando}
            >
              {descargando === 'orden' ? <span className="spinner" /> : 'Ver Orden de Trabajo PDF'}
            </button>
            <button
              className="btn btn-secondary btn-block"
              style={{ marginBottom: 'var(--sp-3)' }}
              onClick={() => handleDescargar('planilla', `/api/solicitudes-muestreo/${idSolicitud}/planilla-muestreo`)}
              disabled={!!descargando}
            >
              {descargando === 'planilla' ? <span className="spinner" /> : 'Ver Planilla de Muestreo PDF'}
            </button>
            <button className="btn btn-ghost btn-block" onClick={() => navigate(-1)}>
              Volver
            </button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="screen">
      <TopBar
        titulo={datos.nro_solicitud}
        subtitulo={`${datos.erp_DESART} (${datos.erp_CODART.trim()})`}
        onBack={() => navigate(-1)}
      />
      <div className="screen-content">
        {soloLectura && (
          <div className="alert alert-info" style={{ marginBottom: 'var(--sp-4)' }}>
            Esta solicitud ya fue ejecutada -- el formulario queda en solo lectura.
          </div>
        )}
        <form onSubmit={handleSubmit}>
          <div className="card" style={{ marginBottom: 'var(--sp-4)' }}>
            <h2 style={{ fontSize: 'var(--fs-lg)', marginBottom: 'var(--sp-3)' }}>Checklist de muestreo</h2>
            <ChecklistMuestreo checklist={checklist} onChange={actualizarChecklist} disabled={guardando || soloLectura} />
          </div>

          <div className="card" style={{ marginBottom: 'var(--sp-4)' }}>
            <h2 style={{ fontSize: 'var(--fs-lg)', marginBottom: 'var(--sp-3)' }}>Datos físicos del muestreo</h2>
            <div style={{ display: 'flex', gap: 'var(--sp-3)', flexWrap: 'wrap' }}>
              <div className="field" style={{ flex: '1 1 200px' }}>
                <label className="field-label">Identificación del contenedor</label>
                <input className="field-input" value={camposFisicos.identificacion_contenedor} onChange={(e) => actualizarCampoFisico('identificacion_contenedor', e.target.value)} disabled={guardando || soloLectura} />
              </div>
              <div className="field" style={{ flex: '1 1 260px' }}>
                <label className="field-label">Fecha de vencimiento real *</label>
                <input
                  className="field-input"
                  type="date"
                  value={camposFisicos.fecha_vencimiento_real}
                  onChange={(e) => {
                    const valor = e.target.value;
                    // Cargar una fecha real y tildar "no tiene vencimiento"
                    // son mutuamente excluyentes -- si se escribe una fecha,
                    // se destilda el checkbox automáticamente.
                    setCamposFisicos((prev) => ({ ...prev, fecha_vencimiento_real: valor, sin_vencimiento_confirmado: valor ? false : prev.sin_vencimiento_confirmado }));
                  }}
                  disabled={guardando || soloLectura || camposFisicos.sin_vencimiento_confirmado}
                />
                {datos?.fecha_vencimiento_sugerida && camposFisicos.fecha_vencimiento_real === datos.fecha_vencimiento_sugerida && (
                  <span style={{ fontSize: 'var(--fs-xs)', color: 'var(--ink-2)' }}>Sugerido por el ERP -- confirmá o corregí si no coincide con el envase.</span>
                )}
                <label style={{ display: 'flex', alignItems: 'center', gap: 'var(--sp-2)', marginTop: 'var(--sp-2)', fontSize: 'var(--fs-sm)', cursor: soloLectura ? 'default' : 'pointer' }}>
                  <input
                    type="checkbox"
                    checked={camposFisicos.sin_vencimiento_confirmado}
                    onChange={(e) => {
                      const marcado = e.target.checked;
                      setCamposFisicos((prev) => ({ ...prev, sin_vencimiento_confirmado: marcado, fecha_vencimiento_real: marcado ? '' : prev.fecha_vencimiento_real }));
                    }}
                    disabled={guardando || soloLectura}
                  />
                  Este material no tiene fecha de vencimiento
                </label>
              </div>
              <div className="field" style={{ flex: '1 1 200px' }}>
                <label className="field-label">Fecha de reanálisis real</label>
                <input className="field-input" type="date" value={camposFisicos.fecha_reanalisis_real} onChange={(e) => actualizarCampoFisico('fecha_reanalisis_real', e.target.value)} disabled={guardando || soloLectura} />
              </div>
              <div className="field" style={{ flex: '1 1 200px' }}>
                <label className="field-label">Aspecto de la MP</label>
                <input className="field-input" value={camposFisicos.aspecto_mp} onChange={(e) => actualizarCampoFisico('aspecto_mp', e.target.value)} disabled={guardando || soloLectura} />
              </div>
              <div className="field" style={{ flex: '1 1 200px' }}>
                <label className="field-label">Materias extrañas</label>
                <input className="field-input" value={camposFisicos.materias_extranas} onChange={(e) => actualizarCampoFisico('materias_extranas', e.target.value)} disabled={guardando || soloLectura} />
              </div>
              <div className="field" style={{ flex: '1 1 200px' }}>
                <label className="field-label">Olor</label>
                <input className="field-input" value={camposFisicos.olor} onChange={(e) => actualizarCampoFisico('olor', e.target.value)} disabled={guardando || soloLectura} />
              </div>
              <div className="field" style={{ flex: '1 1 200px' }}>
                <label className="field-label">Color</label>
                <input className="field-input" value={camposFisicos.color} onChange={(e) => actualizarCampoFisico('color', e.target.value)} disabled={guardando || soloLectura} />
              </div>
              <div className="field" style={{ flex: '1 1 200px' }}>
                <label className="field-label">N° bultos muestreados</label>
                <input className="field-input" type="number" step="1" value={camposFisicos.nro_bultos_muestreados} onChange={(e) => actualizarCampoFisico('nro_bultos_muestreados', e.target.value)} disabled={guardando || soloLectura} />
              </div>
            </div>
            <div className="field" style={{ marginTop: 'var(--sp-3)' }}>
              <label className="field-label">Observaciones</label>
              <textarea
                className="field-input"
                style={{ height: 70, paddingTop: 'var(--sp-2)' }}
                value={camposFisicos.observaciones_muestreo}
                onChange={(e) => actualizarCampoFisico('observaciones_muestreo', e.target.value)}
                disabled={guardando || soloLectura}
              />
            </div>
          </div>

          <div className="card" style={{ marginBottom: 'var(--sp-4)' }}>
            <h2 style={{ fontSize: 'var(--fs-lg)', marginBottom: 'var(--sp-3)' }}>Muestras a tomar</h2>
            {muestrasEspec.length === 0 && muestrasAdhoc.length === 0 ? (
              <div className="alert alert-warn">
                Esta especificación no tiene muestras definidas. Podés agregar una muestra ad-hoc abajo.
              </div>
            ) : (
              <div className="table-scroll">
                <table className="data-table data-table-compact">
                  <thead>
                    <tr>
                      <th></th>
                      <th>Tipo</th>
                      <th>Cantidad</th>
                      <th>Unidad</th>
                      <th>Laboratorio</th>
                      <th>Cant. real</th>
                      <th></th>
                    </tr>
                  </thead>
                  <tbody>
                    {muestrasEspec.map((m) => {
                      const conf = muestrasConfirmadas[m.id] || { confirmada: false, cantidad_real: String(m.cantidad) };
                      return (
                        <tr key={m.id}>
                          <td>
                            <input
                              type="checkbox"
                              checked={conf.confirmada}
                              onChange={() => toggleMuestraConfirmada(m.id)}
                              disabled={guardando || soloLectura}
                            />
                          </td>
                          <td>
                            <span className={`badge ${BADGE_TIPO_MUESTRA[m.tipo_muestra] || 'badge-neutral'}`}>
                              {LABEL_TIPO_MUESTRA[m.tipo_muestra] || m.tipo_muestra}
                            </span>
                          </td>
                          <td className="num">{m.cantidad}</td>
                          <td>{m.unidad}</td>
                          <td>{m.laboratorio_nombre || 'Sin asignar'}</td>
                          <td>
                            <input
                              className="field-input"
                              type="number"
                              step="any"
                              style={{ maxWidth: 110 }}
                              value={conf.cantidad_real}
                              onChange={(e) => actualizarCantidadRealMuestra(m.id, e.target.value)}
                              disabled={!conf.confirmada || guardando || soloLectura}
                            />
                          </td>
                          <td></td>
                        </tr>
                      );
                    })}
                    {muestrasAdhoc.map((m) => (
                      <tr key={m.key}>
                        <td></td>
                        <td>
                          <select
                            className="field-input"
                            style={{ maxWidth: 150 }}
                            value={m.tipo_muestra}
                            onChange={(e) => actualizarMuestraAdhoc(m.key, 'tipo_muestra', e.target.value)}
                            disabled={guardando || soloLectura}
                          >
                            <option value="">Elegí un tipo...</option>
                            <option value="analisis">Análisis</option>
                            <option value="contramuestra">Contramuestra</option>
                            <option value="testigo">Testigo</option>
                          </select>
                        </td>
                        <td colSpan={2}>
                          <span className="badge badge-neutral">Ad-hoc (no está en la especificación)</span>
                        </td>
                        <td></td>
                        <td>
                          <div style={{ display: 'flex', gap: 'var(--sp-2)' }}>
                            <input
                              className="field-input"
                              type="number"
                              step="any"
                              style={{ maxWidth: 90 }}
                              placeholder="Cant."
                              value={m.cantidad_real}
                              onChange={(e) => actualizarMuestraAdhoc(m.key, 'cantidad_real', e.target.value)}
                              disabled={guardando || soloLectura}
                            />
                            <input
                              className="field-input"
                              style={{ maxWidth: 90 }}
                              placeholder="Unidad"
                              value={m.unidad}
                              onChange={(e) => actualizarMuestraAdhoc(m.key, 'unidad', e.target.value)}
                              disabled={guardando || soloLectura}
                            />
                          </div>
                        </td>
                        <td>
                          <button
                            type="button"
                            className="btn btn-ghost btn-sm"
                            onClick={() => quitarMuestraAdhoc(m.key)}
                            disabled={guardando || soloLectura}
                          >
                            Quitar
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
            {!soloLectura && (
              <button type="button" className="btn btn-secondary" style={{ marginTop: 'var(--sp-3)' }} onClick={agregarMuestraAdhoc} disabled={guardando}>
                + Agregar muestra ad-hoc
              </button>
            )}
          </div>

          <div className="card" style={{ marginBottom: 'var(--sp-4)' }}>
            <h2 style={{ fontSize: 'var(--fs-lg)', marginBottom: 'var(--sp-3)' }}>Recepción del proveedor</h2>
            <div style={{ display: 'flex', gap: 'var(--sp-3)', flexWrap: 'wrap' }}>
              <div className="field" style={{ flex: '1 1 200px' }}>
                <label className="field-label">Fecha de factura</label>
                <input
                  className="field-input"
                  type="date"
                  value={recepcion.fecha_factura_proveedor}
                  onChange={(e) => actualizarRecepcion('fecha_factura_proveedor', e.target.value)}
                  disabled={guardando || soloLectura}
                />
              </div>
              <div className="field" style={{ flex: '1 1 200px' }}>
                <label className="field-label">N° de factura</label>
                <input
                  className="field-input"
                  value={recepcion.numero_factura_proveedor}
                  onChange={(e) => actualizarRecepcion('numero_factura_proveedor', e.target.value)}
                  disabled={guardando || soloLectura}
                />
              </div>
              <div className="field" style={{ flex: '1 1 200px' }}>
                <label className="field-label">Recibió</label>
                <select
                  className="field-input"
                  value={recepcion.id_usuario_recibio}
                  onChange={(e) => actualizarRecepcion('id_usuario_recibio', e.target.value)}
                  disabled={guardando || soloLectura}
                >
                  <option value="">Seleccioná un usuario...</option>
                  {usuariosActivos.map((u) => (
                    <option key={u.id_usuario} value={u.id_usuario}>{u.nombre_completo}</option>
                  ))}
                </select>
              </div>
              <div className="field" style={{ flex: '1 1 200px' }}>
                <label className="field-label">Rotuló</label>
                <select
                  className="field-input"
                  value={recepcion.id_usuario_rotulo}
                  onChange={(e) => actualizarRecepcion('id_usuario_rotulo', e.target.value)}
                  disabled={guardando || soloLectura}
                >
                  <option value="">Seleccioná un usuario...</option>
                  {usuariosActivos.map((u) => (
                    <option key={u.id_usuario} value={u.id_usuario}>{u.nombre_completo}</option>
                  ))}
                </select>
              </div>
            </div>
          </div>

          {error && <div className="alert alert-danger" style={{ marginBottom: 'var(--sp-4)' }}>{error}</div>}

          {!soloLectura && (
            <button type="submit" className="btn btn-primary btn-block btn-lg" disabled={guardando}>
              {guardando ? <span className="spinner" /> : 'Confirmar muestreo'}
            </button>
          )}
        </form>
      </div>
    </div>
  );
}
