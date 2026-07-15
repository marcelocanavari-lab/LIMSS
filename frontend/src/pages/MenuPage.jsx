import { useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import TopBar from '../components/TopBar';

const DATOS_MAESTROS = {
  titulo: 'Datos Maestros',
  desc: 'Especificaciones por producto y catálogo de testigos/estándares',
  icono: '■',
  roles: ['admin', 'qa'],
  items: [
    { label: 'Especificaciones', ruta: '/maestros/especificaciones', roles: ['admin', 'qa'] },
    { label: 'Testigos y estándares', ruta: '/maestros/testigos', roles: ['admin', 'qa'] },
  ],
};

const MUESTRAS_CARD = {
  titulo: 'Muestras',
  desc: 'Registro de muestreo y envío a laboratorio externo',
  icono: '◆',
  roles: ['muestreador', 'analista_qc', 'qa', 'admin'],
  items: [
    { label: 'Muestras', ruta: '/muestras', roles: ['muestreador', 'analista_qc', 'qa', 'admin'] },
    { label: 'Laboratorios externos', ruta: '/muestras/laboratorios', roles: ['admin', 'qa'] },
  ],
};

const MODULOS_OPERATIVOS = [
  {
    titulo: 'Resultados',
    desc: 'Carga de resultados analíticos y adjuntos documentales',
    icono: '●',
    roles: ['analista_qc', 'qa', 'admin'],
    disponible: true,
    ruta: '/resultados',
  },
  {
    titulo: 'Dictamen QA',
    desc: 'Revisión, desvíos y liberación final del lote',
    icono: '▲',
    roles: ['qa', 'admin'],
    disponible: true,
    ruta: '/dictamenes',
  },
];

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

  const modulosVisibles = MODULOS_OPERATIVOS.filter((m) => m.roles.includes(user?.rol));

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
        <TarjetaModulo card={DATOS_MAESTROS} rol={user?.rol} navigate={navigate} />

        <div className="select-list">
          {modulosVisibles.map((mod) => (
            <button
              key={mod.titulo}
              className="select-item"
              disabled={!mod.disponible}
              style={!mod.disponible ? { opacity: 0.5 } : undefined}
              onClick={() => mod.disponible && navigate(mod.ruta)}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--sp-3)' }}>
                <span style={{ fontSize: 22, color: 'var(--accent)' }}>{mod.icono}</span>
                <span className="select-item-main">
                  <span className="select-item-title">{mod.titulo}</span>
                  <span className="select-item-sub" style={{ fontFamily: 'var(--font-body)' }}>
                    {mod.desc}
                  </span>
                </span>
              </div>
              {mod.disponible ? (
                <span style={{ color: 'var(--accent)' }}>→</span>
              ) : (
                <span className="badge badge-neutral">Próximamente</span>
              )}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
