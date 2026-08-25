-- ============================================================
-- MIGRACIÓN: grupos de bultos de una Solicitud de Muestreo
-- ------------------------------------------------------------
-- Hasta ahora una solicitud solo tenía un N° de bultos único
-- (lims_solicitudes_muestreo.nro_bultos), todos con la misma cantidad. Esta
-- tabla permite desglosarlo en grupos desiguales (ej. "4 x 50 kg" + "1 x 30
-- kg"), cada uno con su propia cantidad_bultos x cantidad_unidades -- ver
-- BultoGrupoInput/BultoGrupoResponse en app/schemas/solicitudes_muestreo.py
-- y app/services/bultos.py (expandir_bultos combina los grupos en un
-- listado continuo de bultos individuales para imprimir las etiquetas
-- CUARENTENA/APROBADO/RECHAZADO).
--
-- Solicitudes sin filas acá (caso legacy, o solicitudes que no cargaron
-- grupos) siguen usando el N° de bultos único de siempre -- ver el fallback
-- en expandir_bultos, no rompe nada existente.
--
-- Idempotente (igual que el resto de backend/*.sql).
--
-- Ejecutar en la BD LIMSS_DEV (SQL Server Management Studio) -- LIMSS_DEV
-- es una copia independiente de LIMSS para desarrollo, no tocar producción.
-- ============================================================

USE [LIMSS_DEV];
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.tables WHERE name = 'lims_solicitud_bultos'
)
BEGIN
    CREATE TABLE lims_solicitud_bultos (
        id_bulto_grupo      INT IDENTITY(1,1)  PRIMARY KEY,
        id_solicitud        INT                 NOT NULL
                             REFERENCES lims_solicitudes_muestreo(id_solicitud),
        cantidad_bultos      INT                 NOT NULL,
        cantidad_unidades    DECIMAL(10,4)       NULL,
        unidad_medida        VARCHAR(20)         NULL,
        orden                INT                 NOT NULL DEFAULT 0
    );
    PRINT 'Tabla lims_solicitud_bultos creada';
END
GO
