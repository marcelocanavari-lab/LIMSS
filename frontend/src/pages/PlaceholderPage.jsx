import { useNavigate } from 'react-router-dom';
import TopBar from '../components/TopBar';

/**
 * Pantalla genérica para secciones del menú v2.0 todavía sin implementar
 * (Remitos de Muestras, Auditoría, Áreas y Equipos). Un solo componente
 * parametrizado en vez de tres páginas casi idénticas.
 */
export default function PlaceholderPage({ titulo, subtitulo }) {
  const navigate = useNavigate();

  return (
    <div className="screen">
      <TopBar titulo={titulo} subtitulo={subtitulo} onBack={() => navigate('/menu')} />
      <div className="screen-content" style={{ alignItems: 'center', justifyContent: 'center' }}>
        <div className="state-block">
          <span className="state-block-title">Funcionalidad en desarrollo</span>
          <span>Esta sección todavía no está disponible.</span>
          <button className="btn btn-primary" style={{ marginTop: 'var(--sp-4)' }} onClick={() => navigate('/menu')}>
            Volver al menú
          </button>
        </div>
      </div>
    </div>
  );
}
