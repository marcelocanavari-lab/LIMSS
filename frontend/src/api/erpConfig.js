import { api } from './client';

export const erpConfigApi = {
  listar: () => api.get('/api/erp-config'),
  actualizar: (id, data) => api.put(`/api/erp-config/${id}`, data),

  // Subartículos que requieren muestreo (consultados por el agente de
  // detección automática de IR -- ver app/services/agente_muestreo.py).
  // El listado es el catálogo GIT59SAR del ERP combinado con el estado de
  // configuración en LIMSS; el guardado es un upsert por CODSAR (no por id).
  listarSubarticulos: () => api.get('/api/erp-config/subarticulos'),
  guardarSubarticulo: (erpCodsar, data) =>
    api.put(`/api/erp-config/subarticulos/${encodeURIComponent(erpCodsar)}`, data),
};
