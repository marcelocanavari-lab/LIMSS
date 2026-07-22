import { useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import TopBar from '../../components/TopBar';
import { maestrosApi } from '../../api/maestros';
import { ApiError } from '../../api/client';

export default function TestigoFormPage({ modo }) {
  const esEdicion = modo === 'editar';
  const { id } = useParams();
  const navigate = useNavigate();

  const [codigo, setCodigo] = useState('');
  const [nombre, setNombre] = useState('');
  const [nroLote, setNroLote] = useState('');
  const [nroIr, setNroIr] = useState('');
  const [fechaVencimiento, setFechaVencimiento] = useState('');
  const [stockActual, setStockActual] = useState('');
  const [stockMinimo, setStockMinimo] = useState('');
  const [unidadMedida, setUnidadMedida] = useState('');
  const [observaciones, setObservaciones] = useState('');
  const [archivo, setArchivo] = useState(null);
  const [tieneCertificado, setTieneCertificado] = useState(false);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(esEdicion);
  const [guardando, setGuardando] = useState(false);

  useEffect(() => {
    if (!esEdicion) return;
    maestrosApi
      .obtenerTestigo(id)
      .then((t) => {
        setCodigo(t.codigo);
        setNombre(t.nombre);
        setNroLote(t.nro_lote);
        setNroIr(t.nro_ir || '');
        setFechaVencimiento(t.fecha_vencimiento);
        setStockMinimo(String(t.stock_minimo));
        setUnidadMedida(t.unidad_medida || '');
        setObservaciones(t.observaciones || '');
        setTieneCertificado(!!t.pdf_certificado);
      })
      .catch((err) => setError(err instanceof ApiError ? err.message : 'No se pudo cargar el testigo'))
      .finally(() => setLoading(false));
  }, [esEdicion, id]);

  async function verCertificado() {
    try {
      const blob = await maestrosApi.descargarCertificado(id);
      const url = URL.createObjectURL(blob);
      window.open(url, '_blank');
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'No se pudo descargar el certificado');
    }
  }

  async function handleSubmit(e) {
    e.preventDefault();
    setError('');

    if (!nombre.trim() || !nroLote.trim() || !fechaVencimiento || (!esEdicion && !codigo.trim())) {
      setError('Completá todos los campos obligatorios');
      return;
    }
    if (archivo && archivo.type !== 'application/pdf') {
      setError('El archivo debe ser un PDF');
      return;
    }

    setGuardando(true);
    try {
      if (esEdicion) {
        const formData = new FormData();
        formData.append('nombre', nombre.trim());
        formData.append('nro_lote', nroLote.trim());
        if (nroIr.trim()) formData.append('nro_ir', nroIr.trim());
        formData.append('fecha_vencimiento', fechaVencimiento);
        formData.append('stock_minimo', stockMinimo || '0');
        if (unidadMedida.trim()) formData.append('unidad_medida', unidadMedida.trim());
        if (observaciones.trim()) formData.append('observaciones', observaciones.trim());
        if (archivo) formData.append('pdf_certificado', archivo);
        await maestrosApi.editarTestigo(id, formData);
        navigate(`/maestros/testigos/${id}`, { replace: true });
      } else {
        const formData = new FormData();
        formData.append('codigo', codigo.trim().toUpperCase());
        formData.append('nombre', nombre.trim());
        formData.append('nro_lote', nroLote.trim());
        if (nroIr.trim()) formData.append('nro_ir', nroIr.trim());
        formData.append('fecha_vencimiento', fechaVencimiento);
        formData.append('stock_actual', stockActual || '0');
        formData.append('stock_minimo', stockMinimo || '0');
        if (unidadMedida.trim()) formData.append('unidad_medida', unidadMedida.trim());
        if (observaciones.trim()) formData.append('observaciones', observaciones.trim());
        if (archivo) formData.append('pdf_certificado', archivo);
        const testigo = await maestrosApi.crearTestigo(formData);
        navigate(`/maestros/testigos/${testigo.id_testigo}`, { replace: true });
      }
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'No se pudo guardar el testigo');
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
        titulo={esEdicion ? 'Editar testigo' : 'Nuevo testigo'}
        subtitulo="Datos Maestros"
        onBack={() => navigate(esEdicion ? `/maestros/testigos/${id}` : '/maestros/testigos')}
      />
      <div className="screen-content">
        <form onSubmit={handleSubmit}>
          <div className="card" style={{ marginBottom: 'var(--sp-5)' }}>
            <div className="field">
              <label className="field-label" htmlFor="codigo">Código único</label>
              {esEdicion ? (
                <input id="codigo" className="field-input" value={codigo} disabled />
              ) : (
                <input
                  id="codigo"
                  className="field-input"
                  placeholder="Ej. TEST-0042"
                  value={codigo}
                  onChange={(e) => setCodigo(e.target.value)}
                  disabled={guardando}
                />
              )}
            </div>

            <div className="field">
              <label className="field-label" htmlFor="nombre">Nombre / descripción del estándar</label>
              <input
                id="nombre"
                className="field-input"
                placeholder="Ej. Estándar de Referencia USP Amoxicilina"
                value={nombre}
                onChange={(e) => setNombre(e.target.value)}
                disabled={guardando}
              />
            </div>

            <div className="field">
              <label className="field-label" htmlFor="nroLote">Número de lote / IR del testigo</label>
              <input
                id="nroLote"
                className="field-input"
                value={nroLote}
                onChange={(e) => setNroLote(e.target.value)}
                disabled={guardando}
              />
            </div>

            <div className="field">
              <label className="field-label" htmlFor="nroIr">N° de IR (ej. 262/20)</label>
              <input
                id="nroIr"
                className="field-input"
                placeholder="Ej. 262/20"
                value={nroIr}
                onChange={(e) => setNroIr(e.target.value)}
                maxLength={6}
                disabled={guardando}
              />
            </div>

            <div className="field">
              <label className="field-label" htmlFor="fechaVencimiento">Fecha de vencimiento / recertificación</label>
              <input
                id="fechaVencimiento"
                className="field-input"
                type="date"
                value={fechaVencimiento}
                onChange={(e) => setFechaVencimiento(e.target.value)}
                disabled={guardando}
              />
            </div>

            <div style={{ display: 'flex', gap: 'var(--sp-3)' }}>
              {!esEdicion && (
                <div className="field" style={{ flex: 1 }}>
                  <label className="field-label" htmlFor="stockActual">Stock actual</label>
                  <input
                    id="stockActual"
                    className="field-input"
                    type="number"
                    step="any"
                    min="0"
                    value={stockActual}
                    onChange={(e) => setStockActual(e.target.value)}
                    disabled={guardando}
                  />
                </div>
              )}
              <div className="field" style={{ flex: 1 }}>
                <label className="field-label" htmlFor="stockMinimo">Stock mínimo de alerta</label>
                <input
                  id="stockMinimo"
                  className="field-input"
                  type="number"
                  step="any"
                  min="0"
                  value={stockMinimo}
                  onChange={(e) => setStockMinimo(e.target.value)}
                  disabled={guardando}
                />
              </div>
              <div className="field" style={{ flex: 1 }}>
                <label className="field-label" htmlFor="unidadMedida">Unidad</label>
                <input
                  id="unidadMedida"
                  className="field-input"
                  placeholder="g, mL, u..."
                  value={unidadMedida}
                  onChange={(e) => setUnidadMedida(e.target.value)}
                  disabled={guardando}
                />
              </div>
            </div>

            <div className="field">
              <label className="field-label" htmlFor="observaciones">Observaciones</label>
              <input
                id="observaciones"
                className="field-input"
                placeholder="Notas adicionales (opcional)"
                value={observaciones}
                onChange={(e) => setObservaciones(e.target.value)}
                disabled={guardando}
              />
            </div>

            <div className="field">
              <label className="field-label" htmlFor="pdf">Certificado analítico (PDF) (opcional)</label>
              {esEdicion && tieneCertificado && !archivo && (
                <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--sp-3)', marginBottom: 'var(--sp-2)' }}>
                  <button type="button" className="btn btn-ghost" onClick={verCertificado}>
                    Ver certificado actual
                  </button>
                </div>
              )}
              <input
                id="pdf"
                className="field-input"
                type="file"
                accept="application/pdf"
                onChange={(e) => setArchivo(e.target.files?.[0] || null)}
                disabled={guardando}
              />
              {esEdicion && (
                <span style={{ fontSize: 'var(--fs-xs)', color: 'var(--ink-2)' }}>
                  {tieneCertificado ? 'Dejalo vacío para conservar el certificado actual, o subí uno nuevo para reemplazarlo.' : 'Todavía no tiene certificado cargado.'}
                </span>
              )}
            </div>
          </div>

          {error && <div className="alert alert-danger" style={{ marginBottom: 'var(--sp-4)' }}>{error}</div>}

          <button type="submit" className="btn btn-primary btn-block btn-lg" disabled={guardando}>
            {guardando ? <span className="spinner" /> : esEdicion ? 'Guardar cambios' : 'Crear testigo'}
          </button>
        </form>
      </div>
    </div>
  );
}
