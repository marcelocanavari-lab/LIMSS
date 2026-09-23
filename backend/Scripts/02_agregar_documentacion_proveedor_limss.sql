/* =====================================================================
   Documentacion del proveedor (remito y/o factura) en Solicitudes de Muestreo
   Generado: 2026-08-11

   A diferencia del protocolo del proveedor (obligatorio para generar la
   solicitud), esta es opcional al momento de crear la solicitud, pero
   se puede adjuntar despues editando la solicitud ya creada. Un solo
   archivo (remito y factura combinados en un mismo PDF o foto).

   IMPORTANTE: correr a mano en SSMS con una cuenta con permisos DDL.
   ===================================================================== */

USE LIMSS;
GO

IF COL_LENGTH('dbo.lims_solicitudes_muestreo', 'documentacion_proveedor_path') IS NULL
    ALTER TABLE dbo.lims_solicitudes_muestreo
        ADD documentacion_proveedor_path VARCHAR(300) NULL;

IF COL_LENGTH('dbo.lims_solicitudes_muestreo', 'documentacion_proveedor_nombre_original') IS NULL
    ALTER TABLE dbo.lims_solicitudes_muestreo
        ADD documentacion_proveedor_nombre_original VARCHAR(200) NULL;
GO

-- Verificacion
SELECT id_solicitud, nro_solicitud, documentacion_proveedor_path, documentacion_proveedor_nombre_original
FROM dbo.lims_solicitudes_muestreo
ORDER BY id_solicitud DESC;
