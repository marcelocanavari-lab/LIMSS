import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import TopBar from '../components/TopBar';
import { erpConfigApi } from '../api/erpConfig';
import { ApiError } from '../api/client';

const BLOQUES = [
  { campo: 'incluye_bloque_muestras', label: 'Muestras', nombreCompleto: 'Muestras (cantidades por tipo de muestra)' },
  { campo: 'incluye_bloque_analisis_laboratorio', label: 'Análisis', nombreCompleto: 'Análisis de laboratorio (ensayos etapa análisis)' },
  { campo: 'incluye_bloque_muestreo_fisico', label: 'Muestreo', nombreCompleto: 'Muestreo físico (checklist etapa muestreo)' },
  { campo: 'incluye_bloque_testigos', label: 'Testigos', nombreCompleto: 'Testigos/estándares asociados' },
];

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

  // Genérico para los 5 checkboxes de la fila (Requiere muestreo + los 4
  // bloques) -- el backend espera el estado completo en cada PUT (no hace
  // merge parcial), así que se manda el de la fila actual con un solo campo
  // invertido.
  async function toggleCampo(s, campo) {
    setError('');
    setGuardandoCodsar(s.erp_codsar);
    try {
      const actualizado = await erpConfigApi.guardarSubarticulo(s.erp_codsar, {
        requiere_muestreo: s.requiere_muestreo,
        incluye_bloque_muestras: s.incluye_bloque_muestras,
        incluye_bloque_analisis_laboratorio: s.incluye_bloque_analisis_laboratorio,
        incluye_bloque_muestreo_fisico: s.incluye_bloque_muestreo_fisico,
        incluye_bloque_testigos: s.incluye_bloque_testigos,
        [campo]: !s[campo],
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
          vigente en Datos Maestros para decidir si genera la Solicitud de Muestreo sola. Los 4
          checkboxes de "Bloques" controlan qué secciones se muestran en la ficha de especificación
          de ese subartículo -- todos tildados por defecto, destildá solo donde corresponda ocultar
          ese bloque.
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
                  <th>Bloques en la ficha de especificación</th>
                  <th>Estado</th>
                </tr>
              </thead>
              <tbody>
                {subarticulos.map((s) => {
                  const guardando = guardandoCodsar === s.erp_codsar;
                  return (
                    <tr key={s.erp_codsar}>
                      <td style={{ fontFamily: 'var(--font-mono)' }}>{s.erp_codsar}</td>
                      <td>{s.erp_dessar || '—'}</td>
                      <td>
                        <label style={{ display: 'flex', alignItems: 'center', gap: 'var(--sp-2)', cursor: 'pointer' }}>
                          <input
                            type="checkbox"
                            checked={s.requiere_muestreo}
                            onChange={() => toggleCampo(s, 'requiere_muestreo')}
                            disabled={guardando}
                          />
                        </label>
                      </td>
                      <td>
                        <div style={{ display: 'flex', gap: 'var(--sp-3)', flexWrap: 'wrap' }}>
                          {BLOQUES.map((b) => (
                            <label
                              key={b.campo}
                              title={b.nombreCompleto}
                              style={{ display: 'flex', alignItems: 'center', gap: 'var(--sp-1)', cursor: 'pointer', whiteSpace: 'nowrap' }}
                            >
                              <input
                                type="checkbox"
                                checked={s[b.campo]}
                                onChange={() => toggleCampo(s, b.campo)}
                                disabled={guardando}
                              />
                              <span style={{ fontSize: 'var(--fs-sm)' }}>{b.label}</span>
                            </label>
                          ))}
                        </div>
                      </td>
                      <td>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--sp-2)' }}>
                          <span className={s.configurado ? 'badge badge-ok' : 'badge badge-neutral'}>
                            {s.configurado ? 'Configurado' : 'No configurado'}
                          </span>
                          {guardando && <span className="spinner" />}
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
