import { api } from './client';

export const testigosRemitosApi = {
  crearRemito: (data) => api.post('/api/testigos/remitos', data),
  listarRemitos: () => api.get('/api/testigos/remitos'),
  obtenerRemito: (id) => api.get(`/api/testigos/remitos/${id}`),
  descargarPdf: (id) => api.getBlob(`/api/testigos/remitos/${id}/pdf`),
  historialEnvios: (idTestigo) => api.get(`/api/testigos/${idTestigo}/historial-envios`),

  // Constancia de recepción (copia firmada por el laboratorio)
  adjuntarCopiaFirmada: (id, formData) => api.postForm(`/api/testigos/remitos/${id}/copia-firmada`, formData),
  descargarCopiaFirmada: (id) => api.getBlob(`/api/testigos/remitos/${id}/copia-firmada`),
};
