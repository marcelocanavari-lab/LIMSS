import { api } from './client';

export const dashboardApi = {
  obtenerResumen: () => api.get('/api/dashboard/resumen'),
  obtenerTestigos: ({ estados = [], orden = 'vencimiento_asc', limite = 100 } = {}) => {
    const params = new URLSearchParams();
    if (estados.length > 0) params.set('estados', estados.join(','));
    params.set('orden', orden);
    params.set('limite', limite);
    return api.get(`/api/dashboard/testigos?${params.toString()}`);
  },
  obtenerSolicitudesPendientes: (idMuestreador = 0) =>
    api.get(`/api/dashboard/solicitudes-pendientes?id_muestreador=${idMuestreador}`),
  obtenerMuestreadoresActivos: () => api.get('/api/dashboard/muestreadores-activos'),
};
