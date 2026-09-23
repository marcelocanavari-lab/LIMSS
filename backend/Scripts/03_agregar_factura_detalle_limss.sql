/* =====================================================================
   Detalle de facturas por ensayo (LIMSS)
   Generado: 2026-08-09

   Hoy lims_factura_envios vincula una factura con los envios que cubre,
   pero sin desglose de importe por ensayo. Una factura puede incluir
   varios remitos (envios), y cada envio puede tener varios ensayos
   solicitados (lims_envio_ensayos ya modela esa relacion envio->ensayo).

   Se agrega lims_factura_detalle, que cuelga directamente de
   lims_envio_ensayos.id (no de id_envio + id_espec_ensayo por separado)
   porque esa fila ya identifica de forma unica "este ensayo, en este
   envio". Con eso una factura queda con un importe por cada
   combinacion factura + envio + ensayo.

   lims_factura_envios se mantiene sin cambios (compatibilidad con lo
   existente); lims_factura_detalle es la fuente de verdad nueva para
   el desglose. El total de una factura (lims_facturas.monto) deberia
   idealmente coincidir con la suma de sus lims_factura_detalle.importe,
   pero esa validacion queda a cargo de la aplicacion, no de la base
   (para no bloquear por redondeos o ajustes puntuales).

   IMPORTANTE: correr a mano en SSMS con una cuenta con permisos DDL.
   ===================================================================== */

USE LIMSS;
GO

IF OBJECT_ID('dbo.lims_factura_detalle', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.lims_factura_detalle (
        id                INT IDENTITY(1,1) PRIMARY KEY,
        id_factura        INT NOT NULL,
        id_envio_ensayo   INT NOT NULL,
        importe           DECIMAL(12,2) NOT NULL,
        observaciones     VARCHAR(200) NULL,
        CONSTRAINT FK_factura_detalle_factura
            FOREIGN KEY (id_factura) REFERENCES dbo.lims_facturas(id_factura),
        CONSTRAINT FK_factura_detalle_envio_ensayo
            FOREIGN KEY (id_envio_ensayo) REFERENCES dbo.lims_envio_ensayos(id),
        -- Un mismo ensayo de un mismo envio no puede facturarse dos veces
        -- DENTRO de la misma factura.
        CONSTRAINT UQ_factura_detalle UNIQUE (id_factura, id_envio_ensayo)
    );
END
GO

-- Indices para el reporte de importes facturados (filtros por factura,
-- y por ensayo via envio_ensayo)
IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE name = 'IX_factura_detalle_factura'
      AND object_id = OBJECT_ID('dbo.lims_factura_detalle')
)
    CREATE INDEX IX_factura_detalle_factura ON dbo.lims_factura_detalle (id_factura);

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE name = 'IX_factura_detalle_envio_ensayo'
      AND object_id = OBJECT_ID('dbo.lims_factura_detalle')
)
    CREATE INDEX IX_factura_detalle_envio_ensayo ON dbo.lims_factura_detalle (id_envio_ensayo);
GO

-- Verificacion
SELECT * FROM dbo.lims_factura_detalle;
