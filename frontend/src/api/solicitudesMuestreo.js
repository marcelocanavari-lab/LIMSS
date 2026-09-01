import { api } from './client';

export const solicitudesMuestreoApi = {
  listar: ({ estado, idMuestreador } = {}) => {
    const params = new URLSearchParams();
    if (estado) params.set('estado', estado);
    if (idMuestreador) params.set('id_muestreador', idMuestreador);
    return api.get(`/api/solicitudes-muestreo?${params.toString()}`);
  },
  misSolicitudes: () => api.get('/api/solicitudes-muestreo/mis-solicitudes'),
  listarMuestreadores: () => api.get('/api/solicitudes-muestreo/muestreadores'),
  listarUsuariosActivos: () => api.get('/api/solicitudes-muestreo/usuarios-activos'),
  crear: (data, protocoloProveedor, documentacionProveedor) => {
    const formData = new FormData();
    formData.append('datos', JSON.stringify(data));
    formData.append('protocolo_proveedor', protocoloProveedor);
    // Opcional -- a diferencia del protocolo, se puede omitir y adjuntar después.
    if (documentacionProveedor) formData.append('documentacion_proveedor', documentacionProveedor);
    return api.postForm('/api/solicitudes-muestreo', formData);
  },
  obtener: (id) => api.get(`/api/solicitudes-muestreo/${id}`),
  anular: (id, motivo) => api.put(`/api/solicitudes-muestreo/${id}/anular`, { motivo }),

  // Completa laboratorio, muestreador y/o los datos manuales del ingreso
  // (lote, país de origen, fecha de reanálisis, bultos, metodología,
  // fabricante) de una solicitud pendiente que quedó sin alguno -- pensado
  // para las que generó el agente (origen='agente', ver AgenteMuestreoPage),
  // que no puede resolverlos solo con el ERP. El protocolo y la
  // documentación del proveedor se completan aparte, por archivo (ver
  // subirProtocoloProveedor/subirDocumentacionProveedor).
  completarDatos: (id, data) => api.put(`/api/solicitudes-muestreo/${id}/completar-datos`, data),

  // Protocolo del proveedor (foto o PDF) -- obligatorio en el alta manual
  // desde el momento de crear la solicitud (ver crear), pero las que genera
  // el agente no lo tienen disponible en ese flujo automático. `motivo`
  // opcional -- cuando este reemplazo es parte de "Corregir datos de
  // recepción" (ver corregirRecepcion), va con el mismo motivo al audit
  // trail que el resto de esa corrección.
  subirProtocoloProveedor: (id, archivo, motivo) => {
    const formData = new FormData();
    formData.append('protocolo_proveedor', archivo);
    if (motivo) formData.append('motivo', motivo);
    return api.postForm(`/api/solicitudes-muestreo/${id}/protocolo-proveedor`, formData);
  },

  // Documentación del proveedor (remito y/o factura, un solo archivo) --
  // opcional, se puede adjuntar en la creación (ver crear) o después.
  subirDocumentacionProveedor: (id, archivo, motivo) => {
    const formData = new FormData();
    formData.append('documentacion_proveedor', archivo);
    if (motivo) formData.append('motivo', motivo);
    return api.postForm(`/api/solicitudes-muestreo/${id}/documentacion-proveedor`, formData);
  },

  // Corrección puntual, post-ejecución, de bultos + datos de recepción del
  // proveedor -- excepción controlada a la regla de "ejecutada = bloqueada
  // para edición", solo QA/Admin (ver corregir_recepcion en el backend).
  // Motivo obligatorio.
  corregirRecepcion: (id, data) => api.put(`/api/solicitudes-muestreo/${id}/corregir-recepcion`, data),

  // Genera el envío antes de ejecutar el muestreo físico: crea la muestra
  // por adelantado (datos_muestreo_pendientes=true) para poder seguir con
  // el flujo normal de Envío de Muestras sin esperar al muestreador.
  generarEnvioAnticipado: (id) => api.post(`/api/solicitudes-muestreo/${id}/generar-envio-anticipado`),

  // Orden de Trabajo digital (Etapa 2: el muestreador ejecuta) -- Sección A
  // (datos físicos) + Sección B (resultados de ensayos del laboratorio de
  // la solicitud).
  obtenerEnsayosParaOrden: (id) => api.get(`/api/solicitudes-muestreo/${id}/ensayos-para-orden`),
  confirmarOrdenTrabajo: (id, body) => api.post(`/api/solicitudes-muestreo/${id}/orden-trabajo-digital`, body),

  // Etiquetas CUARENTENA -- una por bulto (nro_bultos), impresión directa SATO.
  // desdeBulto/hastaBulto opcionales -- reimpresión parcial por pérdida o
  // rotura de uno o pocos bultos (sin ambos, se imprime el rango completo,
  // igual que siempre).
  imprimirCuarentena: (id, idImpresora, desdeBulto, hastaBulto) =>
    api.post(`/api/solicitudes-muestreo/${id}/imprimir-cuarentena`, {
      id_impresora: idImpresora, desde_bulto: desdeBulto || undefined, hasta_bulto: hastaBulto || undefined,
    }),

  // Etiquetas de MUESTRA por SATO para una solicitud TODAVÍA PENDIENTE (sin
  // id_muestra real) -- misma fuente de datos que "Etiquetas (PDF)" para
  // ese mismo caso (ver _armar_etiquetas_logicas_de_solicitud en el
  // backend). Para una solicitud ya ejecutada, se sigue usando
  // muestrasApi.imprimirDirecto/contarEtiquetas con el id_muestra real.
  imprimirDirecto: (id, idImpresora) =>
    api.post(`/api/solicitudes-muestreo/${id}/imprimir-directo`, { id_impresora: idImpresora }),
  contarEtiquetas: (id) => api.get(`/api/solicitudes-muestreo/${id}/etiquetas-cantidad`),
};
