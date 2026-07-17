import { api } from './client';

export const muestrasApi = {
  // ERP: búsqueda de IR
  buscarIR: (nroIr) => api.get(`/api/muestras/erp/ir/${encodeURIComponent(nroIr)}`),

  // Búsqueda unificada por tipo de material: IR (materia prima, ERP) o
  // número de lote interno (resto, eBR)
  buscarMaterial: (tipo, referencia) => {
    const params = new URLSearchParams();
    params.set('tipo', tipo);
    params.set('referencia', referencia);
    return api.get(`/api/muestras/buscar-material?${params.toString()}`);
  },

  // Muestras
  crearMuestra: (data) => api.post('/api/muestras/', data),
  listarMuestras: ({ estado, buscar = '' } = {}) => {
    const params = new URLSearchParams();
    if (estado) params.set('estado', estado);
    if (buscar) params.set('buscar', buscar);
    return api.get(`/api/muestras/?${params.toString()}`);
  },
  obtenerMuestra: (id) => api.get(`/api/muestras/${id}`),

  // Envío
  confirmarEnvio: (id, data) => api.post(`/api/muestras/${id}/envio`, data),
  obtenerRemito: (id) => api.get(`/api/muestras/${id}/remito`),

  // Etiqueta (REQ-ENV-003)
  generarEtiqueta: (id) => api.post(`/api/muestras/${id}/etiqueta`),
  obtenerUltimaEtiqueta: (id) => api.get(`/api/muestras/${id}/etiqueta`),

  // Laboratorios
  listarLaboratorios: (activo) => {
    const params = new URLSearchParams();
    if (activo !== undefined && activo !== null) params.set('activo', activo);
    return api.get(`/api/muestras/laboratorios?${params.toString()}`);
  },
  crearLaboratorio: (data) => api.post('/api/muestras/laboratorios', data),
  editarLaboratorio: (id, data) => api.put(`/api/muestras/laboratorios/${id}`, data),
  cambiarEstadoLaboratorio: (id, activo) => api.put(`/api/muestras/laboratorios/${id}/estado?activo=${activo}`),
};
