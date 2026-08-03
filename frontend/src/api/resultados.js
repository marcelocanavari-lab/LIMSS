import { api } from './client';

export const resultadosApi = {
  listarPendientes: () => api.get('/api/envios/pendientes'),
  obtenerParaCarga: (idEnvio) => api.get(`/api/envios/${idEnvio}/resultados`),
  guardarResultados: (idEnvio, { resultados, nroProtocoloExt, fechaEmision, protocoloPdf }) => {
    const formData = new FormData();
    formData.append('resultados', JSON.stringify(resultados));
    formData.append('nro_protocolo_ext', nroProtocoloExt);
    formData.append('fecha_emision', fechaEmision);
    formData.append('protocolo_pdf', protocoloPdf);
    return api.postForm(`/api/envios/${idEnvio}/resultados`, formData);
  },
};
