/* =====================================================================
   Limpieza de datos transaccionales antes de lanzar LIMSS a produccion
   Generado: 2026-08-09

   Borra TODO lo que no es dato maestro (solicitudes, muestras, envios,
   resultados, dictamenes, facturas, remitos, movimientos de stock,
   auditoria y sesiones de prueba). Conserva intactos:

     - lims_especificaciones / lims_especificacion_ensayos /
       lims_especificacion_muestras / lims_especificacion_testigos
     - lims_ensayos_maestro
     - lims_laboratorios / lims_laboratorio_contactos
     - lims_testigos / lims_testigo_categorias / lims_testigo_origenes /
       lims_testigo_laboratorios
     - lims_erp_config
     - lims_usuarios

   IMPORTANTE:
   - Correr contra LA BASE CORRECTA. Verificar con el SELECT de abajo
     antes de descomentar el bloque de borrado.
   - Se recomienda correr crear_limss_dev.sql ANTES que este script,
     para tener un respaldo completo de los datos de prueba por si se
     necesitan consultar despues.
   - El orden de los DELETE respeta las foreign keys (hijos antes que
     padres) - no reordenar.
   - Corre dentro de una transaccion: si algo falla, se revierte todo
     (no queda la base a medio borrar).
   ===================================================================== */

USE LIMSS;
GO

-- Confirmar que estamos en la base correcta antes de continuar
SELECT DB_NAME() AS base_actual;
GO

BEGIN TRANSACTION;

