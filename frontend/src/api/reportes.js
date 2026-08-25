import { api } from './client';

function paramsFecha({ fechaDesde, fechaHasta } = {}) {
  const params = new URLSearchParams();
  if (fechaDesde) params.set('fecha_desde', fechaDesde);
  if (fechaHasta) params.set('fecha_hasta', fechaHasta);
  return params;
}

export const reportesApi = {
  libroIngresos: (filtro) => api.get(`/api/reportes/libro-ingresos?${paramsFecha(filtro).toString()}`),
  libroIngresosExportarPath: (filtro) => `/api/reportes/libro-ingresos/exportar?${paramsFecha(filtro).toString()}`,
};
