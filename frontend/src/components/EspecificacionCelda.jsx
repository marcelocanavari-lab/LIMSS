import { useState } from 'react';
import { muestrasApi } from '../api/muestras';
import { ApiError } from '../api/client';

const LABEL_TIPO_MATERIAL = {
  materia_prima: 'Materia Prima',
  granel: 'Granel',
  semi_elaborado: 'Semi-Elaborado',
  producto_terminado: 'Producto Terminado',
};

// Celda "Especificación" de la ficha de una muestra -- si ya está vinculada
// muestra el id sin más; si no (caso real: la muestra se creó antes de que
// la especificación de su artículo existiera en Datos Maestros, quedó con
// id_especificacion NULL y no había forma de reconectarla después, ver
// especificacionCandidata/vincularEspecificacion en la API) muestra el
// aviso + el botón para buscar la especificación vigente del artículo y
// vincularla. Compartido entre MuestraDetallePage.jsx ("Mis Muestras") y
// ConsultaMuestraDetallePage.jsx ("Consulta de Muestras", roles QA/admin,
// que son justamente los que necesitan generar el envío y se topan con
// este problema) -- mismo componente, misma lógica, sin duplicar.
export default function EspecificacionCelda({ idMuestra, idEspecificacion, erpCodart, puedeEditar, onVinculada }) {
  const [modalAbierto, setModalAbierto] = useState(false);
  const [buscandoCandidata, setBuscandoCandidata] = useState(false);
  // undefined = todavía no se buscó; null = ya se buscó, no hay ninguna
  // vigente; objeto = se encontró una candidata para confirmar.
  const [especCandidata, setEspecCandidata] = useState(undefined);
  const [vinculando, setVinculando] = useState(false);
  const [error, setError] = useState('');

  function abrirVincular() {
    setError('');
    setModalAbierto(true);
    setBuscandoCandidata(true);
    muestrasApi
      .especificacionCandidata(idMuestra)
      .then(setEspecCandidata)
      .catch((err) => setError(err instanceof ApiError ? err.message : 'No se pudo buscar la especificación'))
      .finally(() => setBuscandoCandidata(false));
  }

  function cerrarVincular() {
    setModalAbierto(false);
    setEspecCandidata(undefined);
    setError('');
  }

  async function confirmarVincular() {
    if (!especCandidata) return;
    setVinculando(true);
    setError('');
    try {
      const actualizada = await muestrasApi.vincularEspecificacion(idMuestra, especCandidata.id_especificacion);
      setModalAbierto(false);
      setEspecCandidata(undefined);
      onVinculada?.(actualizada);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'No se pudo vincular la especificación');
    } finally {
      setVinculando(false);
    }
  }

  if (idEspecificacion) {
    return <>{`#${idEspecificacion}`}</>;
  }

  return (
    <>
      <span style={{ display: 'flex', alignItems: 'center', gap: 'var(--sp-2)', flexWrap: 'wrap' }}>
        <span className="badge badge-warn">Sin especificación vinculada</span>
        {puedeEditar && (
          <button type="button" className="btn btn-ghost" onClick={abrirVincular}>
            Vincular especificación →
          </button>
        )}
      </span>

      {modalAbierto && (
        <div
          className="no-print"
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
                  Se encontró una especificación vigente para <b>{erpCodart}</b>:
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
                Todavía no hay ninguna especificación vigente cargada para {erpCodart}. Cargala primero en
                Datos Maestros y volvé a intentar desde acá.
              </p>
            )}

            {error && <div className="alert alert-danger" style={{ marginBottom: 'var(--sp-3)' }}>{error}</div>}

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
    </>
  );
}
