import { api } from './client';

export const facturasApi = {
  listarFacturas: ({ idLaboratorio, estadoPago, fechaDesde, fechaHasta } = {}) => {
    const params = new URLSearchParams();
    if (idLaboratorio) params.set('id_laboratorio', idLaboratorio);
    if (estadoPago) params.set('estado_pago', estadoPago);
    if (fechaDesde) params.set('fecha_desde', fechaDesde);
    if (fechaHasta) params.set('fecha_hasta', fechaHasta);
    return api.get(`/api/facturas?${params.toString()}`);
  },
  crearFactura: (data) => api.post('/api/facturas', data),
  obtenerFactura: (id) => api.get(`/api/facturas/${id}`),
  editarFactura: (id, data) => api.put(`/api/facturas/${id}`, data),
  registrarPago: (id, data) => api.put(`/api/facturas/${id}/pago`, data),
  anularFactura: (id, data) => api.put(`/api/facturas/${id}/anular`, data),
  enviosSinFacturar: (idLaboratorio) => api.get(`/api/muestras/laboratorios/${idLaboratorio}/envios-sin-facturar`),
};
