import { api } from './client';

export const enviosApi = {
  generarRemitoPdf: (idEnvio) => api.post(`/api/envios/${idEnvio}/remito`),
  // Devuelve { blob, numero, fecha } o rechaza con ApiError(status=404) si todavía no existe.
  obtenerRemitoPdf: (idEnvio) => api.getBlobConMeta(`/api/envios/${idEnvio}/remito`),

  // Historial completo (append-only: "Generar uno nuevo" nunca sobrescribe,
  // ver el docstring del módulo en el backend) -- más reciente primero.
  listarRemitos: (idEnvio) => api.get(`/api/envios/${idEnvio}/remitos`),
  // Descarga un remito PUNTUAL del historial por su id (a diferencia de
  // obtenerRemitoPdf, que siempre trae el más reciente).
  obtenerRemitoPorId: (idRemito) => api.getBlobConMeta(`/api/envios/remitos/${idRemito}`),

  // Constancia de recepción (copia firmada por el laboratorio) -- mismo
  // patrón que testigosRemitosApi.adjuntarCopiaFirmada.
  adjuntarCopiaFirmada: (idEnvio, formData) => api.postForm(`/api/envios/${idEnvio}/remito/copia-firmada`, formData),
};
