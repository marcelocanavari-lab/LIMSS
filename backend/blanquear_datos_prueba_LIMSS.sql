-- ============================================================
-- LIMSS — Blanqueo de datos de prueba antes de producción
-- Versión 2.0 — Actualizado con todas las tablas
--
-- CONSERVA (datos maestros):
--   lims_usuarios, lims_laboratorios, lims_laboratorio_contactos
--   lims_testigos, lims_testigo_categorias, lims_testigo_laboratorios
--   lims_ensayos_maestro, lims_ensayos_OLD
--   lims_especificaciones, lims_especificacion_ensayos
--   lims_especificacion_muestras, lims_especificacion_testigos
--   lims_erp_config
--
-- BLANQUEA (movimientos y transacciones):
--   Todo lo demás
-- ============================================================
USE [LIMSS];
GO

PRINT '=== Iniciando blanqueo de datos de prueba ===';
PRINT '';

-- Desactivar restricciones de FK temporalmente
EXEC sp_MSforeachtable 'ALTER TABLE ? NOCHECK CONSTRAINT ALL';
GO

-- ── MÓDULO III — Dictámenes y aprobaciones ────────────────────
DELETE FROM lims_aprobaciones_lote;
PRINT 'lims_aprobaciones_lote: OK';

DELETE FROM lims_dictamenes;
PRINT 'lims_dictamenes: OK';

-- ── MÓDULO II — Resultados y protocolos ──────────────────────
DELETE FROM lims_orden_trabajo_resultados;
PRINT 'lims_orden_trabajo_resultados: OK';

DELETE FROM lims_resultados;
PRINT 'lims_resultados: OK';

DELETE FROM lims_protocolos;
PRINT 'lims_protocolos: OK';

-- ── MÓDULO I — Envíos ────────────────────────────────────────
DELETE FROM lims_envio_ensayos;
PRINT 'lims_envio_ensayos: OK';

DELETE FROM lims_envio_testigos;
PRINT 'lims_envio_testigos: OK';

DELETE FROM lims_envios;
PRINT 'lims_envios: OK';

DELETE FROM lims_etiquetas;
PRINT 'lims_etiquetas: OK';

DELETE FROM lims_remitos;
PRINT 'lims_remitos: OK';

-- ── MUESTRAS ─────────────────────────────────────────────────
DELETE FROM lims_muestras;
PRINT 'lims_muestras: OK';

-- ── SOLICITUDES DE MUESTREO ───────────────────────────────────
DELETE FROM lims_solicitud_muestras;
PRINT 'lims_solicitud_muestras: OK';

DELETE FROM lims_solicitudes_muestreo;
PRINT 'lims_solicitudes_muestreo: OK';

-- ── REMITOS Y MOVIMIENTOS DE TESTIGOS ────────────────────────
DELETE FROM lims_remito_testigos_det;
PRINT 'lims_remito_testigos_det: OK';

DELETE FROM lims_remito_testigos_cab;
PRINT 'lims_remito_testigos_cab: OK';

DELETE FROM lims_testigo_movimientos;
PRINT 'lims_testigo_movimientos: OK';

-- Resetear stock de testigos a 0 (los stocks reales se ingresan en producción)
UPDATE lims_testigos SET stock_actual = 0;
PRINT 'lims_testigos.stock_actual: reseteado a 0';

-- ── AUDIT TRAIL Y SESIONES ────────────────────────────────────
DELETE FROM lims_audit_trail;
PRINT 'lims_audit_trail: OK';

DELETE FROM lims_sesiones;
PRINT 'lims_sesiones: OK';

-- Reactivar restricciones de FK
EXEC sp_MSforeachtable 'ALTER TABLE ? WITH CHECK CHECK CONSTRAINT ALL';
GO

-- ── Resetear contadores IDENTITY ──────────────────────────────
DBCC CHECKIDENT ('lims_aprobaciones_lote',        RESEED, 0);
DBCC CHECKIDENT ('lims_dictamenes',               RESEED, 0);
DBCC CHECKIDENT ('lims_orden_trabajo_resultados', RESEED, 0);
DBCC CHECKIDENT ('lims_resultados',               RESEED, 0);
DBCC CHECKIDENT ('lims_protocolos',               RESEED, 0);
DBCC CHECKIDENT ('lims_envio_ensayos',            RESEED, 0);
DBCC CHECKIDENT ('lims_envio_testigos',           RESEED, 0);
DBCC CHECKIDENT ('lims_envios',                   RESEED, 0);
DBCC CHECKIDENT ('lims_etiquetas',                RESEED, 0);
DBCC CHECKIDENT ('lims_remitos',                  RESEED, 0);
DBCC CHECKIDENT ('lims_muestras',                 RESEED, 0);
DBCC CHECKIDENT ('lims_solicitud_muestras',       RESEED, 0);
DBCC CHECKIDENT ('lims_solicitudes_muestreo',     RESEED, 0);
DBCC CHECKIDENT ('lims_remito_testigos_det',      RESEED, 0);
DBCC CHECKIDENT ('lims_remito_testigos_cab',      RESEED, 0);
DBCC CHECKIDENT ('lims_testigo_movimientos',      RESEED, 0);
DBCC CHECKIDENT ('lims_audit_trail',              RESEED, 0);
DBCC CHECKIDENT ('lims_sesiones',                 RESEED, 0);
GO

PRINT '';
PRINT '==============================================';
PRINT 'LIMSS — Blanqueo completado exitosamente.';
PRINT '';
PRINT 'TABLAS CONSERVADAS (datos maestros):';
PRINT '  lims_usuarios';
PRINT '  lims_laboratorios + lims_laboratorio_contactos';
PRINT '  lims_testigos (stock reseteado a 0)';
PRINT '  lims_testigo_categorias';
PRINT '  lims_testigo_laboratorios';
PRINT '  lims_ensayos_maestro + lims_ensayos_OLD';
PRINT '  lims_especificaciones';
PRINT '  lims_especificacion_ensayos';
PRINT '  lims_especificacion_muestras';
PRINT '  lims_especificacion_testigos';
PRINT '  lims_erp_config';
PRINT '';
PRINT 'TABLAS BLANQUEADAS (movimientos):';
PRINT '  lims_muestras, lims_envios, lims_resultados';
PRINT '  lims_dictamenes, lims_aprobaciones_lote';
PRINT '  lims_solicitudes_muestreo, lims_solicitud_muestras';
PRINT '  lims_remitos, lims_etiquetas, lims_protocolos';
PRINT '  lims_remito_testigos_cab/det';
PRINT '  lims_testigo_movimientos';
PRINT '  lims_audit_trail, lims_sesiones';
PRINT '==============================================';
GO
