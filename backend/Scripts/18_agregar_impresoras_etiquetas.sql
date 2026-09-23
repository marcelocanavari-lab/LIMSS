/* =====================================================================
   Impresoras de etiquetas (SATO) - tabla de configuracion
   Generado: 2026-08-14

   Permite agregar/editar impresoras SATO desde una pantalla en vez de
   hardcodear nombres de red en el codigo. Cada impresora tiene su
   propia ruta de red (compartida desde la PC donde esta conectada por
   USB) y su propio tamano de etiqueta configurable.

   IMPORTANTE: correr a mano en SSMS con una cuenta con permisos DDL.
   ===================================================================== */

USE LIMSS;
GO

IF OBJECT_ID('dbo.lims_impresoras_etiquetas', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.lims_impresoras_etiquetas (
        id_impresora      INT IDENTITY(1,1) PRIMARY KEY,
        nombre             VARCHAR(50) NOT NULL,          -- nombre amigable, ej. "Muestreo - Estacion 1"
        modelo             VARCHAR(20) NOT NULL,            -- 'CG40TT' | 'WS408TT'
        ruta_red           VARCHAR(200) NOT NULL,           -- \\NOMBREPC\NombreCompartido
        resolucion_dpi     INT NOT NULL DEFAULT 203,
        ancho_mm           INT NOT NULL DEFAULT 100,
        alto_mm            INT NOT NULL DEFAULT 85,
        activa             BIT NOT NULL DEFAULT 1,
        id_usuario_carga   INT NOT NULL,
        fecha_carga        DATETIME NOT NULL DEFAULT GETDATE(),
        CONSTRAINT UQ_impresoras_etiquetas_nombre UNIQUE (nombre),
        CONSTRAINT FK_impresoras_etiquetas_usuario
            FOREIGN KEY (id_usuario_carga) REFERENCES dbo.lims_usuarios(id_usuario)
    );
END
GO

-- Verificacion
SELECT * FROM dbo.lims_impresoras_etiquetas;
