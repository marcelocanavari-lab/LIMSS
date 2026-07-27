import { useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import RequireAuth from './RequireAuth';

/**
 * Guard de ruta: autenticación (delega en RequireAuth, que ya redirige a
 * /login si no hay sesión) + rol. Si no se pasa `roles`, solo exige estar
 * autenticado. Si se pasa `roles` y el usuario no está en la lista, muestra
 * una pantalla de error 403 en vez de redirigir.
 */
export default function PrivateRoute({ roles, children }) {
  return (
    <RequireAuth>
      <RoleGate roles={roles}>{children}</RoleGate>
    </RequireAuth>
  );
}

function RoleGate({ roles, children }) {
  const { user } = useAuth();
  const navigate = useNavigate();

  if (roles && !roles.includes(user?.rol)) {
    return (
      <div className="screen" style={{ alignItems: 'center', justifyContent: 'center' }}>
        <div className="state-block">
          <span className="state-block-title">403 — Acceso restringido</span>
          <span>No tenés permiso para acceder a esta sección.</span>
          <button className="btn btn-primary" style={{ marginTop: 'var(--sp-4)' }} onClick={() => navigate('/menu')}>
            Volver al menú
          </button>
        </div>
      </div>
    );
  }

  return children;
}
