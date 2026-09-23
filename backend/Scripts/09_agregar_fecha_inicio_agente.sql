/* =====================================================================
   Fecha de inicio para el agente de muestreo
   Generado: 2026-08-12

   El agente no debe procesar IRs anteriores a esta fecha, aunque su
   N01Id sea mayor a la marca de agua (que arranca en 0). Sin este
   corte, la primera corrida evalua TODO el historial de comprobantes
   IR que existio alguna vez.
   ===================================================================== */

USE LIMSS;
GO

IF NOT EXISTS (SELECT 1 FROM dbo.lims_erp_config WHERE clave = 'agente_muestreo_fecha_inicio')
    INSERT INTO dbo.lims_erp_config (clave, valor, descripcion, editable, fecha_modificacion)
    VALUES ('agente_muestreo_fecha_inicio', '2026-08-01',
            'El agente ignora comprobantes IR con FECCOR anterior a esta fecha (evita procesar el historial completo)',
            1, GETDATE());
GO

SELECT * FROM dbo.lims_erp_config WHERE clave = 'agente_muestreo_fecha_inicio';
