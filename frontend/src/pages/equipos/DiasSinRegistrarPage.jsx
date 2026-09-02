import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import TopBar from '../../components/TopBar';
import { equiposApi } from '../../api/equipos';
import { ApiError } from '../../api/client';

function hoyISO() {
  return new Date().toISOString().slice(0, 10);
}

function hace30DiasISO() {
  const d = new Date();
  d.setDate(d.getDate() - 30);
  return d.toISOString().slice(0, 10);
}

function formatearFecha(fechaISO) {
  // new Date('YYYY-MM-DD') interpreta la fecha en UTC -- se arma con las
  // partes sueltas para no correr un día para atrás en huso horario
  // negativo (mismo problema que el resto de las pantallas de fecha del
  // proyecto).
  const [anio, mes, dia] = fechaISO.split('-');
  return `${dia}/${mes}/${anio}`;
}

// Reporte de "Días sin registrar" -- para detectar huecos en el control
// diario: de todos los días hábiles (lunes a viernes) del rango elegido,
// cuáles NO tienen ninguna lectura cargada para el equipo. Los fines de
// semana los excluye directamente el backend (el laboratorio no abre esos
// días, no corresponde exigirles registro).
export default function DiasSinRegistrarPage() {
  const navigate = useNavigate();

  const [equipos, setEquipos] = useState([]);
  const [idEquipo, setIdEquipo] = useState('');
  const [fechaDesde, setFechaDesde] = useState(hace30DiasISO());
  const [fechaHasta, setFechaHasta] = useState(hoyISO());
  const [dias, setDias] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    equiposApi.listar().then((data) => {
      setEquipos(data);
      if (data.length >= 1) setIdEquipo((prev) => prev || String(data[0].id_equipo));
    }).catch((err) => setError(err instanceof ApiError ? err.message : 'No se pudo cargar la pantalla'));
  }, []);

  // Carga el reporte con el rango de fechas ACTUAL de los inputs -- se
  // llama automáticamente al cambiar de equipo (selección completa de un
  // <select>, sin riesgo de "valor a medio tipear"), y a demanda desde el
  // botón "Generar" para las fechas. Mismo fix y mismo criterio que
  // GraficoTendenciaPage.jsx/HistorialLecturasPage.jsx/
  // ReporteDesviacionesPage.jsx.
  function cargar() {
    if (!idEquipo) return;
    setLoading(true);
    setError('');
    equiposApi
      .diasSinRegistrar({ idEquipo, fechaDesde, fechaHasta })
      .then(setDias)
      .catch((err) => setError(err instanceof ApiError ? err.message : 'No se pudo cargar el reporte'))
      .finally(() => setLoading(false));
  }

  useEffect(cargar, [idEquipo]);

  const equipoElegido = equipos.find((eq) => String(eq.id_equipo) === idEquipo);

  return (
    <div className="screen">
      <TopBar titulo="Días sin Registrar" subtitulo="Equipos" onBack={() => navigate(-1)} />
      <div className="screen-content">
        <div className="card" style={{ marginBottom: 'var(--sp-4)' }}>
          <div style={{ display: 'flex', gap: 'var(--sp-3)', flexWrap: 'wrap', alignItems: 'flex-end' }}>
            <div className="field" style={{ flex: '1 1 220px' }}>
              <label className="field-label" htmlFor="equipo">Equipo</label>
              <select id="equipo" className="field-input" value={idEquipo} onChange={(e) => setIdEquipo(e.target.value)}>
                {equipos.map((eq) => (
                  <option key={eq.id_equipo} value={eq.id_equipo}>{eq.nombre}</option>
                ))}
              </select>
            </div>
            <div className="field" style={{ flex: '1 1 160px' }}>
              <label className="field-label" htmlFor="desde">Desde</label>
              <input id="desde" className="field-input" type="date" value={fechaDesde} onChange={(e) => setFechaDesde(e.target.value)} />
            </div>
            <div className="field" style={{ flex: '1 1 160px' }}>
              <label className="field-label" htmlFor="hasta">Hasta</label>
              <input id="hasta" className="field-input" type="date" value={fechaHasta} onChange={(e) => setFechaHasta(e.target.value)} />
            </div>
            <button className="btn btn-primary" onClick={cargar} disabled={loading}>
              {loading ? <span className="spinner" /> : 'Generar →'}
            </button>
          </div>
        </div>

        {error && <div className="alert alert-danger" style={{ marginBottom: 'var(--sp-4)' }}>{error}</div>}

        {loading ? (
          <div className="state-block"><span className="spinner" /></div>
        ) : dias.length === 0 ? (
          <div className="alert alert-ok">
            Todos los días hábiles del período tienen registro{equipoElegido ? ` -- ${equipoElegido.nombre}` : ''}.
          </div>
        ) : (
          <>
            <p style={{ color: 'var(--ink-2)', marginBottom: 'var(--sp-3)' }}>
              {dias.length} día{dias.length === 1 ? '' : 's'} hábil{dias.length === 1 ? '' : 'es'} sin registro -- {equipoElegido?.nombre}
            </p>
            <div className="table-scroll">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Día</th>
                  </tr>
                </thead>
                <tbody>
                  {dias.map((d) => (
                    <tr key={d.fecha}>
                      <td>{d.dia_semana} {formatearFecha(d.fecha)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
