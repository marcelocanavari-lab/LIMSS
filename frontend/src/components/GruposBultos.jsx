// Grupos de bultos (cantidad de bultos x cantidad de unidades cada uno --
// ver lims_solicitud_bultos en el backend) -- reemplaza/complementa al
// simple "N° de bultos": cuando los bultos no son todos iguales (ej. "4 x
// 50 kg" + "1 x 30 kg"), cada grupo termina imprimiendo esa cantidad de
// etiquetas CUARENTENA/APROBADO/RECHAZADO con SU cantidad particular, en
// vez de todas iguales. Compartido entre el formulario de "+ Nueva
// solicitud" y el modal "Completar" de SolicitudesMuestreoPage.jsx.
export default function GruposBultos({ grupos, onChange, disabled }) {
  function agregarGrupo() {
    onChange([...grupos, { cantidad_bultos: '', cantidad_unidades: '', unidad_medida: '' }]);
  }

  function quitarGrupo(i) {
    onChange(grupos.filter((_, idx) => idx !== i));
  }

  function actualizarGrupo(i, campo, valor) {
    onChange(grupos.map((g, idx) => (idx === i ? { ...g, [campo]: valor } : g)));
  }

  const totalBultos = grupos.reduce((acc, g) => acc + (Number(g.cantidad_bultos) || 0), 0);

  return (
    <div className="field">
      <label className="field-label">Grupos de bultos (opcional)</label>
      <p style={{ fontSize: 'var(--fs-xs)', color: 'var(--ink-2)', marginBottom: 'var(--sp-2)' }}>
        Si los bultos no son todos de la misma cantidad, cargalos acá en vez de (o además de) "N° de bultos" --
        ej. "4 x 50 kg" + "1 x 30 kg". Cada grupo imprime esa cantidad de etiquetas con su cantidad particular.
      </p>
      {grupos.map((g, i) => (
        <div key={i} style={{ display: 'flex', gap: 'var(--sp-2)', marginBottom: 'var(--sp-2)', alignItems: 'flex-end' }}>
          <div className="field" style={{ flex: '0 0 90px', marginBottom: 0 }}>
            <label className="field-label" style={{ fontSize: 'var(--fs-xs)' }}>Bultos</label>
            <input
              className="field-input" type="number" step="1" min="1"
              value={g.cantidad_bultos}
              onChange={(e) => actualizarGrupo(i, 'cantidad_bultos', e.target.value)}
              disabled={disabled}
            />
          </div>
          <span style={{ paddingBottom: 10 }}>x</span>
          <div className="field" style={{ flex: '0 0 110px', marginBottom: 0 }}>
            <label className="field-label" style={{ fontSize: 'var(--fs-xs)' }}>Cantidad</label>
            <input
              className="field-input" type="number" step="any" min="0"
              value={g.cantidad_unidades}
              onChange={(e) => actualizarGrupo(i, 'cantidad_unidades', e.target.value)}
              disabled={disabled}
            />
          </div>
          <div className="field" style={{ flex: '0 0 100px', marginBottom: 0 }}>
            <label className="field-label" style={{ fontSize: 'var(--fs-xs)' }}>Unidad</label>
            <input
              className="field-input"
              value={g.unidad_medida}
              onChange={(e) => actualizarGrupo(i, 'unidad_medida', e.target.value)}
              disabled={disabled}
              placeholder="kg"
            />
          </div>
          <button type="button" className="btn btn-ghost" onClick={() => quitarGrupo(i)} disabled={disabled}>
            Quitar
          </button>
        </div>
      ))}
      <button type="button" className="btn btn-secondary" onClick={agregarGrupo} disabled={disabled}>
        + Agregar grupo
      </button>
      {grupos.length > 0 && (
        <p style={{ fontSize: 'var(--fs-xs)', color: 'var(--ink-2)', marginTop: 'var(--sp-2)' }}>
          Total: {totalBultos} bulto{totalBultos === 1 ? '' : 's'} (reemplaza el N° de bultos de arriba).
        </p>
      )}
    </div>
  );
}
