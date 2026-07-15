-- ============================================================
-- MIGRACIÓN: tipo_material admite 'semi_elaborado'
-- ------------------------------------------------------------
-- El ERP distingue Granel (GIT59SAR.CODSAR='0002') de Semi-Elaborado
-- (CODSAR='0003') como categorías propias. lims_especificaciones.tipo_material
-- solo aceptaba ('materia_prima','granel','producto_terminado'); se agrega
-- 'semi_elaborado' como cuarto valor válido.
--
-- La restricción original se creó sin nombre explícito (SQL Server le asignó
-- uno autogenerado tipo CK__lims_espe__...), así que hay que ubicarla
-- dinámicamente antes de reemplazarla. Idempotente: si la restricción nueva
-- (con nombre fijo) ya existe, no hace nada.
--
-- Ejecutar en la BD LIMSS (SQL Server Management Studio)
-- ============================================================

USE [LIMSS];
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.check_constraints WHERE name = 'CK_lims_especificaciones_tipo_material'
)
BEGIN
    DECLARE @constraint_name NVARCHAR(200);
    SELECT @constraint_name = cc.name
    FROM sys.check_constraints cc
    INNER JOIN sys.columns col
        ON col.object_id = cc.parent_object_id AND col.column_id = cc.parent_column_id
    WHERE cc.parent_object_id = OBJECT_ID('lims_especificaciones') AND col.name = 'tipo_material';

    IF @constraint_name IS NOT NULL
    BEGIN
        EXEC('ALTER TABLE lims_especificaciones DROP CONSTRAINT [' + @constraint_name + ']');
        PRINT 'Restricción CHECK anterior de tipo_material eliminada: ' + @constraint_name;
    END

    ALTER TABLE lims_especificaciones
        ADD CONSTRAINT CK_lims_especificaciones_tipo_material
        CHECK (tipo_material IN ('materia_prima','granel','semi_elaborado','producto_terminado'));
    PRINT 'Restricción CHECK de tipo_material actualizada (agregado semi_elaborado)';
END
GO
