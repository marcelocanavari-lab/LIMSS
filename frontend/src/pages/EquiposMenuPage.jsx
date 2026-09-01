import { useNavigate } from 'react-router-dom';
import TopBar from '../components/TopBar';

const ITEMS = [
  { label: 'Nueva Lectura', ruta: '/equipos/nueva-lectura' },
  { label: 'Historial de Lecturas', ruta: '/equipos/historial' },
  { label: 'Gráfico de Tendencia', ruta: '/equipos/grafico' },
  { label: 'Reporte de Desviaciones', ruta: '/equipos/reporte-desviaciones' },
  { label: 'Días sin Registrar', ruta: '/equipos/dias-sin-registrar' },
];

export default function EquiposMenuPage() {
  const navigate = useNavigate();

  return (
    <div className="screen">
      <TopBar titulo="Equipos" subtitulo="Dashboard" onBack={() => navigate('/menu')} />
      <div className="screen-content">
        <h1 style={{ fontSize: 'var(--fs-lg)', marginBottom: 'var(--sp-3)' }}>Control de Variables de Equipos</h1>
        <div className="card" style={{ maxWidth: 480 }}>
          <div className="select-list">
            {ITEMS.map((item) => (
              <button key={item.ruta} className="select-item" onClick={() => navigate(item.ruta)}>
                <span className="select-item-title">{item.label}</span>
                <span style={{ color: 'var(--accent)' }}>→</span>
              </button>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
