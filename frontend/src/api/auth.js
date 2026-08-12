import { api } from './client';

export const authApi = {
  login: (codigo, pin) => api.postPublic('/api/auth/login', { codigo, pin }),
  logout: () => api.post('/api/auth/logout'),
  me: () => api.get('/api/auth/me'),
  cambiarPin: (pinActual, pinNuevo) =>
    api.post('/api/auth/cambiar-pin', { pin_actual: pinActual, pin_nuevo: pinNuevo }),

  listarUsuarios: () => api.get('/api/auth/usuarios'),
  crearUsuario: (data) => api.post('/api/auth/usuarios', data),
  editarUsuario: (idUsuario, data) => api.put(`/api/auth/usuarios/${idUsuario}`, data),
  cambiarEstadoUsuario: (idUsuario, activo) =>
    api.put(`/api/auth/usuarios/${idUsuario}/estado?activo=${activo}`),
  resetearPin: (idUsuario, pin, forzarCambioPin) =>
    api.put(`/api/auth/usuarios/${idUsuario}/pin`, { pin, forzar_cambio_pin: forzarCambioPin }),
};
