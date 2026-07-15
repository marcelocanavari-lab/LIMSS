import { api } from './client';

export const maestrosApi = {
  // Artículos ERP (búsqueda para asociar especificaciones)
  buscarArticulos: (buscar) => api.get(`/api/maestros/articulos?buscar=${encodeURIComponent(buscar)}`),

  // Especificaciones
  crearEspecificacion: (data) => api.post('/api/maestros/especificaciones', data),
  listarEspecificaciones: ({ vigente, buscar = '' } = {}) => {
    const params = new URLSearchParams();
    if (vigente !== undefined && vigente !== null) params.set('vigente', vigente);
    if (buscar) params.set('buscar', buscar);
    return api.get(`/api/maestros/especificaciones?${params.toString()}`);
  },
  obtenerEspecificacion: (id) => api.get(`/api/maestros/especificaciones/${id}`),
  revisarEspecificacion: (id, ensayos) =>
    api.post(`/api/maestros/especificaciones/${id}/revisar`, { ensayos }),

  // Testigos
  crearTestigo: (formData) => api.postForm('/api/maestros/testigos', formData),
  listarTestigos: ({ activo, soloAlertas, buscar = '' } = {}) => {
    const params = new URLSearchParams();
    if (activo !== undefined && activo !== null) params.set('activo', activo);
    if (soloAlertas) params.set('solo_alertas', 'true');
    if (buscar) params.set('buscar', buscar);
    return api.get(`/api/maestros/testigos?${params.toString()}`);
  },
  obtenerTestigo: (id) => api.get(`/api/maestros/testigos/${id}`),
  editarTestigo: (id, data) => api.put(`/api/maestros/testigos/${id}`, data),
  historialMovimientos: (id) => api.get(`/api/maestros/testigos/${id}/movimientos`),
  descargarCertificado: (id) => api.getBlob(`/api/maestros/testigos/${id}/certificado`),
  cambiarEstadoTestigo: (id, activo) => api.put(`/api/maestros/testigos/${id}/estado?activo=${activo}`),
  ajustarStockTestigo: (id, cantidad, observaciones) =>
    api.post(`/api/maestros/testigos/${id}/movimiento`, { cantidad, observaciones }),
};
