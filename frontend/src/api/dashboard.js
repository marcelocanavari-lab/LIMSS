import { api } from './client';

export const dashboardApi = {
  obtenerResumen: () => api.get('/api/dashboard/resumen'),
  obtenerTestigos: ({ estados = [], orden = 'vencimiento_asc', limite = 100, fechaRef, diasAnticipacion } = {}) => {
    const params = new URLSearchParams();
    if (estados.length > 0) params.set('estados', estados.join(','));
    params.set('orden', orden);
    params.set('limite', limite);
    if (fechaRef) params.set('fecha_ref', fechaRef);
    if (diasAnticipacion !== undefined && diasAnticipacion !== null) params.set('dias_anticipacion', diasAnticipacion);
    return api.get(`/api/dashboard/testigos?${params.toString()}`);
  },
  obtenerSolicitudesPendientes: (idMuestreador = 0) =>
    api.get(`/api/dashboard/solicitudes-pendientes?id_muestreador=${idMuestreador}`),
  obtenerMuestreadoresActivos: () => api.get('/api/dashboard/muestreadores-activos'),
};
