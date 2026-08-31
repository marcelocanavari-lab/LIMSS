-- ============================================================
-- MIGRACIÓN: cantidad configurable de etiquetas complementarias de Aprobado
-- ------------------------------------------------------------
-- Reemplaza al diseño anterior (checkbox sí/no, columna
-- requiere_etiqueta_complementaria BIT) por una cantidad configurable por
-- especificación: 0 (default) = no necesita ninguna, un número mayor
-- indica cuántas etiquetas complementarias imprimir junto con la etiqueta
-- principal de Aprobado (ver POST /api/muestras/{id}/imprimir-aprobado).
--
-- requiere_etiqueta_complementaria (si esta base llegó a tener esa
-- columna, de la iteración anterior de esta misma funcionalidad) queda
-- sin uso -- no se migra ni se borra acá, a propósito.
--
-- Idempotente (igual que el resto de backend/*.sql).
--
-- Ejecutar en la BD LIMSS_DEV (SQL Server Management Studio)
-- ============================================================

USE [LIMSS_DEV];
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.columns WHERE object_id = OBJECT_ID('lims_especificaciones') AND name = 'cantidad_etiquetas_complementarias'
)
BEGIN
    ALTER TABLE lims_especificaciones
        ADD cantidad_etiquetas_complementarias INT NOT NULL CONSTRAINT DF_lims_especificaciones_cant_etiq_compl DEFAULT (0);
    PRINT 'Columna cantidad_etiquetas_complementarias agregada a lims_especificaciones';
END
GO
