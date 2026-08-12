import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import TopBar from '../components/TopBar';
import { erpConfigApi } from '../api/erpConfig';
import { ApiError } from '../api/client';

export default function SubarticulosConfigPage() {
  const navigate = useNavigate();

  const [subarticulos, setSubarticulos] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [guardandoCodsar, setGuardandoCodsar] = useState(null);

  function cargar() {
    setLoading(true);
    setError('');
    erpConfigApi
      .listarSubarticulos()
      .then(setSubarticulos)
      .catch((err) => setError(err instanceof ApiError ? err.message : 'No se pudo cargar el catálogo de subartículos'))
      .finally(() => setLoading(false));
  }

  useEffect(cargar, []);

  async function toggleRequiereMuestreo(s) {
    setError('');
    setGuardandoCodsar(s.erp_codsar);
    try {
      const actualizado = await erpConfigApi.guardarSubarticulo(s.erp_codsar, {
        requiere_muestreo: !s.requiere_muestreo,
      });
      setSubarticulos((prev) => prev.map((item) => (item.erp_codsar === s.erp_codsar ? actualizado : item)));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'No se pudo guardar el subartículo');
    } finally {
      setGuardandoCodsar(null);
    }
  }

  return (
    <div className="screen">
      <TopBar titulo="Subartículos y Muestreo" subtitulo="Administración" onBack={() => navigate(-1)} />
      <div className="screen-content">
        <p style={{ color: 'var(--ink-2)', marginBottom: 'var(--sp-4)' }}>
          Catálogo de subartículos del ERP (GIT59SAR) -- son los tipos de material (materia prima,
          granel, semi-elaborado, etc.), no artículos individuales. Tildá "Requiere muestreo" en los
          que correspondan: el agente de detección de IR consulta esto junto con la especificación
          vigente en Datos Maestros para decidir si genera la Solicitud de Muestreo sola.
        </p>

        {error && <div className="alert alert-danger" style={{ marginBottom: 'var(--sp-4)' }}>{error}</div>}

        {loading ? (
          <div className="state-block"><span className="spinner" /></div>
        ) : subarticulos.length === 0 ? (
          <div className="state-block"><span className="state-block-title">El ERP no tiene subartículos cargados en GIT59SAR</span></div>
        ) : (
          <div className="table-scroll">
            <table className="data-table">
              <thead>
                <tr>
                  <th>CODSAR</th>
                  <th>Descripción (ERP)</th>
                  <th>Requiere muestreo</th>
                  <th>Estado</th>
                </tr>
              </thead>
              <tbody>
                {subarticulos.map((s) => (
                  <tr key={s.erp_codsar}>
                    <td style={{ fontFamily: 'var(--font-mono)' }}>{s.erp_codsar}</td>
                    <td>{s.erp_dessar || '—'}</td>
                    <td>
                      <label style={{ display: 'flex', alignItems: 'center', gap: 'var(--sp-2)', cursor: 'pointer' }}>
                        <input
                          type="checkbox"
                          checked={s.requiere_muestreo}
                          onChange={() => toggleRequiereMuestreo(s)}
                          disabled={guardandoCodsar === s.erp_codsar}
                        />
                        {guardandoCodsar === s.erp_codsar && <span className="spinner" />}
                      </label>
                    </td>
                    <td>
                      <span className={s.configurado ? 'badge badge-ok' : 'badge badge-neutral'}>
                        {s.configurado ? 'Configurado' : 'No configurado'}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
