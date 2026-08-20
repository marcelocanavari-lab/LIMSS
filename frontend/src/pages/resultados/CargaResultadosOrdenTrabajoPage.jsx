import { useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import TopBar from '../../components/TopBar';
import { solicitudesMuestreoApi } from '../../api/solicitudesMuestreo';
import { muestrasApi } from '../../api/muestras';
import { ApiError, abrirPdfConAuth } from '../../api/client';

const CAMPO_FISICO_VACIO = {
  identificacion_contenedor: '', fecha_vencimiento_real: '', fecha_reanalisis_real: '',
  aspecto_mp: '', materias_extranas: '', olor: '', color: '',
  observaciones_muestreo: '', nro_bultos_muestreados: '',
};

// Inspección visual del contenedor al tomar la muestra -- Cumple/No cumple
// en vez de texto libre. El valor que viaja al backend sigue siendo el
// string "Cumple" / "No cumple" en el mismo campo VARCHAR de siempre (sin
// cambio de modelo de datos), así que un muestreo viejo con texto libre
// cargado (ej. "Correcto") se sigue mostrando tal cual, solo que ningún
// botón queda marcado como seleccionado para ese valor.
function CampoCumple({ label, valor, onChange, disabled }) {
  return (
    <div className="field" style={{ flex: '1 1 200px' }}>
      <label className="field-label">{label}</label>
      <div style={{ display: 'flex', gap: 'var(--sp-2)' }}>
        <button
          type="button"
          className="btn btn-secondary"
          style={valor === 'Cumple' ? { background: 'var(--ok)', borderColor: 'var(--ok)', color: '#fff' } : undefined}
          onClick={() => onChange('Cumple')}
          disabled={disabled}
        >
          Cumple
        </button>
        <button
          type="button"
          className="btn btn-secondary"
          style={valor === 'No cumple' ? { background: 'var(--danger)', borderColor: 'var(--danger)', color: '#fff' } : undefined}
          onClick={() => onChange('No cumple')}
          disabled={disabled}
        >
          No cumple
        </button>
      </div>
    </div>
  );
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
  const [descargando, setDescargando] = useState('');

  useEffect(() => {
    solicitudesMuestreoApi
      .obtenerEnsayosParaOrden(idSolicitud)
      .then(async (data) => {
        setDatos(data);
        const df = data.datos_fisicos || {};
        setCamposFisicos({
          identificacion_contenedor: df.identificacion_contenedor || '',
          fecha_vencimiento_real: df.fecha_vencimiento_real || '',
          fecha_reanalisis_real: df.fecha_reanalisis_real || '',
          aspecto_mp: df.aspecto_mp || '',
          materias_extranas: df.materias_extranas || '',
          olor: df.olor || '',
          color: df.color || '',
          observaciones_muestreo: df.observaciones_muestreo || '',
          nro_bultos_muestreados: df.nro_bultos_muestreados ?? '',
        });
        setChecklist(data.checklist_muestreo || []);

        if (data.estado !== 'pendiente') {
          try {
            const solicitud = await solicitudesMuestreoApi.obtener(idSolicitud);
            if (solicitud.id_muestra) {
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

  function actualizarChecklist(idEspecEnsayo, valor) {
    setChecklist((prev) => prev.map((it) => (
      it.id_espec_ensayo === idEspecEnsayo ? { ...it, valor_cualitativo: valor } : it
    )));
  }

  async function handleSubmit(e) {
    e.preventDefault();
    setError('');

    setGuardando(true);
    try {
      const resp = await solicitudesMuestreoApi.confirmarOrdenTrabajo(idSolicitud, {
        datos_fisicos: {
          identificacion_contenedor: camposFisicos.identificacion_contenedor.trim() || null,
          fecha_vencimiento_real: camposFisicos.fecha_vencimiento_real || null,
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
      });
      setResultado(resp);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'No se pudo confirmar el muestreo');
    } finally {
      setGuardando(false);
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
              {descargando === 'etiquetas' ? <span className="spinner" /> : 'Descargar etiquetas'}
            </button>
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
            {checklist.length === 0 ? (
              <div className="alert alert-warn" style={{ marginBottom: 'var(--sp-3)' }}>
                Esta especificación no tiene ítems de etapa muestreo configurados -- no hay nada que revisar acá.
              </div>
            ) : (
              <div style={{ display: 'flex', gap: 'var(--sp-3)', flexWrap: 'wrap', marginBottom: 'var(--sp-3)' }}>
                {checklist.map((item) => (
                  <div key={item.id_espec_ensayo} style={{ flex: '1 1 260px' }}>
                    <CampoCumple
                      label={item.nombre_ensayo}
                      valor={item.valor_cualitativo}
                      onChange={(v) => actualizarChecklist(item.id_espec_ensayo, v)}
                      disabled={guardando || soloLectura}
                    />
                    {item.especificacion_texto && (
                      <p style={{ fontSize: 'var(--fs-xs)', color: 'var(--ink-2)', marginTop: 'var(--sp-1)' }}>
                        {item.especificacion_texto}
                      </p>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>

          <div className="card" style={{ marginBottom: 'var(--sp-4)' }}>
            <h2 style={{ fontSize: 'var(--fs-lg)', marginBottom: 'var(--sp-3)' }}>Datos físicos del muestreo</h2>
            <div style={{ display: 'flex', gap: 'var(--sp-3)', flexWrap: 'wrap' }}>
              <div className="field" style={{ flex: '1 1 200px' }}>
                <label className="field-label">Identificación del contenedor</label>
                <input className="field-input" value={camposFisicos.identificacion_contenedor} onChange={(e) => actualizarCampoFisico('identificacion_contenedor', e.target.value)} disabled={guardando || soloLectura} />
              </div>
              <div className="field" style={{ flex: '1 1 200px' }}>
                <label className="field-label">Fecha de vencimiento real</label>
                <input className="field-input" type="date" value={camposFisicos.fecha_vencimiento_real} onChange={(e) => actualizarCampoFisico('fecha_vencimiento_real', e.target.value)} disabled={guardando || soloLectura} />
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
