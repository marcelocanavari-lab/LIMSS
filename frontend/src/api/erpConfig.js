import { api } from './client';

export const erpConfigApi = {
  listar: () => api.get('/api/erp-config'),
  actualizar: (id, data) => api.put(`/api/erp-config/${id}`, data),
};
