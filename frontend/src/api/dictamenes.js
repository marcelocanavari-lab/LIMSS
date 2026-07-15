import { api } from './client';

export const dictamenesApi = {
  obtenerDictamen: (id) => api.get(`/api/dictamenes/muestras/${id}`),
  emitirDictamen: (id, data) => api.post(`/api/dictamenes/muestras/${id}`, data),
};
