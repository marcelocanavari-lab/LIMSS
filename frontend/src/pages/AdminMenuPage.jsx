import { useNavigate } from 'react-router-dom';
import TopBar from '../components/TopBar';

const ITEMS = [
  { label: 'Gestión de Usuarios', ruta: '/usuarios' },
  { label: 'Configuración ERP', ruta: '/erp-config' },
  { label: 'Subartículos y Muestreo', ruta: '/subarticulos-config' },
  { label: 'Impresoras de Etiquetas', ruta: '/muestras/impresoras' },
  { label: 'Auditoría', ruta: '/auditoria' },
];

export default function AdminMenuPage() {
  const navigate = useNavigate();

  return (
    <div className="screen">
      <TopBar titulo="Administración" subtitulo="Dashboard" onBack={() => navigate('/menu')} />
      <div className="screen-content">
        <h1 style={{ fontSize: 'var(--fs-lg)', marginBottom: 'var(--sp-3)' }}>Administración</h1>
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
