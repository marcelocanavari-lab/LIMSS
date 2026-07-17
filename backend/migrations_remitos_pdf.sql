-- ============================================================
-- MIGRACIÓN: Remito de envío en PDF (REQ-ENV-004)
-- ------------------------------------------------------------
-- Documento PDF formal del remito, con numeración interna propia
-- (REM-YYYY-NNNN) -- distinta del número de remito/guía externo del
-- transportista, que ya se registra en lims_envios.nro_remito
-- (REQ-ENV-005). Append-only: "generar" siempre crea un documento nuevo,
-- nunca se sobrescribe uno existente (si se corrige algo, se reimprime).
--
-- Ejecutar en la BD LIMSS (SQL Server Management Studio)
-- ============================================================

USE [LIMSS];
GO

IF NOT EXISTS (SELECT 1 FROM sys.tables WHERE name = 'lims_remitos')
BEGIN
    CREATE TABLE lims_remitos (
        id_remito           INT IDENTITY(1,1)   PRIMARY KEY,
        id_envio            INT                 NOT NULL REFERENCES lims_envios(id_envio),
        nro_remito_interno  VARCHAR(20)         NOT NULL UNIQUE,
        pdf_path            VARCHAR(300)        NOT NULL,
        id_usuario_genera   INT                 NOT NULL REFERENCES lims_usuarios(id_usuario),
        fecha_generacion    DATETIME            NOT NULL DEFAULT GETDATE()
    );
    CREATE INDEX ix_remitos_envio ON lims_remitos(id_envio, fecha_generacion);
    PRINT 'Tabla lims_remitos creada OK';
END
GO
