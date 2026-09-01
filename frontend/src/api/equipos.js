import { api } from './client';

export const equiposApi = {
  listar: (activo) => {
    const params = new URLSearchParams();
    if (activo !== undefined && activo !== null) params.set('activo', activo);
    return api.get(`/api/equipos?${params.toString()}`);
  },
  crearEquipo: (data) => api.post('/api/equipos', data),
  editarEquipo: (idEquipo, data) => api.put(`/api/equipos/${idEquipo}`, data),

  listarVariables: (idEquipo, activo) => {
    const params = new URLSearchParams();
    if (activo !== undefined && activo !== null) params.set('activo', activo);
    return api.get(`/api/equipos/${idEquipo}/variables?${params.toString()}`);
  },
  crearVariable: (idEquipo, data) => api.post(`/api/equipos/${idEquipo}/variables`, data),
  editarVariable: (idEquipo, idVariable, data) => api.put(`/api/equipos/${idEquipo}/variables/${idVariable}`, data),

  crearLectura: (data) => api.post('/api/equipos/lecturas', data),
  listarLecturas: ({ idEquipo, fechaDesde, fechaHasta, soloFueraDeRango } = {}) => {
    const params = new URLSearchParams();
    if (idEquipo) params.set('id_equipo', idEquipo);
    if (fechaDesde) params.set('fecha_desde', fechaDesde);
    if (fechaHasta) params.set('fecha_hasta', fechaHasta);
    if (soloFueraDeRango) params.set('solo_fuera_de_rango', 'true');
    return api.get(`/api/equipos/lecturas?${params.toString()}`);
  },
  // Reporte de Mediciones -- CSV (Excel) con las 13 variables como
  // columnas fijas, por eso idEquipo es obligatorio acá (a diferencia de
  // listarLecturas).
  exportarLecturasPath: ({ idEquipo, fechaDesde, fechaHasta }) => {
    const params = new URLSearchParams();
    params.set('id_equipo', idEquipo);
    if (fechaDesde) params.set('fecha_desde', fechaDesde);
    if (fechaHasta) params.set('fecha_hasta', fechaHasta);
    return `/api/equipos/lecturas/exportar?${params.toString()}`;
  },
  // Reporte de valores fuera de rango -- CSV con una fila por desviación.
  exportarDesviacionesPath: ({ idEquipo, fechaDesde, fechaHasta, idVariable } = {}) => {
    const params = new URLSearchParams();
    if (idEquipo) params.set('id_equipo', idEquipo);
    if (fechaDesde) params.set('fecha_desde', fechaDesde);
    if (fechaHasta) params.set('fecha_hasta', fechaHasta);
    if (idVariable) params.set('id_variable', idVariable);
    return `/api/equipos/lecturas/exportar-desviaciones?${params.toString()}`;
  },
  // Reporte de Días sin registrar -- días hábiles del rango sin ninguna
  // lectura cargada para el equipo.
  diasSinRegistrar: ({ idEquipo, fechaDesde, fechaHasta }) => {
    const params = new URLSearchParams();
    params.set('id_equipo', idEquipo);
    params.set('fecha_desde', fechaDesde);
    params.set('fecha_hasta', fechaHasta);
    return api.get(`/api/equipos/lecturas/dias-sin-registrar?${params.toString()}`);
  },
};
