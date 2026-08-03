import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import TopBar from '../../components/TopBar';
import { muestrasApi } from '../../api/muestras';
import { ApiError } from '../../api/client';
import { BADGE_POR_ESTADO, ESTADOS } from './MuestrasPage';

const TIPOS_MATERIAL = [
  { value: '', label: 'Todos los materiales' },
  { value: 'materia_prima', label: 'Materia Prima' },
  { value: 'granel', label: 'Granel' },
  { value: 'semi_elaborado', label: 'Semi-Elaborado' },
  { value: 'producto_terminado', label: 'Producto Terminado' },
];

export default function ConsultaMuestrasPage() {
  const navigate = useNavigate();

  const [muestras, setMuestras] = useState([]);
  const [laboratorios, setLaboratorios] = useState([]);
  const [buscar, setBuscar] = useState('');
  const [estado, setEstado] = useState('');
  const [tipoMaterial, setTipoMaterial] = useState('');
  const [fechaDesde, setFechaDesde] = useState('');
  const [fechaHasta, setFechaHasta] = useState('');
  const [idLaboratorio, setIdLaboratorio] = useState('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    muestrasApi.listarLaboratorios(true).then(setLaboratorios).catch(() => {});
  }, []);

  useEffect(() => {
    let activo = true;
    setLoading(true);
    setError('');
    muestrasApi
      .listarMuestras({
        buscar, estado,
        tipoMaterial: tipoMaterial || undefined,
        fechaDesde: fechaDesde || undefined,
        fechaHasta: fechaHasta || undefined,
        idLaboratorio: idLaboratorio || undefined,
      })
      .then((data) => activo && setMuestras(data))
      .catch((err) => activo && setError(err instanceof ApiError ? err.message : 'No se pudo cargar el listado'))
      .finally(() => activo && setLoading(false));
    return () => {
      activo = false;
    };
  }, [buscar, estado, tipoMaterial, fechaDesde, fechaHasta, idLaboratorio]);

  return (
    <div className="screen">
      <TopBar titulo="Consulta de Muestras" subtitulo="Estado general y recorrido completo" onBack={() => navigate(-1)} />
      <div className="screen-content">
        <div style={{ display: 'flex', gap: 'var(--sp-3)', marginBottom: 'var(--sp-4)', flexWrap: 'wrap' }}>
          <input
            className="field-input"
            style={{ flex: 1, minWidth: 200 }}
            placeholder="Buscar por código, IR o material..."
            value={buscar}
            onChange={(e) => setBuscar(e.target.value)}
          />
          <select className="field-input" style={{ maxWidth: 200 }} value={estado} onChange={(e) => setEstado(e.target.value)}>
            {ESTADOS.map((e) => (
              <option key={e.value} value={e.value}>{e.label}</option>
            ))}
          </select>
          <select className="field-input" style={{ maxWidth: 200 }} value={tipoMaterial} onChange={(e) => setTipoMaterial(e.target.value)}>
            {TIPOS_MATERIAL.map((t) => (
              <option key={t.value} value={t.value}>{t.label}</option>
            ))}
          </select>
          <select className="field-input" style={{ maxWidth: 220 }} value={idLaboratorio} onChange={(e) => setIdLaboratorio(e.target.value)}>
            <option value="">Todos los laboratorios</option>
            {laboratorios.map((l) => (
              <option key={l.id_laboratorio} value={l.id_laboratorio}>{l.nombre}</option>
            ))}
          </select>
          <input
            className="field-input"
            type="date"
            style={{ maxWidth: 160 }}
            value={fechaDesde}
            onChange={(e) => setFechaDesde(e.target.value)}
            title="Fecha de muestreo desde"
          />
          <input
            className="field-input"
            type="date"
            style={{ maxWidth: 160 }}
            value={fechaHasta}
            onChange={(e) => setFechaHasta(e.target.value)}
            title="Fecha de muestreo hasta"
          />
        </div>

        {error && <div className="alert alert-danger" style={{ marginBottom: 'var(--sp-4)' }}>{error}</div>}

        {loading ? (
          <div className="state-block"><span className="spinner" /></div>
        ) : muestras.length === 0 ? (
          <div className="state-block">
            <span className="state-block-title">Sin muestras</span>
            <span>No hay muestras cargadas con estos filtros</span>
          </div>
        ) : (
          <div className="table-scroll">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Código</th>
                  <th>IR / Lote</th>
                  <th>Material</th>
                  <th>Tipo</th>
                  <th>Fecha muestreo</th>
                  <th>Muestreador</th>
                  <th>Estado</th>
                </tr>
              </thead>
              <tbody>
                {muestras.map((m) => (
                  <tr key={m.id_muestra} style={{ cursor: 'pointer' }} onClick={() => navigate(`/consulta-muestras/${m.id_muestra}`)}>
                    <td style={{ fontFamily: 'var(--font-mono)' }}>{m.codigo_muestra}</td>
                    <td style={{ fontFamily: 'var(--font-mono)' }}>
                      <span className="badge badge-neutral" style={{ marginRight: 6 }}>{m.tipo_referencia === 'ir' ? 'IR' : 'Lote'}</span>
                      {m.nro_referencia}
                    </td>
                    <td>{m.erp_DESART}</td>
                    <td>{TIPOS_MATERIAL.find((t) => t.value === m.tipo_material)?.label || m.tipo_material || '—'}</td>
                    <td>{new Date(m.fecha_muestreo).toLocaleDateString()}</td>
                    <td>{m.usuario_muestreo_nombre}</td>
                    <td><span className={`badge ${BADGE_POR_ESTADO[m.estado] || 'badge-neutral'}`}>{m.estado.replace(/_/g, ' ')}</span></td>
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
