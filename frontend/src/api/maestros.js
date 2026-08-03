import { api } from './client';

export const maestrosApi = {
  // Artículos ERP (búsqueda para asociar especificaciones)
  buscarArticulos: (buscar) => api.get(`/api/maestros/articulos?buscar=${encodeURIComponent(buscar)}`),

  // Especificaciones
  crearEspecificacion: (data) => api.post('/api/maestros/especificaciones', data),
  listarEspecificaciones: ({ vigente, buscar = '', tipoMaterial } = {}) => {
    const params = new URLSearchParams();
    if (vigente !== undefined && vigente !== null) params.set('vigente', vigente);
    if (buscar) params.set('buscar', buscar);
    if (tipoMaterial) params.set('tipo_material', tipoMaterial);
    return api.get(`/api/maestros/especificaciones?${params.toString()}`);
  },
  obtenerEspecificacion: (id) => api.get(`/api/maestros/especificaciones/${id}`),
  revisarEspecificacion: (id) => api.post(`/api/maestros/especificaciones/${id}/revisar`),
  copiarEspecificacion: (id, data) => api.post(`/api/maestros/especificaciones/${id}/copiar`, data),
  editarCantidadesEspecificacion: (id, data) => api.put(`/api/maestros/especificaciones/${id}/cantidades`, data),

  // Muestras definidas por especificación
  listarMuestrasEspecificacion: (id) => api.get(`/api/maestros/especificaciones/${id}/muestras`),
  crearMuestraEspecificacion: (id, data) => api.post(`/api/maestros/especificaciones/${id}/muestras`, data),
  editarMuestraEspecificacion: (id, idMuestra, data) =>
    api.put(`/api/maestros/especificaciones/${id}/muestras/${idMuestra}`, data),
  eliminarMuestraEspecificacion: (id, idMuestra) =>
    api.del(`/api/maestros/especificaciones/${id}/muestras/${idMuestra}`),

  // Catálogo de ensayos
  listarEnsayosMaestro: (buscar = '') => api.get(`/api/maestros/ensayos?buscar=${encodeURIComponent(buscar)}`),
  crearEnsayoMaestro: (data) => api.post('/api/maestros/ensayos', data),
  editarEnsayoMaestro: (id, data) => api.put(`/api/maestros/ensayos/${id}`, data),
  eliminarEnsayoMaestro: (id) => api.del(`/api/maestros/ensayos/${id}`),

  // Ensayos aplicados a una especificación
  listarEnsayosEspecificacion: (id) => api.get(`/api/maestros/especificaciones/${id}/ensayos`),
  agregarEnsayoEspecificacion: (id, data) => api.post(`/api/maestros/especificaciones/${id}/ensayos`, data),
  editarEnsayoEspecificacion: (id, idEspecEnsayo, data) =>
    api.put(`/api/maestros/especificaciones/${id}/ensayos/${idEspecEnsayo}`, data),
  eliminarEnsayoEspecificacion: (id, idEspecEnsayo) =>
    api.del(`/api/maestros/especificaciones/${id}/ensayos/${idEspecEnsayo}`),

  // Testigos asociados a una especificación
  listarTestigosEspecificacion: (id) => api.get(`/api/maestros/especificaciones/${id}/testigos`),
  asociarTestigoEspecificacion: (id, idTestigo) =>
    api.post(`/api/maestros/especificaciones/${id}/testigos`, { id_testigo: idTestigo }),
  desasociarTestigoEspecificacion: (id, idTestigo) =>
    api.del(`/api/maestros/especificaciones/${id}/testigos/${idTestigo}`),

  // Testigos
  crearTestigo: (formData) => api.postForm('/api/maestros/testigos', formData),
  listarTestigos: ({ activo, soloAlertas, buscar = '', estado, stockBajo, orden, fechaRef } = {}) => {
    const params = new URLSearchParams();
    if (activo !== undefined && activo !== null) params.set('activo', activo);
    if (soloAlertas) params.set('solo_alertas', 'true');
    if (buscar) params.set('buscar', buscar);
    if (estado) params.set('estado', estado);
    if (stockBajo) params.set('stock_bajo', 'true');
    if (orden) params.set('orden', orden);
    if (fechaRef) params.set('fecha_ref', fechaRef);
    return api.get(`/api/maestros/testigos?${params.toString()}`);
  },
  obtenerTestigo: (id) => api.get(`/api/maestros/testigos/${id}`),
  editarTestigo: (id, formData) => api.putForm(`/api/maestros/testigos/${id}`, formData),
  historialMovimientos: (id) => api.get(`/api/maestros/testigos/${id}/movimientos`),
  cambiarEstadoTestigo: (id, activo) => api.put(`/api/maestros/testigos/${id}/estado?activo=${activo}`),
  eliminarTestigo: (id) => api.del(`/api/maestros/testigos/${id}`),
  ajustarStockTestigo: (id, cantidad, observaciones) =>
    api.post(`/api/maestros/testigos/${id}/movimiento`, { cantidad, observaciones }),
};
