import { useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import TopBar from '../components/TopBar';

const MUESTRAS_CARD = {
  titulo: 'Muestras',
  desc: 'Registro de muestreo y generación de etiquetas',
  icono: '◆',
  roles: ['muestreador', 'analista_qc', 'qa', 'admin'],
  items: [
    { label: 'Muestras', ruta: '/muestras', roles: ['muestreador', 'analista_qc', 'qa', 'admin'] },
  ],
};

const ANALISIS_DICTAMEN_CARD = {
  titulo: 'Análisis y Dictamen',
  desc: 'Envío a laboratorio, carga de resultados y dictamen final',
  icono: '●',
  roles: ['analista_qc', 'qa', 'admin'],
  items: [
    { label: 'Muestras pendientes', ruta: '/muestras?vista=pendientes', roles: ['analista_qc', 'qa', 'admin'] },
    { label: 'Cargar resultados', ruta: '/resultados', roles: ['analista_qc', 'qa', 'admin'] },
    { label: 'Dictamen QA', ruta: '/dictamenes', roles: ['qa', 'admin'] },
  ],
};

const DATOS_MAESTROS_CARD = {
  titulo: 'Datos Maestros',
  desc: 'Especificaciones, testigos/estándares y laboratorios',
  icono: '■',
  roles: ['analista_qc', 'qa', 'admin'],
  items: [
    { label: 'Especificaciones', ruta: '/maestros/especificaciones', roles: ['analista_qc', 'qa', 'admin'] },
    { label: 'Catálogo de ensayos', ruta: '/maestros/ensayos', roles: ['analista_qc', 'qa', 'admin'] },
    { label: 'Testigos y estándares', ruta: '/maestros/testigos', roles: ['analista_qc', 'qa', 'admin'] },
    { label: 'Laboratorios', ruta: '/muestras/laboratorios', roles: ['analista_qc', 'qa', 'admin'] },
  ],
};

const ADMINISTRACION_CARD = {
  titulo: 'Administración',
  desc: 'Gestión de usuarios del sistema',
  icono: '★',
  roles: ['admin'],
  items: [
    { label: 'Usuarios', ruta: '/usuarios', roles: ['admin'] },
  ],
};

function TarjetaModulo({ card, rol, navigate }) {
  if (!card.roles.includes(rol)) return null;
  const items = card.items.filter((item) => item.roles.includes(rol));
  if (items.length === 0) return null;

  return (
    <div className="card" style={{ marginBottom: 'var(--sp-5)' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--sp-3)', marginBottom: 'var(--sp-4)' }}>
        <span style={{ fontSize: 22, color: 'var(--accent)' }}>{card.icono}</span>
        <div>
          <h2 style={{ fontSize: 'var(--fs-lg)' }}>{card.titulo}</h2>
          <p style={{ fontSize: 'var(--fs-xs)', color: 'var(--ink-2)', margin: 0 }}>{card.desc}</p>
        </div>
      </div>
      <div className="select-list">
        {items.map((item) => (
          <button key={item.label} className="select-item" onClick={() => navigate(item.ruta)}>
            <span className="select-item-title">{item.label}</span>
            <span style={{ color: 'var(--accent)' }}>→</span>
          </button>
        ))}
      </div>
    </div>
  );
}

export default function MenuPage() {
  const { user } = useAuth();
  const navigate = useNavigate();

  return (
    <div className="screen">
      <TopBar titulo="LIMSS Laboratorio Lamar" subtitulo="Menú principal" />
      <div className="screen-content">
        <h1 style={{ fontSize: 'var(--fs-xl)', marginBottom: 'var(--sp-1)' }}>
          ¿Qué querés hacer?
        </h1>
        <p style={{ color: 'var(--ink-2)', marginBottom: 'var(--sp-5)' }}>
          Elegí un módulo para comenzar
        </p>

        <TarjetaModulo card={MUESTRAS_CARD} rol={user?.rol} navigate={navigate} />
        <TarjetaModulo card={ANALISIS_DICTAMEN_CARD} rol={user?.rol} navigate={navigate} />
        <TarjetaModulo card={DATOS_MAESTROS_CARD} rol={user?.rol} navigate={navigate} />
        <TarjetaModulo card={ADMINISTRACION_CARD} rol={user?.rol} navigate={navigate} />
      </div>
    </div>
  );
}
