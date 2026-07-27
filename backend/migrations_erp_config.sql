-- ============================================================
-- MIGRACIÓN: configuración editable de la relación LIMSS-ERP
-- ------------------------------------------------------------
-- Hoy el mapeo tipo_material -> CODSAR (GIT59SAR, ERP GI_LX) está
-- hardcodeado en backend/app/services/erp_materiales.py
-- (CODSAR_POR_TIPO). Esta migración crea lims_erp_config para que
-- ese mapeo se pueda editar desde una pantalla de administración
-- (solo admin) sin tocar código. El servicio sigue teniendo los
-- valores hardcodeados como fallback si la consulta a esta tabla
-- falla -- ver obtener_codsar_por_tipo() en erp_materiales.py.
--
-- Idempotente (igual que el resto de backend/*.sql).
--
-- Ejecutar en la BD LIMSS (SQL Server Management Studio)
-- ============================================================

USE [LIMSS];
GO

IF NOT EXISTS (SELECT 1 FROM sys.tables WHERE name = 'lims_erp_config')
BEGIN
    CREATE TABLE lims_erp_config (
        id                          INT IDENTITY(1,1)  PRIMARY KEY,
        clave                       VARCHAR(50)         NOT NULL UNIQUE,
        valor                       VARCHAR(100)        NOT NULL,
        descripcion                 VARCHAR(200)        NULL,
        editable                    BIT                 NOT NULL DEFAULT 1,
        fecha_modificacion          DATETIME            NULL,
        id_usuario_modificacion     INT                 NULL
            REFERENCES lims_usuarios(id_usuario)
    );
    PRINT 'Tabla lims_erp_config creada';
END
GO

-- Valores actuales hardcodeados en erp_materiales.CODSAR_POR_TIPO
-- (mapeo confirmado por el usuario del negocio -- ver docstring de ese
-- módulo). Se insertan solo si la tabla está vacía, para no pisar
-- ediciones ya hechas desde la UI si esta migración se corre de nuevo.
IF NOT EXISTS (SELECT 1 FROM lims_erp_config)
BEGIN
    INSERT INTO lims_erp_config (clave, valor, descripcion, editable) VALUES
    ('codsar_materia_prima',      '0001', 'Código CODSAR para Materia Prima en GIT59SAR (ERP GI_LX)',       1),
    ('codsar_granel',             '0002', 'Código CODSAR para Granel en GIT59SAR (ERP GI_LX)',               1),
    ('codsar_semi_elaborado',     '0003', 'Código CODSAR para Semi Elaborado en GIT59SAR (ERP GI_LX)',       1),
    ('codsar_producto_terminado', '0000', 'Código CODSAR para Producto Terminado en GIT59SAR (ERP GI_LX)',   1);
    PRINT 'Valores iniciales de lims_erp_config insertados';
END
GO
