-- ============================================================
-- MIGRACIÓN: muestras confirmadas por el muestreador en una Solicitud de
-- Muestreo
-- ------------------------------------------------------------
-- Cada fila vincula una solicitud con una de las muestras definidas en
-- lims_especificacion_muestras (ver migración de esa tabla), guardando la
-- cantidad real usada y si el muestreador la confirmó o no al ejecutar el
-- muestreo. GET .../etiquetas genera una etiqueta por cada fila con
-- confirmada = 1.
--
-- Idempotente (igual que el resto de backend/*.sql).
--
-- Ejecutar en la BD LIMSS (SQL Server Management Studio)
-- ============================================================

USE [LIMSS];
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.tables WHERE name = 'lims_solicitud_muestras'
)
BEGIN
    CREATE TABLE lims_solicitud_muestras (
        id                      INT IDENTITY(1,1) PRIMARY KEY,
        id_solicitud            INT NOT NULL
                                REFERENCES lims_solicitudes_muestreo(id_solicitud),
        id_espec_muestra        INT NOT NULL
                                REFERENCES lims_especificacion_muestras(id),
        cantidad_real           DECIMAL(10,4) NOT NULL,
        confirmada              BIT NOT NULL DEFAULT 1
    );
    PRINT 'Tabla lims_solicitud_muestras creada';
END
GO
