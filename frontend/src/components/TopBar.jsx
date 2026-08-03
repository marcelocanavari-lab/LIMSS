import { useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';

export default function TopBar({ titulo, subtitulo, onBack }) {
  const { user, logout } = useAuth();
  const navigate = useNavigate();

  async function handleLogout() {
    await logout();
    navigate('/login', { replace: true });
  }

  return (
    <div className="topbar">
      <div className="topbar-brand">
        {onBack && (
          <button
            className="btn btn-ghost"
            style={{ padding: '0 var(--sp-2)', minHeight: 40 }}
            onClick={onBack}
            aria-label="Volver"
          >
            ←
          </button>
        )}
        <img src="/isologo_lamar.png" alt="Laboratorio Lamar" className="topbar-logo" />
        <div>
          <div style={{ fontWeight: 600, fontSize: 'var(--fs-sm)' }}>{titulo}</div>
          {subtitulo && (
            <div style={{ fontSize: 'var(--fs-xs)', color: 'var(--color-topbar-text)', opacity: 0.8 }}>
              {subtitulo}
            </div>
          )}
        </div>
      </div>

      <div className="topbar-user">
        <div className="user-chip">
          <span className="user-chip-name">
            {user?.nombre} {user?.apellido}
          </span>
          <span className="user-chip-role">{user?.rol}</span>
        </div>
        <button
          className="btn btn-ghost"
          style={{ padding: '0 var(--sp-3)', minHeight: 40 }}
          onClick={handleLogout}
        >
          Salir
        </button>
      </div>
    </div>
  );
}
