import { api } from './client';

export const resultadosApi = {
  obtenerParaCarga: (id) => api.get(`/api/resultados/muestras/${id}`),
  iniciarCarga: (id) => api.post(`/api/resultados/muestras/${id}/iniciar`),
  guardarResultados: (id, { resultados, nroProtocoloExt, fechaEmision, protocoloPdf }) => {
    const formData = new FormData();
    formData.append('resultados', JSON.stringify(resultados));
    formData.append('nro_protocolo_ext', nroProtocoloExt);
    formData.append('fecha_emision', fechaEmision);
    formData.append('protocolo_pdf', protocoloPdf);
    return api.postForm(`/api/resultados/muestras/${id}/guardar`, formData);
  },
  descargarProtocolo: (id) => api.getBlob(`/api/resultados/muestras/${id}/protocolo`),
};
