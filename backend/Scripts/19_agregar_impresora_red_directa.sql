/* =====================================================================
   Soporte para impresoras conectadas directo por LAN (IP propia),
   ademas de las compartidas por USB desde una PC
   Generado: 2026-08-20

   IMPORTANTE: correr a mano en SSMS con una cuenta con permisos DDL.
   ===================================================================== */

USE LIMSS;
GO

IF COL_LENGTH('dbo.lims_impresoras_etiquetas', 'tipo_conexion') IS NULL
    ALTER TABLE dbo.lims_impresoras_etiquetas
        ADD tipo_conexion VARCHAR(20) NOT NULL DEFAULT 'compartida';
        -- 'compartida' (USB compartida desde una PC, via ruta_red \\PC\Impresora -- como hoy)
        -- 'red_directa' (impresora con IP propia en la red, conexion por socket)

IF COL_LENGTH('dbo.lims_impresoras_etiquetas', 'ip_directa') IS NULL
    ALTER TABLE dbo.lims_impresoras_etiquetas ADD ip_directa VARCHAR(50) NULL;

IF COL_LENGTH('dbo.lims_impresoras_etiquetas', 'puerto_directo') IS NULL
    ALTER TABLE dbo.lims_impresoras_etiquetas ADD puerto_directo INT NOT NULL DEFAULT 9100;
GO

-- ruta_red pasa a ser opcional (ya no todas las impresoras la usan)
IF COL_LENGTH('dbo.lims_impresoras_etiquetas', 'ruta_red') IS NOT NULL
BEGIN
    DECLARE @sql NVARCHAR(MAX) = (
        SELECT 'ALTER TABLE dbo.lims_impresoras_etiquetas ALTER COLUMN ruta_red VARCHAR(200) NULL;'
    );
    EXEC sp_executesql @sql;
END
GO

-- Verificacion
SELECT nombre, modelo, tipo_conexion, ruta_red, ip_directa, puerto_directo
FROM dbo.lims_impresoras_etiquetas;
