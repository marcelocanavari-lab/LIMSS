-- ============================================================
-- MIGRACIÓN: desglose de importe por ensayo dentro de una factura
-- ------------------------------------------------------------
-- lims_factura_detalle guarda, por cada ensayo de un envío incluido en una
-- factura, el importe que le corresponde. id_envio_ensayo referencia a
-- lims_envio_ensayos(id) -- esa es la PK real de esa tabla (no tiene una
-- columna llamada id_envio_ensayo, la que se llama así es esta FK).
--
-- UNIQUE (id_factura, id_envio_ensayo): un mismo ensayo de un mismo envío no
-- se puede cargar dos veces dentro de la misma factura. Esto es un nivel de
-- detalle adicional DENTRO de una factura -- no cambia ni reemplaza
-- lims_factura_envios ni la regla de que un envío no se factura dos veces.
--
-- Idempotente: si la tabla ya existe, no hace nada.
--
-- Ejecutar en la BD LIMSS (SQL Server Management Studio)
-- ============================================================

USE [LIMSS];
GO

IF OBJECT_ID('lims_factura_detalle', 'U') IS NULL
BEGIN
    CREATE TABLE lims_factura_detalle (
        id              INT IDENTITY(1,1) PRIMARY KEY,
        id_factura      INT NOT NULL REFERENCES lims_facturas(id_factura),
        id_envio_ensayo INT NOT NULL REFERENCES lims_envio_ensayos(id),
        importe         DECIMAL(12,2) NOT NULL DEFAULT 0,
        observaciones   VARCHAR(200) NULL,
        CONSTRAINT uq_factura_envio_ensayo UNIQUE (id_factura, id_envio_ensayo)
    );
    PRINT 'Tabla lims_factura_detalle creada';
END
GO
