/* =====================================================================
   Cambio de PIN propio + cambio obligatorio (LIMSS)
   Generado: 2026-08-10
   ===================================================================== */

USE LIMSS;
GO

IF COL_LENGTH('dbo.lims_usuarios', 'debe_cambiar_pin') IS NULL
    ALTER TABLE dbo.lims_usuarios ADD debe_cambiar_pin BIT NOT NULL DEFAULT 0;
GO

SELECT id_usuario, codigo, nombre, apellido, debe_cambiar_pin FROM dbo.lims_usuarios;