BEGIN TRY

    DELETE FROM dbo.lims_aprobaciones_lote;
    PRINT 'lims_aprobaciones_lote: ' + CAST(@@ROWCOUNT AS VARCHAR) + ' filas borradas';

    DELETE FROM dbo.lims_factura_detalle;
    PRINT 'lims_factura_detalle: ' + CAST(@@ROWCOUNT AS VARCHAR) + ' filas borradas';

    DELETE FROM dbo.lims_orden_trabajo_resultados;
    PRINT 'lims_orden_trabajo_resultados: ' + CAST(@@ROWCOUNT AS VARCHAR) + ' filas borradas';

    DELETE FROM dbo.lims_resultados;
    PRINT 'lims_resultados: ' + CAST(@@ROWCOUNT AS VARCHAR) + ' filas borradas';

    DELETE FROM dbo.lims_etiquetas;
    PRINT 'lims_etiquetas: ' + CAST(@@ROWCOUNT AS VARCHAR) + ' filas borradas';

    DELETE FROM dbo.lims_testigo_movimientos;
    PRINT 'lims_testigo_movimientos: ' + CAST(@@ROWCOUNT AS VARCHAR) + ' filas borradas';

    DELETE FROM dbo.lims_envio_testigos;
    PRINT 'lims_envio_testigos: ' + CAST(@@ROWCOUNT AS VARCHAR) + ' filas borradas';

    DELETE FROM dbo.lims_remito_testigos_det;
    PRINT 'lims_remito_testigos_det: ' + CAST(@@ROWCOUNT AS VARCHAR) + ' filas borradas';

    DELETE FROM dbo.lims_sesiones;
    PRINT 'lims_sesiones: ' + CAST(@@ROWCOUNT AS VARCHAR) + ' filas borradas';

    DELETE FROM dbo.lims_audit_trail;
    PRINT 'lims_audit_trail: ' + CAST(@@ROWCOUNT AS VARCHAR) + ' filas borradas';

    DELETE FROM dbo.lims_dictamenes;
    PRINT 'lims_dictamenes: ' + CAST(@@ROWCOUNT AS VARCHAR) + ' filas borradas';

    DELETE FROM dbo.lims_factura_envios;
    PRINT 'lims_factura_envios: ' + CAST(@@ROWCOUNT AS VARCHAR) + ' filas borradas';

    DELETE FROM dbo.lims_envio_ensayos;
    PRINT 'lims_envio_ensayos: ' + CAST(@@ROWCOUNT AS VARCHAR) + ' filas borradas';

    DELETE FROM dbo.lims_remito_testigos_cab;
    PRINT 'lims_remito_testigos_cab: ' + CAST(@@ROWCOUNT AS VARCHAR) + ' filas borradas';

    DELETE FROM dbo.lims_facturas;
    PRINT 'lims_facturas: ' + CAST(@@ROWCOUNT AS VARCHAR) + ' filas borradas';

    DELETE FROM dbo.lims_protocolos;
    PRINT 'lims_protocolos: ' + CAST(@@ROWCOUNT AS VARCHAR) + ' filas borradas';

    DELETE FROM dbo.lims_remitos;
    PRINT 'lims_remitos: ' + CAST(@@ROWCOUNT AS VARCHAR) + ' filas borradas';

    DELETE FROM dbo.lims_solicitud_muestras;
    PRINT 'lims_solicitud_muestras: ' + CAST(@@ROWCOUNT AS VARCHAR) + ' filas borradas';

    DELETE FROM dbo.lims_envios;
    PRINT 'lims_envios: ' + CAST(@@ROWCOUNT AS VARCHAR) + ' filas borradas';

    DELETE FROM dbo.lims_solicitudes_muestreo;
    PRINT 'lims_solicitudes_muestreo: ' + CAST(@@ROWCOUNT AS VARCHAR) + ' filas borradas';

    DELETE FROM dbo.lims_muestras;
    PRINT 'lims_muestras: ' + CAST(@@ROWCOUNT AS VARCHAR) + ' filas borradas';

    -- Reiniciar los contadores IDENTITY para que la produccion arranque
    -- desde 1 (numeracion prolija de solicitudes/muestras/envios, etc.)
    DBCC CHECKIDENT ('dbo.lims_aprobaciones_lote', RESEED, 0);
    DBCC CHECKIDENT ('dbo.lims_factura_detalle', RESEED, 0);
    DBCC CHECKIDENT ('dbo.lims_orden_trabajo_resultados', RESEED, 0);
    DBCC CHECKIDENT ('dbo.lims_resultados', RESEED, 0);
    DBCC CHECKIDENT ('dbo.lims_etiquetas', RESEED, 0);
    DBCC CHECKIDENT ('dbo.lims_testigo_movimientos', RESEED, 0);
    DBCC CHECKIDENT ('dbo.lims_envio_testigos', RESEED, 0);
    DBCC CHECKIDENT ('dbo.lims_remito_testigos_det', RESEED, 0);
    DBCC CHECKIDENT ('dbo.lims_sesiones', RESEED, 0);
    DBCC CHECKIDENT ('dbo.lims_audit_trail', RESEED, 0);
    DBCC CHECKIDENT ('dbo.lims_dictamenes', RESEED, 0);
    DBCC CHECKIDENT ('dbo.lims_factura_envios', RESEED, 0);
    DBCC CHECKIDENT ('dbo.lims_envio_ensayos', RESEED, 0);
    DBCC CHECKIDENT ('dbo.lims_remito_testigos_cab', RESEED, 0);
    DBCC CHECKIDENT ('dbo.lims_facturas', RESEED, 0);
    DBCC CHECKIDENT ('dbo.lims_protocolos', RESEED, 0);
    DBCC CHECKIDENT ('dbo.lims_remitos', RESEED, 0);
    DBCC CHECKIDENT ('dbo.lims_solicitud_muestras', RESEED, 0);
    DBCC CHECKIDENT ('dbo.lims_envios', RESEED, 0);
    DBCC CHECKIDENT ('dbo.lims_solicitudes_muestreo', RESEED, 0);
    DBCC CHECKIDENT ('dbo.lims_muestras', RESEED, 0);

    -- NO se toca: lims_testigos.stock_actual queda como esta
    -- (el stock actual vigente de cada testigo no se resetea, solo se
    -- borra el HISTORIAL de movimientos que llevo a ese numero).

    PRINT '--- Todo borrado correctamente. Revisar los conteos arriba antes de hacer COMMIT. ---';

    -- *** IMPORTANTE ***
    -- Revisar los mensajes de arriba. Si todo se ve correcto, descomentar
    -- la siguiente linea y volver a ejecutar SOLO esa linea (o correr todo
    -- el script de nuevo con COMMIT activo) para confirmar el borrado.
    -- Si algo se ve mal, ejecutar ROLLBACK TRANSACTION; en su lugar.

    -- COMMIT TRANSACTION;

END TRY
BEGIN CATCH
    ROLLBACK TRANSACTION;
    PRINT 'ERROR - se revirtio todo. Detalle:';
    PRINT ERROR_MESSAGE();
END CATCH
GO

-- Verificacion final (correr DESPUES del COMMIT)
SELECT
    (SELECT COUNT(*) FROM dbo.lims_muestras) AS muestras,
    (SELECT COUNT(*) FROM dbo.lims_solicitudes_muestreo) AS solicitudes,
    (SELECT COUNT(*) FROM dbo.lims_envios) AS envios,
    (SELECT COUNT(*) FROM dbo.lims_facturas) AS facturas,
    (SELECT COUNT(*) FROM dbo.lims_testigos) AS testigos_maestro_intacto,
    (SELECT COUNT(*) FROM dbo.lims_especificaciones) AS especificaciones_maestro_intacto,
    (SELECT COUNT(*) FROM dbo.lims_usuarios) AS usuarios_maestro_intacto;
