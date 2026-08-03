import { useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import TopBar from '../../components/TopBar';
import { resultadosApi } from '../../api/resultados';
import { ApiError } from '../../api/client';

export default function CargaResultadosPage() {
  const { idEnvio } = useParams();
  const navigate = useNavigate();

  const [envio, setEnvio] = useState(null);
  const [valores, setValores] = useState({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const [nroProtocolo, setNroProtocolo] = useState('');
  const [fechaEmision, setFechaEmision] = useState('');
  const [archivo, setArchivo] = useState(null);
  const [guardando, setGuardando] = useState(false);

  useEffect(() => {
    resultadosApi
      .obtenerParaCarga(idEnvio)
      .then((data) => {
        setEnvio(data);
        const iniciales = {};
        data.ensayos.forEach((e) => {
          iniciales[e.id_espec_ensayo] = {
            valor_numerico: e.valor_numerico ?? '',
            valor_cualitativo: e.valor_cualitativo ?? '',
          };
        });
        setValores(iniciales);
        if (data.protocolo) {
          setNroProtocolo(data.protocolo.nro_protocolo_ext);
          setFechaEmision(data.protocolo.fecha_emision);
        }
      })
      .catch((err) => setError(err instanceof ApiError ? err.message : 'No se pudo cargar el envío'))
      .finally(() => setLoading(false));
  }, [idEnvio]);

  function actualizarValor(idEnsayo, campo, valor) {
    setValores((prev) => ({ ...prev, [idEnsayo]: { ...prev[idEnsayo], [campo]: valor } }));
  }

  function faltanObligatorios() {
    if (!envio) return true;
    return envio.ensayos.some((e) => {
      if (!e.obligatorio) return false;
      const v = valores[e.id_espec_ensayo];
      if (e.tipo_dato === 'numerico') return !v || v.valor_numerico === '';
      return !v || !v.valor_cualitativo?.trim();
    });
  }

  async function handleSubmit(e) {
    e.preventDefault();
    setError('');

    if (faltanObligatorios()) {
      setError('Completá todos los ensayos obligatorios');
      return;
    }
    if (!nroProtocolo.trim() || !fechaEmision) {
      setError('El número de protocolo y la fecha de emisión son obligatorios');
      return;
    }
    if (!archivo) {
      setError('El protocolo en PDF es obligatorio');
      return;
    }
    if (archivo.type !== 'application/pdf') {
      setError('El archivo debe ser un PDF');
      return;
    }

    const resultados = envio.ensayos.map((en) => {
      const v = valores[en.id_espec_ensayo] || {};
      return {
        id_espec_ensayo: en.id_espec_ensayo,
        valor_numerico: en.tipo_dato === 'numerico' && v.valor_numerico !== '' ? Number(v.valor_numerico) : null,
        valor_cualitativo: en.tipo_dato === 'cualitativo' ? (v.valor_cualitativo || null) : null,
      };
    });

    setGuardando(true);
    try {
      await resultadosApi.guardarResultados(idEnvio, {
        resultados,
        nroProtocoloExt: nroProtocolo.trim(),
        fechaEmision,
        protocoloPdf: archivo,
      });
      navigate('/carga-resultados', { replace: true });
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'No se pudo guardar los resultados');
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

  if (error && !envio) {
    return (
      <div className="screen">
        <TopBar titulo="Cargar resultados" subtitulo="Carga de Resultados" onBack={() => navigate(-1)} />
        <div className="screen-content">
          <div className="alert alert-danger">{error}</div>
        </div>
      </div>
    );
  }

  return (
    <div className="screen">
      <TopBar
        titulo={envio.codigo_muestra}
        subtitulo={`${envio.erp_DESART} — ${envio.laboratorio_nombre}`}
        onBack={() => navigate(-1)}
      />
      <div className="screen-content">
        <form onSubmit={handleSubmit}>
          <div className="card" style={{ marginBottom: 'var(--sp-5)' }}>
            <h2 style={{ fontSize: 'var(--fs-lg)', marginBottom: 'var(--sp-3)' }}>Resultados de análisis solicitados</h2>
            {envio.ensayos.length === 0 ? (
              <div className="alert alert-info">No hay ensayos solicitados para el envío de esta muestra.</div>
            ) : (
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Ensayo</th>
                    <th>Metodología</th>
                    <th>Especificación</th>
                    <th>Resultado</th>
                  </tr>
                </thead>
                <tbody>
                  {envio.ensayos.map((en) => {
                    const v = valores[en.id_espec_ensayo] || {};
                    return (
                      <tr key={en.id_espec_ensayo}>
                        <td>{en.nombre_ensayo}{en.obligatorio && ' *'}</td>
                        <td>{en.metodologia || '—'}</td>
                        <td>
                          {en.tipo_dato === 'numerico'
                            ? `${en.limite_inferior ?? '—'} a ${en.limite_superior ?? '—'} ${en.unidad_medida || ''}`
                            : en.valor_requerido}
                        </td>
                        <td>
                          {en.tipo_dato === 'numerico' ? (
                            <input
                              className="field-input"
                              type="number"
                              step="any"
                              value={v.valor_numerico}
                              onChange={(e) => actualizarValor(en.id_espec_ensayo, 'valor_numerico', e.target.value)}
                              disabled={guardando}
                            />
                          ) : (
                            <select
                              className="field-input"
                              value={v.valor_cualitativo}
                              onChange={(e) => actualizarValor(en.id_espec_ensayo, 'valor_cualitativo', e.target.value)}
                              disabled={guardando}
                            >
                              <option value="">Seleccioná...</option>
                              <option value="Cumple">Cumple</option>
                              <option value="No cumple">No cumple</option>
                            </select>
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            )}
          </div>

          <div className="card" style={{ marginBottom: 'var(--sp-5)' }}>
            <h2 style={{ fontSize: 'var(--fs-lg)', marginBottom: 'var(--sp-3)' }}>Protocolo del laboratorio</h2>
            <div className="field">
              <label className="field-label" htmlFor="nroProtocolo">Número de protocolo externo</label>
              <input
                id="nroProtocolo"
                className="field-input"
                value={nroProtocolo}
                onChange={(e) => setNroProtocolo(e.target.value)}
                disabled={guardando}
              />
            </div>
            <div className="field">
              <label className="field-label" htmlFor="fechaEmision">Fecha de emisión</label>
              <input
                id="fechaEmision"
                className="field-input"
                type="date"
                value={fechaEmision}
                onChange={(e) => setFechaEmision(e.target.value)}
                disabled={guardando}
              />
            </div>
            <div className="field">
              <label className="field-label" htmlFor="pdf">Protocolo (PDF)</label>
              <input
                id="pdf"
                className="field-input"
                type="file"
                accept="application/pdf"
                onChange={(e) => setArchivo(e.target.files?.[0] || null)}
                disabled={guardando}
              />
            </div>
          </div>

          {error && <div className="alert alert-danger" style={{ marginBottom: 'var(--sp-4)' }}>{error}</div>}

          <button type="submit" className="btn btn-primary btn-block btn-lg" disabled={guardando}>
            {guardando ? <span className="spinner" /> : 'Guardar resultados'}
          </button>
        </form>
      </div>
    </div>
  );
}
