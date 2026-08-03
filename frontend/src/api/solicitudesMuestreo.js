import { api } from './client';

export const solicitudesMuestreoApi = {
  listar: ({ estado, idMuestreador } = {}) => {
    const params = new URLSearchParams();
    if (estado) params.set('estado', estado);
    if (idMuestreador) params.set('id_muestreador', idMuestreador);
    return api.get(`/api/solicitudes-muestreo?${params.toString()}`);
  },
  misSolicitudes: () => api.get('/api/solicitudes-muestreo/mis-solicitudes'),
  listarMuestreadores: () => api.get('/api/solicitudes-muestreo/muestreadores'),
  crear: (data) => api.post('/api/solicitudes-muestreo', data),
  obtener: (id) => api.get(`/api/solicitudes-muestreo/${id}`),
  anular: (id, motivo) => api.put(`/api/solicitudes-muestreo/${id}/anular`, { motivo }),

  // Orden de Trabajo digital (Etapa 2: el muestreador ejecuta) -- Sección A
  // (datos físicos) + Sección B (resultados de ensayos del laboratorio de
  // la solicitud).
  obtenerEnsayosParaOrden: (id) => api.get(`/api/solicitudes-muestreo/${id}/ensayos-para-orden`),
  confirmarOrdenTrabajo: (id, body) => api.post(`/api/solicitudes-muestreo/${id}/orden-trabajo-digital`, body),
};
