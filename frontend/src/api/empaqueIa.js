import { api } from './client';

export const empaqueIaApi = {
  obtenerReferencia: (erpCodart) => api.get(`/api/empaque-referencia/${encodeURIComponent(erpCodart)}`),
  imagenReferenciaBlob: (erpCodart) => api.getBlob(`/api/empaque-referencia/${encodeURIComponent(erpCodart)}/imagen`),
  subirReferencia: (erpCodart, archivo) => {
    const formData = new FormData();
    formData.append('erp_CODART', erpCodart);
    formData.append('imagen', archivo);
    return api.postForm('/api/empaque-referencia', formData);
  },
  // Una sola comparación por ENVÍO (no por ensayo) -- varios ensayos de un
  // mismo envío se verifican todos contra la misma foto de etiqueta.
  compararEtiqueta: (idEnvio, archivo) => {
    const formData = new FormData();
    formData.append('imagen', archivo);
    return api.postForm(`/api/envios/${idEnvio}/comparar-etiqueta`, formData);
  },
};
