import { useNavigate } from 'react-router-dom';
import TopBar from '../components/TopBar';

const ITEMS = [
  { label: 'Categorías de Testigos', ruta: '/maestros/testigo-categorias' },
  { label: 'Orígenes de Testigos', ruta: '/maestros/testigo-origenes' },
  { label: 'Catálogo de Ensayos', ruta: '/maestros/ensayos' },
  { label: 'Testigos y Estándares', ruta: '/maestros/testigos' },
  { label: 'Especificaciones', ruta: '/maestros/especificaciones' },
  { label: 'Laboratorios', ruta: '/muestras/laboratorios' },
];

export default function DefinicionesMenuPage() {
  const navigate = useNavigate();

  return (
    <div className="screen">
      <TopBar titulo="Definiciones" subtitulo="Dashboard" onBack={() => navigate('/menu')} />
      <div className="screen-content">
        <h1 style={{ fontSize: 'var(--fs-lg)', marginBottom: 'var(--sp-3)' }}>Definiciones</h1>
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
