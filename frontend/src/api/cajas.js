import { api } from './client';

export const cajasApi = {
  proximoCodigo: () => api.get('/api/cajas/proximo-codigo'),
  listar: (estado) => {
    const params = new URLSearchParams();
    if (estado) params.set('estado', estado);
    return api.get(`/api/cajas?${params.toString()}`);
  },
  crear: (data) => api.post('/api/cajas', data),
  cerrar: (idCaja) => api.post(`/api/cajas/${idCaja}/cerrar`),
  reabrir: (idCaja) => api.post(`/api/cajas/${idCaja}/reabrir`),
  detalle: (idCaja, historial = false) => api.get(`/api/cajas/${idCaja}?historial=${historial}`),

  // Contramuestras libres (sin caja activa) que se pueden agregar -- la
  // pantalla las muestra directamente en vez de un buscador, "buscar" solo
  // acota la lista cuando es larga.
  muestrasDisponibles: (buscar = '') => api.get(`/api/cajas/muestras-disponibles?buscar=${encodeURIComponent(buscar)}`),
  agregarMuestras: (idCaja, idMuestras) => api.post(`/api/cajas/${idCaja}/muestras`, { id_muestras: idMuestras }),
  retirarMuestra: (idCaja, idMuestra) => api.post(`/api/cajas/${idCaja}/muestras/${idMuestra}/retirar`),

  buscarPorProducto: (buscar) => api.get(`/api/cajas/reportes/por-producto?buscar=${encodeURIComponent(buscar)}`),

  // Etiquetas A4 (PDF, requiere auth -- se abren con abrirPdfConAuth) --
  // una página por caja, ver app/services/pdf_caja.py.
  etiquetaUrl: (idCaja) => `/api/cajas/${idCaja}/etiqueta`,
  etiquetasUrl: (idCajas) => {
    const params = new URLSearchParams();
    idCajas.forEach((id) => params.append('id_cajas', id));
    return `/api/cajas/etiquetas?${params.toString()}`;
  },
};
