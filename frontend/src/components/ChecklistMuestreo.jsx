// Checklist de momento 'muestreo' de una especificación (ver
// app/services/especificaciones.py::obtener_checklist_muestreo en el
// backend) -- lista dinámica de ítems, cada uno Cumple/No cumple, agrupada
// por categoría real (lims_categorias_ensayo -- Aspecto del Contenedor /
// Aspectos de la Materia Prima, ver migración de categorización de
// ensayos). El backend ya devuelve los ítems ordenados por
// cat.orden, se.orden -- acá solo se agrupan preservando ese orden (por
// eso Map en vez de volver a ordenar).
// Compartido por Ejecutar Muestreo (Orden de Trabajo Digital, atada a una
// Solicitud) y por el checklist de Nueva Muestra (creación directa, sin
// solicitud) -- ambos flujos terminan escribiendo en la misma tabla
// (lims_resultados_muestreo) por id_muestra, así que la UI tampoco se
// duplica.

// Inspección visual del contenedor al tomar la muestra -- Cumple/No cumple
// en vez de texto libre. El valor que viaja al backend sigue siendo el
// string "Cumple" / "No cumple" en el mismo campo VARCHAR de siempre, así
// que un muestreo viejo con texto libre cargado (ej. "Correcto") se sigue
// mostrando tal cual, solo que ningún botón queda marcado como seleccionado
// para ese valor.
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

export default function ChecklistMuestreo({ checklist, onChange, disabled }) {
  if (checklist.length === 0) {
    return (
      <div className="alert alert-warn" style={{ marginBottom: 'var(--sp-3)' }}>
        Esta especificación no tiene ítems de muestreo configurados -- no hay nada que revisar acá.
      </div>
    );
  }

  const grupos = new Map();
  for (const item of checklist) {
    const clave = item.id_categoria ?? item.categoria_codigo ?? '';
    if (!grupos.has(clave)) {
      grupos.set(clave, { nombre: item.categoria_nombre, items: [] });
    }
    grupos.get(clave).items.push(item);
  }

  return (
    <>
      {[...grupos.entries()].map(([clave, grupo]) => (
        <div key={clave} style={{ marginBottom: 'var(--sp-3)' }}>
          {grupo.nombre && (
            <h3 style={{ fontSize: 'var(--fs-sm)', color: 'var(--ink-2)', marginBottom: 'var(--sp-2)' }}>
              {grupo.nombre}
            </h3>
          )}
          <div style={{ display: 'flex', gap: 'var(--sp-3)', flexWrap: 'wrap' }}>
            {grupo.items.map((item) => (
              <div key={item.id_espec_ensayo} style={{ flex: '1 1 260px' }}>
                <CampoCumple
                  label={item.nombre_ensayo}
                  valor={item.valor_cualitativo}
                  onChange={(v) => onChange(item.id_espec_ensayo, v)}
                  disabled={disabled}
                />
                {item.especificacion_texto && (
                  <p style={{ fontSize: 'var(--fs-xs)', color: 'var(--ink-2)', marginTop: 'var(--sp-1)' }}>
                    {item.especificacion_texto}
                  </p>
                )}
              </div>
            ))}
          </div>
        </div>
      ))}
    </>
  );
}
