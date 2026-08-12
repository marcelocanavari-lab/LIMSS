import { Navigate, useLocation } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';

export default function RequireAuth({ children }) {
  const { user, loading } = useAuth();
  const location = useLocation();

  if (loading) {
    return (
      <div className="screen" style={{ alignItems: 'center', justifyContent: 'center' }}>
        <span className="spinner" />
      </div>
    );
  }

  if (!user) {
    return <Navigate to="/login" replace />;
  }

  // Cambio de PIN obligatorio: bloquea el resto de la app hasta completarlo
  // -- sin este chequeo acá (antes de renderizar children), cualquier ruta
  // navegable con user existente quedaría accesible igual.
  if (user.debe_cambiar_pin && location.pathname !== '/cambiar-pin') {
    return <Navigate to="/cambiar-pin" replace />;
  }

  return children;
}
