import { api } from './client';

export const dictamenesApi = {
  listarPendientes: () => api.get('/api/dictamen/pendientes'),
  obtenerDetalle: (id) => api.get(`/api/dictamen/${id}`),
  emitirDictamen: (id, data) => api.post(`/api/dictamen/${id}`, data),
};
