import { api } from './client';

export const novedadesEmpaqueApi = {
  listar: (estado) => {
    const params = new URLSearchParams();
    if (estado) params.set('estado', estado);
    return api.get(`/api/novedades-empaque?${params.toString()}`);
  },
  crear: (data) => api.post('/api/novedades-empaque', data),
  resolver: (idNovedad, observaciones) =>
    api.post(`/api/novedades-empaque/${idNovedad}/resolver`, { observaciones_resolucion: observaciones || null }),
};
