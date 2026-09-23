/* =====================================================================
   Protocolo del proveedor en Solicitudes de Muestreo (LIMSS)
   Generado: 2026-08-09

   Al generar una solicitud de muestreo, se debe adjuntar el protocolo
   del proveedor correspondiente al IR (foto o PDF), como requisito
   obligatorio para poder generar la solicitud. Un solo archivo por
   solicitud.

   No confundir con lims_protocolos (protocolo EXTERNO emitido por el
   laboratorio de analisis, ligado a un envio via id_envio) — este es
   el protocolo que el PROVEEDOR entrega junto con el lote, cargado en
   el momento de la solicitud, antes de que exista ningun envio.

   IMPORTANTE: correr a mano en SSMS con una cuenta con permisos DDL.
   ===================================================================== */

USE LIMSS;
GO

IF COL_LENGTH('dbo.lims_solicitudes_muestreo', 'protocolo_proveedor_path') IS NULL
    ALTER TABLE dbo.lims_solicitudes_muestreo
        ADD protocolo_proveedor_path VARCHAR(300) NULL;

IF COL_LENGTH('dbo.lims_solicitudes_muestreo', 'protocolo_proveedor_nombre_original') IS NULL
    ALTER TABLE dbo.lims_solicitudes_muestreo
        ADD protocolo_proveedor_nombre_original VARCHAR(200) NULL;
GO

-- Verificacion
SELECT id_solicitud, nro_solicitud, protocolo_proveedor_path, protocolo_proveedor_nombre_original
FROM dbo.lims_solicitudes_muestreo
ORDER BY id_solicitud DESC;
