/* =====================================================================
   Mover la comparacion de etiquetas de "por ensayo" a "por envio"
   Generado: 2026-08-14

   Hoy imagen_comparacion_path/observacion_ia estan en lims_resultados
   (una fila por ensayo) -- pero la foto de la etiqueta y su
   comparacion contra la referencia son UNA sola cosa por envio, no una
   por cada ensayo (texto legal, colores, codigo de barras, etc.
   comparten la misma foto). Se mueven las columnas a lims_envios.

   Las columnas viejas en lims_resultados NO se borran (por si quedo
   algo cargado de las pruebas) -- simplemente dejan de usarse en el
   flujo nuevo. No hace falta migrar datos existentes de prueba.

   IMPORTANTE: correr a mano en SSMS con una cuenta con permisos DDL.
   ===================================================================== */

USE LIMSS;
GO

IF COL_LENGTH('dbo.lims_envios', 'imagen_comparacion_path') IS NULL
    ALTER TABLE dbo.lims_envios ADD imagen_comparacion_path VARCHAR(300) NULL;

IF COL_LENGTH('dbo.lims_envios', 'observacion_ia') IS NULL
    ALTER TABLE dbo.lims_envios ADD observacion_ia NVARCHAR(2000) NULL;
GO

-- Verificacion
SELECT id_envio, imagen_comparacion_path, observacion_ia FROM dbo.lims_envios WHERE imagen_comparacion_path IS NOT NULL;
