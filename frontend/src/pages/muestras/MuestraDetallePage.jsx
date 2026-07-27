import { useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { useAuth } from '../../context/AuthContext';
import TopBar from '../../components/TopBar';
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

  const [muestra, setMuestra] = useState(null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);

  const [editando, setEditando] = useState(false);
  const [tipoMaterialEdit, setTipoMaterialEdit] = useState('');
  const [observacionesEdit, setObservacionesEdit] = useState('');
  const [guardando, setGuardando] = useState(false);
  const [errorEdit, setErrorEdit] = useState('');
  const [successMsg, setSuccessMsg] = useState('');

  useEffect(() => {
    setLoading(true);
    muestrasApi
      .obtenerMuestra(id)
      .then(setMuestra)
      .catch((err) => setError(err instanceof ApiError ? err.message : 'No se pudo cargar la muestra'))
      .finally(() => setLoading(false));
  }, [id]);

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
        <TopBar titulo="Muestra" subtitulo="Muestras" onBack={() => navigate('/muestras')} />
        <div className="screen-content">
          <div className="alert alert-danger">{error || 'No encontrada'}</div>
        </div>
      </div>
    );
  }

  return (
    <div className="screen">
      <TopBar titulo={muestra.codigo_muestra} subtitulo="Muestras" onBack={() => navigate('/muestras')} />
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
            <span className={`badge ${BADGE_POR_ESTADO[muestra.estado] || 'badge-neutral'}`}>{muestra.estado.replace(/_/g, ' ')}</span>
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
                <tr><td>Especificación</td><td style={{ textAlign: 'left' }}>{muestra.id_especificacion ? `#${muestra.id_especificacion}` : 'Sin especificación vigente asignada'}</td></tr>
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
                    Imprimir etiqueta
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
      </div>
    </div>
  );
}
