-- ============================================================
-- MIGRACIÓN: Impresión de etiquetas de muestra (REQ-ENV-003)
-- ------------------------------------------------------------
-- Registro append-only de cada impresión/reimpresión de etiqueta por
-- muestra. numero_impresion=1 es la impresión original; cualquier valor
-- mayor es una reimpresión. Los datos descriptivos de la etiqueta (código,
-- material, IR/lote, fecha de muestreo, muestreador) no se duplican acá:
-- se resuelven por JOIN contra lims_muestras/lims_usuarios al leer.
--
-- Ejecutar en la BD LIMSS (SQL Server Management Studio)
-- ============================================================

USE [LIMSS];
GO

IF NOT EXISTS (SELECT 1 FROM sys.tables WHERE name = 'lims_etiquetas')
BEGIN
    CREATE TABLE lims_etiquetas (
        id_etiqueta      INT IDENTITY(1,1)   PRIMARY KEY,
        id_muestra       INT                 NOT NULL REFERENCES lims_muestras(id_muestra),
        numero_impresion INT                 NOT NULL,
        id_usuario       INT                 NOT NULL REFERENCES lims_usuarios(id_usuario),
        fecha_hora       DATETIME            NOT NULL DEFAULT GETDATE()
    );
    CREATE INDEX ix_etiquetas_muestra ON lims_etiquetas(id_muestra, numero_impresion);
    PRINT 'Tabla lims_etiquetas creada OK';
END
GO
