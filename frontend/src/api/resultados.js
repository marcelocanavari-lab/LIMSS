import { api } from './client';

export const resultadosApi = {
  listarPendientes: () => api.get('/api/envios/pendientes'),
  obtenerParaCarga: (idEnvio) => api.get(`/api/envios/${idEnvio}/resultados`),
  // Guardado parcial: resultados es independiente del protocolo -- se puede
  // guardar solo con resultados (protocolo aún no disponible) o solo
  // protocolo (ver guardarProtocolo) o ambos juntos si ya se tiene todo.
  guardarResultados: (idEnvio, { resultados, nroProtocoloExt, fechaEmision, protocoloPdf, imagenComparacionPath, observacionIa }) => {
    const formData = new FormData();
    formData.append('resultados', JSON.stringify(resultados));
    if (nroProtocoloExt) formData.append('nro_protocolo_ext', nroProtocoloExt);
    if (fechaEmision) formData.append('fecha_emision', fechaEmision);
    if (protocoloPdf) formData.append('protocolo_pdf', protocoloPdf);
    // Resultado provisorio de comparar-etiqueta (Material de Empaque): recién
    // se persiste en lims_envios acá, junto con el resto -- si nunca se corrió
    // ninguna comparación en esta sesión, no se manda nada.
    if (imagenComparacionPath) formData.append('imagen_comparacion_path', imagenComparacionPath);
    if (observacionIa) formData.append('observacion_ia', observacionIa);
    return api.postForm(`/api/envios/${idEnvio}/resultados`, formData);
  },
  guardarProtocolo: (idEnvio, { nroProtocoloExt, fechaEmision, protocoloPdf }) => {
    const formData = new FormData();
    formData.append('nro_protocolo_ext', nroProtocoloExt);
    formData.append('fecha_emision', fechaEmision);
    formData.append('protocolo_pdf', protocoloPdf);
    return api.postForm(`/api/envios/${idEnvio}/protocolo`, formData);
  },
};
