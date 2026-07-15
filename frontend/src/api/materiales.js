import { api } from './client';

export const materialesApi = {
  buscarMateriales: (tipo, buscar = '') => {
    const params = new URLSearchParams();
    params.set('tipo', tipo);
    if (buscar) params.set('buscar', buscar);
    return api.get(`/api/materiales/?${params.toString()}`);
  },
};
