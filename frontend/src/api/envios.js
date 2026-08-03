import { api } from './client';

export const enviosApi = {
  generarRemitoPdf: (idEnvio) => api.post(`/api/envios/${idEnvio}/remito`),
  // Devuelve { blob, numero, fecha } o rechaza con ApiError(status=404) si todavía no existe.
  obtenerRemitoPdf: (idEnvio) => api.getBlobConMeta(`/api/envios/${idEnvio}/remito`),

  // Constancia de recepción (copia firmada por el laboratorio) -- mismo
  // patrón que testigosRemitosApi.adjuntarCopiaFirmada.
  adjuntarCopiaFirmada: (idEnvio, formData) => api.postForm(`/api/envios/${idEnvio}/remito/copia-firmada`, formData),
};
