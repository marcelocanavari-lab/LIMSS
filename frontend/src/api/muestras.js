import { api } from './client';

export const muestrasApi = {
  // ERP: búsqueda de IR
  buscarIR: (nroIr) => api.get(`/api/muestras/erp/ir/${encodeURIComponent(nroIr)}`),

  // Búsqueda unificada por tipo de material: IR (materia prima) o número de
  // lote (resto) -- ambas contra el ERP, ver buscar_material en el backend
  buscarMaterial: (tipo, referencia) => {
    const params = new URLSearchParams();
    params.set('tipo', tipo);
    params.set('referencia', referencia);
    return api.get(`/api/muestras/buscar-material?${params.toString()}`);
  },

  // Muestras
  crearMuestra: (data) => api.post('/api/muestras/', data),
  listarMuestras: ({ estado, buscar = '', mio, tipoMaterial, fechaDesde, fechaHasta, idLaboratorio } = {}) => {
    const params = new URLSearchParams();
    if (estado) params.set('estado', estado);
    if (buscar) params.set('buscar', buscar);
    if (mio) params.set('mio', 'true');
    if (tipoMaterial) params.set('tipo_material', tipoMaterial);
    if (fechaDesde) params.set('fecha_desde', fechaDesde);
    if (fechaHasta) params.set('fecha_hasta', fechaHasta);
    if (idLaboratorio) params.set('id_laboratorio', idLaboratorio);
    return api.get(`/api/muestras/?${params.toString()}`);
  },
  pendientesEnvio: ({ buscar = '' } = {}) => {
    const params = new URLSearchParams();
    if (buscar) params.set('buscar', buscar);
    return api.get(`/api/muestras/pendientes-envio?${params.toString()}`);
  },
  obtenerMuestra: (id) => api.get(`/api/muestras/${id}`),
  editarMuestra: (id, data) => api.patch(`/api/muestras/${id}`, data),
  obtenerRecorrido: (id) => api.get(`/api/muestras/${id}/recorrido`),

  // Envíos (una muestra puede tener varios, a distintos laboratorios)
  confirmarEnvio: (id, data) => api.post(`/api/muestras/${id}/envios`, data),
  listarEnvios: (id) => api.get(`/api/muestras/${id}/envios`),
  obtenerRemito: (id, idEnvio) => api.get(`/api/muestras/${id}/envios/${idEnvio}/remito`),
  ensayosParaEnvio: (id, idLaboratorio) => api.get(`/api/muestras/${id}/ensayos-para-envio?id_laboratorio=${idLaboratorio}`),

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
