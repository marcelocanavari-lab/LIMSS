import { useLocation, useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import TopBar from '../components/TopBar';

// Menú v2.0 -- estructura y roles definidos en el rediseño.
// Cada ítem declara sus propios roles (no solo la card): esto permite que,
// por ejemplo, "Muestras" muestre "Mis Muestras" solo a muestreador y
// "Consulta de Muestras" solo a los demás roles, dentro de la misma card.

const MUESTRAS_CARD = {
  titulo: 'Muestras',
  desc: 'Registro de muestreo y generación de etiquetas',
  icono: '◆',
  roles: ['muestreador', 'analista_qc', 'qa', 'admin'],
  items: [
    { label: 'Nueva Muestra', ruta: '/muestras/nueva', roles: ['muestreador', 'analista_qc', 'qa', 'admin'] },
    { label: 'Mis Muestras', ruta: '/muestras', roles: ['muestreador'] },
    { label: 'Consulta de Muestras', ruta: '/consulta-muestras', roles: ['analista_qc', 'qa', 'admin'] },
  ],
};

const ANALISIS_CONTROL_CARD = {
  titulo: 'Análisis y Control',
  desc: 'Envío a laboratorio, remitos y carga de resultados',
  icono: '●',
  roles: ['analista_qc', 'qa', 'admin'],
  items: [
    { label: 'Envío de Muestras', ruta: '/envios', roles: ['analista_qc', 'qa', 'admin'] },
    { label: 'Carga de Resultados', ruta: '/carga-resultados', roles: ['analista_qc', 'qa', 'admin'] },
  ],
};

const DATOS_MAESTROS_CARD = {
  titulo: 'Datos Maestros',
  desc: 'Especificaciones, testigos/estándares y laboratorios',
  icono: '■',
  roles: ['analista_qc', 'qa', 'admin'],
  items: [
    { label: 'Especificaciones', ruta: '/maestros/especificaciones', roles: ['analista_qc', 'qa', 'admin'] },
    { label: 'Catálogo de Ensayos', ruta: '/maestros/ensayos', roles: ['analista_qc', 'qa', 'admin'] },
    { label: 'Testigos y Estándares', ruta: '/maestros/testigos', roles: ['analista_qc', 'qa', 'admin'] },
    { label: 'Laboratorios', ruta: '/muestras/laboratorios', roles: ['analista_qc', 'qa', 'admin'] },
  ],
};

const CONTROL_CALIDAD_CARD = {
  titulo: 'Control de Calidad',
  desc: 'Emisión del dictamen final',
  icono: '✓',
  roles: ['qa', 'admin'],
  items: [
    { label: 'Dictamen QA', ruta: '/dictamenes', roles: ['qa', 'admin'] },
  ],
};

const ADMINISTRACION_CARD = {
  titulo: 'Administración',
  desc: 'Usuarios, configuración del ERP y auditoría',
  icono: '★',
  roles: ['admin'],
  items: [
    { label: 'Usuarios', ruta: '/usuarios', roles: ['admin'] },
    { label: 'Configuración ERP', ruta: '/erp-config', roles: ['admin'] },
    { label: 'Auditoría', ruta: '/auditoria', roles: ['admin'] },
  ],
};

function TarjetaModulo({ card, rol, navigate, pathname }) {
  if (!card.roles.includes(rol)) return null;
  const items = card.items.filter((item) => item.roles.includes(rol));
  if (items.length === 0) return null;

  return (
    <div className="card">
      <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--sp-2)', marginBottom: 'var(--sp-3)' }}>
        <span style={{ fontSize: 20, color: 'var(--accent)' }}>{card.icono}</span>
        <div>
          <h2 style={{ fontSize: 'var(--fs-base)' }}>{card.titulo}</h2>
          <p style={{ fontSize: 'var(--fs-xs)', color: 'var(--ink-2)', margin: 0 }}>{card.desc}</p>
        </div>
      </div>
      <div className="select-list">
        {items.map((item) => (
          <button
            key={item.label}
            className={`select-item ${pathname === item.ruta ? 'select-item-active' : ''}`}
            onClick={() => navigate(item.ruta)}
          >
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
  const { pathname } = useLocation();

  return (
    <div className="screen">
      <TopBar titulo="LIMSS Laboratorio Lamar" subtitulo="Menú principal" />
      <div className="screen-content">
        <h1 style={{ fontSize: 'var(--fs-lg)', marginBottom: 2 }}>
          ¿Qué querés hacer?
        </h1>
        <p style={{ color: 'var(--ink-2)', marginBottom: 'var(--sp-3)', fontSize: 'var(--fs-sm)' }}>
          Elegí un módulo para comenzar
        </p>

        <div className="menu-grid">
          <TarjetaModulo card={MUESTRAS_CARD} rol={user?.rol} navigate={navigate} pathname={pathname} />
          <TarjetaModulo card={ANALISIS_CONTROL_CARD} rol={user?.rol} navigate={navigate} pathname={pathname} />
          <TarjetaModulo card={DATOS_MAESTROS_CARD} rol={user?.rol} navigate={navigate} pathname={pathname} />
          <TarjetaModulo card={CONTROL_CALIDAD_CARD} rol={user?.rol} navigate={navigate} pathname={pathname} />
          <TarjetaModulo card={ADMINISTRACION_CARD} rol={user?.rol} navigate={navigate} pathname={pathname} />
        </div>
      </div>
    </div>
  );
}
