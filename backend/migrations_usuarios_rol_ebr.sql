-- ============================================================
-- MIGRACIÓN: lims_usuarios.rol_ebr / lims_usuarios.activo_ebr
-- ------------------------------------------------------------
-- El LIMSS pasa a ser el punto único de administración de usuarios
-- para ambos sistemas (LIMSS y eBR). Se agregan dos columnas a
-- lims_usuarios para guardar el rol que ese usuario tiene en el eBR
-- (independiente de su rol en LIMSS) y si su acceso al eBR está
-- activo. rol_ebr NULL significa "sin acceso al eBR".
--
-- Idempotente (igual que el resto de backend/*.sql).
--
-- Ejecutar en la BD LIMSS (SQL Server Management Studio)
-- ============================================================

USE [LIMSS];
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.columns WHERE object_id = OBJECT_ID('lims_usuarios') AND name = 'rol_ebr'
)
BEGIN
    ALTER TABLE lims_usuarios ADD rol_ebr VARCHAR(20) NULL;
    PRINT 'Columna lims_usuarios.rol_ebr agregada';
END
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.check_constraints WHERE name = 'CK_lims_usuarios_rol_ebr'
)
BEGIN
    ALTER TABLE lims_usuarios
        ADD CONSTRAINT CK_lims_usuarios_rol_ebr
        CHECK (rol_ebr IN ('operario', 'supervisor', 'qa', 'admin'));
    PRINT 'CHECK CK_lims_usuarios_rol_ebr agregado';
END
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.columns WHERE object_id = OBJECT_ID('lims_usuarios') AND name = 'activo_ebr'
)
BEGIN
    ALTER TABLE lims_usuarios ADD activo_ebr BIT NOT NULL DEFAULT 0;
    PRINT 'Columna lims_usuarios.activo_ebr agregada';
END
GO
