import { api } from './client';

export const auditoriaApi = {
  listar: ({ fechaDesde, fechaHasta, idUsuario, accion, limite = 100, offset = 0 } = {}) => {
    const params = new URLSearchParams();
    if (fechaDesde) params.set('fecha_desde', fechaDesde);
    if (fechaHasta) params.set('fecha_hasta', fechaHasta);
    if (idUsuario) params.set('id_usuario', idUsuario);
    if (accion) params.set('accion', accion);
    params.set('limite', limite);
    params.set('offset', offset);
    return api.get(`/api/auditoria?${params.toString()}`);
  },
  listarUsuarios: () => api.get('/api/auditoria/usuarios'),
};
