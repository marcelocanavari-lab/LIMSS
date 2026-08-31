import { api } from './client';

export const muestrasApi = {
  // ERP: búsqueda de IR
  buscarIR: (nroIr) => api.get(`/api/muestras/erp/ir/${encodeURIComponent(nroIr)}`),

  // Búsqueda unificada por tipo de material: IR (materia prima) o número de
  // lote (resto) -- ambas contra el ERP, ver buscar_material en el backend
  buscarMaterial: (tipo, referencia) => {
    const params = new URLSearchParams();
    params.set('tipo', tipo);
    params.set('referencia', referencia);
    return api.get(`/api/muestras/buscar-material?${params.toString()}`);
  },

  // Proveedores del ERP (GIM02ANA, IdT04=2) -- buscador para el campo
  // "Proveedor" de la Solicitud de Muestreo, ya no se autocompleta del IR.
  buscarProveedoresErp: (buscar) => api.get(`/api/erp/proveedores?buscar=${encodeURIComponent(buscar)}`),

  // Muestras
  crearMuestra: (data) => api.post('/api/muestras/', data),
  listarMuestras: ({ estado, buscar = '', mio, tipoMaterial, fechaDesde, fechaHasta, idLaboratorio } = {}) => {
    const params = new URLSearchParams();
    if (estado) params.set('estado', estado);
    if (buscar) params.set('buscar', buscar);
    if (mio) params.set('mio', 'true');
    if (tipoMaterial) params.set('tipo_material', tipoMaterial);
    if (fechaDesde) params.set('fecha_desde', fechaDesde);
    if (fechaHasta) params.set('fecha_hasta', fechaHasta);
    if (idLaboratorio) params.set('id_laboratorio', idLaboratorio);
    return api.get(`/api/muestras/?${params.toString()}`);
  },
  pendientesEnvio: ({ buscar = '' } = {}) => {
    const params = new URLSearchParams();
    if (buscar) params.set('buscar', buscar);
    return api.get(`/api/muestras/pendientes-envio?${params.toString()}`);
  },
  obtenerMuestra: (id) => api.get(`/api/muestras/${id}`),
  editarMuestra: (id, data) => api.patch(`/api/muestras/${id}`, data),
  obtenerRecorrido: (id) => api.get(`/api/muestras/${id}/recorrido`),

  // Vincular especificación -- caso real: la muestra se creó antes de que
  // la especificación de su artículo existiera en Datos Maestros, así que
  // quedó con id_especificacion NULL sin ningún mecanismo para reconectarla
  // después (ver especificacion_candidata/vincular_especificacion en el
  // backend).
  especificacionCandidata: (id) => api.get(`/api/muestras/${id}/especificacion-candidata`),
  vincularEspecificacion: (id, idEspecificacion) =>
    api.post(`/api/muestras/${id}/vincular-especificacion`, { id_especificacion: idEspecificacion }),

  // Checklist de muestreo (etapa 'muestreo' de la especificación) -- mismo
  // mecanismo que usa Ejecutar Muestreo, expuesto acá directo por
  // id_muestra para las muestras creadas con Nueva Muestra (sin solicitud).
  obtenerChecklistMuestreo: (id) => api.get(`/api/muestras/${id}/checklist-muestreo`),
  guardarChecklistMuestreo: (id, checklist) => api.post(`/api/muestras/${id}/checklist-muestreo`, checklist),

  // Envíos (una muestra puede tener varios, a distintos laboratorios)
  confirmarEnvio: (id, data) => api.post(`/api/muestras/${id}/envios`, data),
  listarEnvios: (id) => api.get(`/api/muestras/${id}/envios`),
  obtenerRemito: (id, idEnvio) => api.get(`/api/muestras/${id}/envios/${idEnvio}/remito`),
  ensayosParaEnvio: (id, idLaboratorio) => api.get(`/api/muestras/${id}/ensayos-para-envio?id_laboratorio=${idLaboratorio}`),

  // Etiqueta (REQ-ENV-003)
  generarEtiqueta: (id) => api.post(`/api/muestras/${id}/etiqueta`),
  obtenerUltimaEtiqueta: (id) => api.get(`/api/muestras/${id}/etiqueta`),

  // Impresión directa (SATO/SBPL, sin pasar por el PDF)
  imprimirDirecto: (id, idImpresora) => api.post(`/api/muestras/${id}/imprimir-directo`, { id_impresora: idImpresora }),
  // Preview de cantidad ANTES de mandar el trabajo real -- mismo criterio
  // ya usado para CUARENTENA (cantidad conocida de antemano).
  contarEtiquetas: (id) => api.get(`/api/muestras/${id}/etiquetas-cantidad`),
  // Etiquetas APROBADO/RECHAZADO -- el backend bloquea si el dictamen no
  // coincide con el estado de la etiqueta que se quiere imprimir.
  // Si la especificación del artículo tiene cantidad_etiquetas_
  // complementarias > 0, imprimir-aprobado adjunta automáticamente esa
  // cantidad de etiquetas "APROBADO -- COMPLEMENTARIA" al mismo trabajo de
  // impresión -- no hay endpoint aparte para eso.
  imprimirAprobado: (id, idImpresora, cantidad = 1) => api.post(`/api/muestras/${id}/imprimir-aprobado`, { id_impresora: idImpresora, cantidad }),
  imprimirRechazado: (id, idImpresora, cantidad = 1) => api.post(`/api/muestras/${id}/imprimir-rechazado`, { id_impresora: idImpresora, cantidad }),

  // Impresión de Etiquetas (acceso general desde el Dashboard): busca
  // solicitudes/muestras y qué etiquetas corresponden imprimir para cada una.
  buscarParaEtiquetas: (buscar) => api.get(`/api/muestras/buscar-etiquetas?buscar=${encodeURIComponent(buscar)}`),

  // Impresoras de etiquetas
  listarImpresoras: (activa) => {
    const params = new URLSearchParams();
    if (activa !== undefined && activa !== null) params.set('activa', activa);
    return api.get(`/api/muestras/impresoras?${params.toString()}`);
  },
  crearImpresora: (data) => api.post('/api/muestras/impresoras', data),
  editarImpresora: (id, data) => api.put(`/api/muestras/impresoras/${id}`, data),
  cambiarEstadoImpresora: (id, activa) => api.put(`/api/muestras/impresoras/${id}/estado?activa=${activa}`),

  // Laboratorios
  listarLaboratorios: (activo) => {
    const params = new URLSearchParams();
    if (activo !== undefined && activo !== null) params.set('activo', activo);
    return api.get(`/api/muestras/laboratorios?${params.toString()}`);
  },
  crearLaboratorio: (data) => api.post('/api/muestras/laboratorios', data),
  editarLaboratorio: (id, data) => api.put(`/api/muestras/laboratorios/${id}`, data),
  cambiarEstadoLaboratorio: (id, activo) => api.put(`/api/muestras/laboratorios/${id}/estado?activo=${activo}`),

  // Contactos por laboratorio
  listarContactos: (idLaboratorio) => api.get(`/api/muestras/laboratorios/${idLaboratorio}/contactos`),
  crearContacto: (idLaboratorio, data) => api.post(`/api/muestras/laboratorios/${idLaboratorio}/contactos`, data),
  editarContacto: (idLaboratorio, idContacto, data) =>
    api.put(`/api/muestras/laboratorios/${idLaboratorio}/contactos/${idContacto}`, data),
  eliminarContacto: (idLaboratorio, idContacto) =>
    api.del(`/api/muestras/laboratorios/${idLaboratorio}/contactos/${idContacto}`),
};
