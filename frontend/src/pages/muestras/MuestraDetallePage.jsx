import { useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { useAuth } from '../../context/AuthContext';
import TopBar from '../../components/TopBar';
import ChecklistMuestreo from '../../components/ChecklistMuestreo';
import { muestrasApi } from '../../api/muestras';
import { ApiError } from '../../api/client';
import { BADGE_POR_ESTADO } from './MuestrasPage';

const TIPOS_MATERIAL = [
  { value: 'materia_prima', label: 'Materia Prima' },
  { value: 'granel', label: 'Granel' },
  { value: 'semi_elaborado', label: 'Semi-Elaborado' },
  { value: 'producto_terminado', label: 'Producto Terminado' },
];

const LABEL_TIPO_MATERIAL = Object.fromEntries(TIPOS_MATERIAL.map((t) => [t.value, t.label]));

export default function MuestraDetallePage() {
  const { id } = useParams();
  const navigate = useNavigate();
  const { user } = useAuth();
  const puedeEditar = ['analista_qc', 'qa', 'admin'].includes(user?.rol);
  const puedeCompletarMuestreo = ['muestreador', 'analista_qc', 'qa', 'admin'].includes(user?.rol);

  const [muestra, setMuestra] = useState(null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);

  // Checklist de etapa 'muestreo' -- mismo mecanismo que Ejecutar Muestreo,
  // expuesto acá para las muestras creadas con Nueva Muestra (sin
  // solicitud detrás). Si la especificación no tiene ítems de esta etapa,
  // checklist queda en [] y la sección ni se muestra.
  const [checklist, setChecklist] = useState([]);
  const [checklistLoading, setChecklistLoading] = useState(true);
  const [checklistGuardando, setChecklistGuardando] = useState(false);
  const [checklistError, setChecklistError] = useState('');
  const [checklistOk, setChecklistOk] = useState('');
  // Si ya existe una etiqueta impresa para esta muestra, la próxima
  // impresión queda registrada como reimpresión (lims_etiquetas.reimpresion,
  // ver generar_etiqueta) -- se refleja acá para que el botón lo diga
  // explícitamente en vez de imprimir/reimprimir en silencio.
  const [tieneEtiqueta, setTieneEtiqueta] = useState(false);

  const [editando, setEditando] = useState(false);
  const [tipoMaterialEdit, setTipoMaterialEdit] = useState('');
  const [observacionesEdit, setObservacionesEdit] = useState('');
  const [guardando, setGuardando] = useState(false);
  const [errorEdit, setErrorEdit] = useState('');
  const [successMsg, setSuccessMsg] = useState('');

  // "Vincular especificación" -- caso real: la muestra se creó antes de que
  // la especificación de su artículo existiera en Datos Maestros, quedó con
  // id_especificacion NULL y no había forma de reconectarla después (ver
  // especificacionCandidata/vincularEspecificacion en la API). El modal se
  // abre a demanda (no se busca la candidata hasta que la persona lo pide)
  // porque para la gran mayoría de las muestras esto nunca hace falta.
  const [modalVincularAbierto, setModalVincularAbierto] = useState(false);
  const [buscandoCandidata, setBuscandoCandidata] = useState(false);
  // undefined = todavía no se buscó; null = ya se buscó, no hay ninguna
  // vigente; objeto = se encontró una candidata para confirmar.
  const [especCandidata, setEspecCandidata] = useState(undefined);
  const [vinculando, setVinculando] = useState(false);
  const [errorVincular, setErrorVincular] = useState('');

  useEffect(() => {
    setLoading(true);
    muestrasApi
      .obtenerMuestra(id)
      .then(setMuestra)
      .catch((err) => setError(err instanceof ApiError ? err.message : 'No se pudo cargar la muestra'))
      .finally(() => setLoading(false));
  }, [id]);

  useEffect(() => {
    muestrasApi
      .obtenerUltimaEtiqueta(id)
      .then(() => setTieneEtiqueta(true))
      .catch(() => setTieneEtiqueta(false));
  }, [id]);

  useEffect(() => {
    setChecklistLoading(true);
    muestrasApi
      .obtenerChecklistMuestreo(id)
      .then(setChecklist)
      .catch(() => setChecklist([]))
      .finally(() => setChecklistLoading(false));
  }, [id]);

  function actualizarChecklist(idEspecEnsayo, valor) {
    setChecklist((prev) => prev.map((it) => (
      it.id_espec_ensayo === idEspecEnsayo ? { ...it, valor_cualitativo: valor } : it
    )));
  }

  async function guardarChecklist() {
    setChecklistError('');
    setChecklistOk('');
    setChecklistGuardando(true);
    try {
      const actualizado = await muestrasApi.guardarChecklistMuestreo(
        id,
        checklist
          .filter((it) => it.valor_cualitativo)
          .map((it) => ({ id_espec_ensayo: it.id_espec_ensayo, valor_cualitativo: it.valor_cualitativo })),
      );
      setChecklist(actualizado);
      setChecklistOk('Checklist guardado correctamente');
    } catch (err) {
      setChecklistError(err instanceof ApiError ? err.message : 'No se pudo guardar el checklist');
    } finally {
      setChecklistGuardando(false);
    }
  }

  function abrirEdicion() {
    setTipoMaterialEdit(muestra.tipo_material || '');
    setObservacionesEdit(muestra.observaciones || '');
    setErrorEdit('');
    setSuccessMsg('');
    setEditando(true);
  }

  function cancelarEdicion() {
    setEditando(false);
    setErrorEdit('');
  }

  async function guardarEdicion(e) {
    e.preventDefault();
    setErrorEdit('');
    setGuardando(true);
    try {
      const actualizada = await muestrasApi.editarMuestra(id, {
        tipo_material: tipoMaterialEdit || null,
        observaciones: observacionesEdit.trim() || null,
      });
      setMuestra(actualizada);
      setEditando(false);
      setSuccessMsg('Muestra actualizada correctamente');
    } catch (err) {
      setErrorEdit(err instanceof ApiError ? err.message : 'No se pudo guardar los cambios');
    } finally {
      setGuardando(false);
    }
  }

  function abrirVincular() {
    setErrorVincular('');
    setModalVincularAbierto(true);
    setBuscandoCandidata(true);
    muestrasApi
      .especificacionCandidata(id)
      .then(setEspecCandidata)
      .catch((err) => setErrorVincular(err instanceof ApiError ? err.message : 'No se pudo buscar la especificación'))
      .finally(() => setBuscandoCandidata(false));
  }

  function cerrarVincular() {
    setModalVincularAbierto(false);
    setEspecCandidata(undefined);
    setErrorVincular('');
  }

  async function confirmarVincular() {
    if (!especCandidata) return;
    setVinculando(true);
    setErrorVincular('');
    try {
      const actualizada = await muestrasApi.vincularEspecificacion(id, especCandidata.id_especificacion);
      setMuestra(actualizada);
      setModalVincularAbierto(false);
      setEspecCandidata(undefined);
      setSuccessMsg(`Especificación #${especCandidata.id_especificacion} vinculada correctamente`);
    } catch (err) {
      setErrorVincular(err instanceof ApiError ? err.message : 'No se pudo vincular la especificación');
    } finally {
      setVinculando(false);
    }
  }

  if (loading) {
    return (
      <div className="screen" style={{ alignItems: 'center', justifyContent: 'center' }}>
        <span className="spinner" />
      </div>
    );
  }

  if (error || !muestra) {
    return (
      <div className="screen">
        <TopBar titulo="Muestra" subtitulo="Muestras" onBack={() => navigate(-1)} />
        <div className="screen-content">
          <div className="alert alert-danger">{error || 'No encontrada'}</div>
        </div>
      </div>
    );
  }

  return (
    <div className="screen">
      <TopBar titulo={muestra.codigo_muestra} subtitulo="Muestras" onBack={() => navigate(-1)} />
      <div className="screen-content">
        {successMsg && <div className="alert alert-ok" style={{ marginBottom: 'var(--sp-4)' }}>{successMsg}</div>}

        <div className="card" style={{ marginBottom: 'var(--sp-5)' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 'var(--sp-3)' }}>
            <div>
              <div style={{ fontFamily: 'var(--font-mono)', color: 'var(--ink-2)', fontSize: 'var(--fs-sm)' }}>
                {muestra.tipo_referencia === 'ir' ? 'IR' : 'Lote'} {muestra.nro_referencia}
              </div>
              <h1 style={{ fontSize: 'var(--fs-xl)' }}>{muestra.erp_DESART}</h1>
            </div>
            <div style={{ display: 'flex', gap: 4 }}>
              <span className={`badge ${BADGE_POR_ESTADO[muestra.estado] || 'badge-neutral'}`}>{muestra.estado.replace(/_/g, ' ')}</span>
              {muestra.datos_muestreo_pendientes && (
                <span className="badge badge-warn" title="El envío se generó por adelantado -- todavía falta completar el registro físico del muestreo">
                  Datos pendientes
                </span>
              )}
            </div>
          </div>

          <form onSubmit={guardarEdicion}>
            <table className="data-table">
              <tbody>
                <tr><td>Código</td><td style={{ textAlign: 'left', fontFamily: 'var(--font-mono)' }}>{muestra.erp_CODART}</td></tr>
                <tr>
                  <td>Tipo de material</td>
                  <td style={{ textAlign: 'left' }}>
                    {editando ? (
                      <select
                        className="field-input"
                        value={tipoMaterialEdit}
                        onChange={(e) => setTipoMaterialEdit(e.target.value)}
                        disabled={guardando}
                      >
                        <option value="">Sin especificar</option>
                        {TIPOS_MATERIAL.map((t) => (
                          <option key={t.value} value={t.value}>{t.label}</option>
                        ))}
                      </select>
                    ) : (
                      LABEL_TIPO_MATERIAL[muestra.tipo_material] || muestra.tipo_material || '—'
                    )}
                  </td>
                </tr>
                <tr><td>Cantidad de lote</td><td className="num" style={{ textAlign: 'left' }}>{muestra.erp_cantidad_lote ?? '—'}</td></tr>
                <tr><td>Proveedor</td><td style={{ textAlign: 'left' }}>{muestra.erp_proveedor || '—'}</td></tr>
                <tr><td>Cantidad enviada</td><td className="num" style={{ textAlign: 'left' }}>{muestra.cantidad_enviada != null ? `${muestra.cantidad_enviada} ${muestra.unidad_enviada || ''}` : '—'}</td></tr>
                <tr>
                  <td>Especificación</td>
                  <td style={{ textAlign: 'left' }}>
                    {muestra.id_especificacion ? (
                      `#${muestra.id_especificacion}`
                    ) : (
                      <span style={{ display: 'flex', alignItems: 'center', gap: 'var(--sp-2)', flexWrap: 'wrap' }}>
                        <span className="badge badge-warn">Sin especificación vinculada</span>
                        {puedeEditar && (
                          <button type="button" className="btn btn-ghost" onClick={abrirVincular}>
                            Vincular especificación →
                          </button>
                        )}
                      </span>
                    )}
                  </td>
                </tr>
                <tr><td>Fecha de muestreo</td><td style={{ textAlign: 'left' }}>{new Date(muestra.fecha_muestreo).toLocaleString()}</td></tr>
                <tr><td>Muestreador</td><td style={{ textAlign: 'left' }}>{muestra.usuario_muestreo_nombre}</td></tr>
                <tr>
                  <td>Observaciones</td>
                  <td style={{ textAlign: 'left' }}>
                    {editando ? (
                      <textarea
                        className="field-input"
                        style={{ height: 80, paddingTop: 'var(--sp-2)' }}
                        value={observacionesEdit}
                        onChange={(e) => setObservacionesEdit(e.target.value)}
                        disabled={guardando}
                      />
                    ) : (
                      muestra.observaciones || '—'
                    )}
                  </td>
                </tr>
              </tbody>
            </table>

            {errorEdit && <div className="alert alert-danger" style={{ marginTop: 'var(--sp-3)' }}>{errorEdit}</div>}

            <div style={{ display: 'flex', gap: 'var(--sp-3)', marginTop: 'var(--sp-4)', flexWrap: 'wrap' }}>
              {editando ? (
                <>
                  <button type="button" className="btn btn-ghost" onClick={cancelarEdicion} disabled={guardando}>
                    Cancelar
                  </button>
                  <button type="submit" className="btn btn-primary" disabled={guardando}>
                    {guardando ? <span className="spinner" /> : 'Guardar'}
                  </button>
                </>
              ) : (
                <>
                  <button type="button" className="btn btn-primary" onClick={() => navigate(`/muestras/${id}/etiqueta`)}>
                    {tieneEtiqueta ? 'Reimprimir etiqueta' : 'Imprimir etiqueta'}
                  </button>
                  {puedeEditar && (
                    <button type="button" className="btn btn-secondary" onClick={abrirEdicion}>
                      Editar
                    </button>
                  )}
                </>
              )}
            </div>
          </form>
        </div>

        {!checklistLoading && checklist.length > 0 && (
          <div className="card" style={{ marginBottom: 'var(--sp-5)' }}>
            <h2 style={{ fontSize: 'var(--fs-lg)', marginBottom: 'var(--sp-3)' }}>Checklist de muestreo</h2>
            <ChecklistMuestreo
              checklist={checklist}
              onChange={actualizarChecklist}
              disabled={checklistGuardando || !puedeCompletarMuestreo}
            />
            {checklistError && <div className="alert alert-danger" style={{ marginBottom: 'var(--sp-3)' }}>{checklistError}</div>}
            {checklistOk && <div className="alert alert-ok" style={{ marginBottom: 'var(--sp-3)' }}>{checklistOk}</div>}
            {puedeCompletarMuestreo && (
              <button className="btn btn-primary" onClick={guardarChecklist} disabled={checklistGuardando}>
                {checklistGuardando ? <span className="spinner" /> : 'Guardar checklist'}
              </button>
            )}
          </div>
        )}

        {modalVincularAbierto && (
          <div
            style={{
              position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.5)',
              display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 100, padding: 'var(--sp-4)',
            }}
            onClick={() => !vinculando && cerrarVincular()}
          >
            <div className="card" style={{ width: '90%', maxWidth: 480 }} onClick={(e) => e.stopPropagation()}>
              <h2 style={{ fontSize: 'var(--fs-lg)', marginBottom: 'var(--sp-3)' }}>Vincular especificación</h2>

              {buscandoCandidata ? (
                <div className="state-block"><span className="spinner" /></div>
              ) : especCandidata ? (
                <>
                  <p style={{ marginBottom: 'var(--sp-3)' }}>
                    Se encontró una especificación vigente para <b>{muestra.erp_CODART}</b>:
                  </p>
                  <table className="data-table data-table-compact" style={{ marginBottom: 'var(--sp-3)' }}>
                    <tbody>
                      <tr><td>Código</td><td style={{ textAlign: 'left' }}>{especCandidata.erp_CODART}</td></tr>
                      <tr><td>Descripción</td><td style={{ textAlign: 'left' }}>{especCandidata.erp_DESART}</td></tr>
                      <tr><td>Tipo de material</td><td style={{ textAlign: 'left' }}>{LABEL_TIPO_MATERIAL[especCandidata.tipo_material] || especCandidata.tipo_material}</td></tr>
                      <tr><td>Versión</td><td style={{ textAlign: 'left' }}>{especCandidata.version}</td></tr>
                    </tbody>
                  </table>
                  <p style={{ color: 'var(--ink-2)', fontSize: 'var(--fs-sm)', marginBottom: 'var(--sp-3)' }}>
                    Confirmá que corresponde antes de vincularla -- esta acción no se puede deshacer desde acá.
                  </p>
                </>
              ) : (
                <p style={{ color: 'var(--ink-2)', marginBottom: 'var(--sp-3)' }}>
                  Todavía no hay ninguna especificación vigente cargada para {muestra.erp_CODART}. Cargala primero en
                  Datos Maestros y volvé a intentar desde acá.
                </p>
              )}

              {errorVincular && <div className="alert alert-danger" style={{ marginBottom: 'var(--sp-3)' }}>{errorVincular}</div>}

              <div style={{ display: 'flex', gap: 'var(--sp-3)' }}>
                <button type="button" className="btn btn-ghost" onClick={cerrarVincular} disabled={vinculando}>
                  Cerrar
                </button>
                {especCandidata && (
                  <button type="button" className="btn btn-primary" onClick={confirmarVincular} disabled={vinculando}>
                    {vinculando ? <span className="spinner" /> : 'Confirmar y vincular'}
                  </button>
                )}
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
