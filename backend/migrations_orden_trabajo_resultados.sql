-- ============================================================
-- MIGRACIÓN: modelo correcto de resultados de Orden de Trabajo
-- ------------------------------------------------------------
-- La Orden de Trabajo (análisis interno, ver Solicitud de Muestreo) NO
-- tiene dictamen propio -- sus resultados se integran al dictamen general
-- de la MUESTRA (lims_muestras), igual que los resultados de envíos
-- externos (lims_resultados). Por eso:
--   1. Se elimina lims_orden_trabajo_dictamen si llegó a crearse (nunca se
--      llegó a usar desde el código -- no hay datos que perder).
--   2. Se crea lims_orden_trabajo_resultados, análoga a lims_resultados
--      pero vinculada a lims_solicitudes_muestreo (no a lims_envios):
--      cada ensayo de la especificación/laboratorio de la solicitud tiene
--      a lo sumo un resultado.
--
-- Idempotente (igual que el resto de backend/*.sql).
--
-- Ejecutar en la BD LIMSS (SQL Server Management Studio)
-- ============================================================

USE [LIMSS];
GO

IF EXISTS (SELECT 1 FROM sys.tables WHERE name = 'lims_orden_trabajo_dictamen')
BEGIN
    DROP TABLE lims_orden_trabajo_dictamen;
    PRINT 'Tabla lims_orden_trabajo_dictamen eliminada';
END
GO

IF NOT EXISTS (SELECT 1 FROM sys.tables WHERE name = 'lims_orden_trabajo_resultados')
BEGIN
    CREATE TABLE lims_orden_trabajo_resultados (
        id_resultado            INT IDENTITY(1,1)   PRIMARY KEY,
        id_solicitud            INT                 NOT NULL REFERENCES lims_solicitudes_muestreo(id_solicitud),
        id_espec_ensayo         INT                 NOT NULL REFERENCES lims_especificacion_ensayos(id_espec_ensayo),
        valor_numerico          DECIMAL(18,4)       NULL,
        valor_cualitativo       VARCHAR(50)         NULL,
        dentro_especificacion   BIT                 NULL,
        id_usuario_carga        INT                 NOT NULL REFERENCES lims_usuarios(id_usuario),
        fecha_carga             DATETIME            NOT NULL DEFAULT GETDATE(),
        CONSTRAINT uq_ot_resultado_solicitud_ensayo UNIQUE (id_solicitud, id_espec_ensayo)
    );
    PRINT 'Tabla lims_orden_trabajo_resultados creada';
END
GO
