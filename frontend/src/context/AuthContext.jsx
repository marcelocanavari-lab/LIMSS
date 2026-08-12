import { createContext, useContext, useState, useCallback, useEffect } from 'react';
import { authApi } from '../api/auth';
import { getToken, setToken, clearToken } from '../api/client';

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const token = getToken();
    if (!token) {
      setLoading(false);
      return;
    }
    authApi
      .me()
      .then(setUser)
      .catch(() => clearToken())
      .finally(() => setLoading(false));
  }, []);

  const login = useCallback(async (codigo, pin) => {
    const data = await authApi.login(codigo, pin);
    setToken(data.access_token);
    setUser({
      id_usuario: data.id_usuario,
      nombre: data.nombre,
      apellido: data.apellido,
      rol: data.rol,
      codigo,
      debe_cambiar_pin: data.requiere_cambio_pin,
    });
    return data;
  }, []);

  const logout = useCallback(async () => {
    try {
      await authApi.logout();
    } catch {
      // si falla igual cerramos sesión localmente
    }
    clearToken();
    setUser(null);
  }, []);

  // Se llama al completar Cambiar mi PIN -- libera el acceso normal sin
  // necesitar un refresh de página ni volver a pedir /me.
  const marcarPinCambiado = useCallback(() => {
    setUser((prev) => (prev ? { ...prev, debe_cambiar_pin: false } : prev));
  }, []);

  return (
    <AuthContext.Provider value={{ user, loading, login, logout, marcarPinCambiado }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth debe usarse dentro de AuthProvider');
  return ctx;
}
