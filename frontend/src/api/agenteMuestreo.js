import { api } from './client';

export const agenteMuestreoApi = {
  listarEvaluaciones: ({ idComprobanteErp, resultado, desde, hasta } = {}) => {
    const params = new URLSearchParams();
    if (idComprobanteErp) params.set('id_comprobante_erp', idComprobanteErp);
    if (resultado) params.set('resultado', resultado);
    if (desde) params.set('desde', desde);
    if (hasta) params.set('hasta', hasta);
    return api.get(`/api/integraciones/agente/evaluaciones?${params.toString()}`);
  },
  reprocesar: (idComprobanteErp) => api.post(`/api/integraciones/agente/reprocesar/${idComprobanteErp}`),
  ejecutarAhora: () => api.post('/api/integraciones/agente/ejecutar-ahora'),
};
