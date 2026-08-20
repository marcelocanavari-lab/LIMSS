import { useNavigate } from 'react-router-dom';
import TopBar from '../components/TopBar';

const ITEMS = [
  { label: 'Solicitud de Muestreo', ruta: '/solicitudes-muestreo' },
  { label: 'Nueva Muestra', ruta: '/muestras/nueva' },
  { label: 'Consulta de Muestras', ruta: '/consulta-muestras' },
];

export default function MuestrasMenuPage() {
  const navigate = useNavigate();

  return (
    <div className="screen">
      <TopBar titulo="Muestras" subtitulo="Dashboard" onBack={() => navigate('/menu')} />
      <div className="screen-content">
        <h1 style={{ fontSize: 'var(--fs-lg)', marginBottom: 'var(--sp-3)' }}>Muestras</h1>
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
