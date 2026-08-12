# LIMSS — Estado del sistema

**Generado:** 6 de agosto de 2026
**Build:** `004b6f4`
**Servidor:** LAMARSERVER · 192.168.10.99
**Estado general:** v1.0 en producción — Laboratorio Lamar

---

## 1. Resumen

LIMSS (LIMS Simplificado) cubre el flujo completo de control de calidad con laboratorios externos: alta de muestra → envío (posiblemente a varios laboratorios en paralelo) → carga de resultados → dictamen QA con firma por PIN → facturación del laboratorio externo.

Esta ronda de trabajo agregó un módulo completo nuevo (**Facturación de Laboratorios**) y una serie de mejoras/correcciones sobre Testigos, el Dashboard y el Reporte de Testigos.

| | |
|---|---|
| Routers de backend | 14 |
| Pantallas de frontend | 38 |
| Roles | `muestreador` · `analista_qc` · `qa` · `admin` |
| Módulos nuevos esta sesión | 1 (Facturación) |

---

## 2. Arquitectura

| Componente | Detalle |
|---|---|
| Backend | FastAPI 0.111 + Uvicorn sobre Python 3.12, acceso a SQL Server vía `pyodbc`. Autenticación JWT (`python-jose`) con PIN de usuario. |
| Frontend | React 18 + Vite, servido en producción como build estático (`npm run preview`), no como dev server. |
| Base de datos | SQL Server, base `LIMSS`. La cuenta de aplicación (`limss_app`) tiene permisos solo de DML — todo cambio de esquema (DDL) se ejecuta a mano en SSMS. |
| Integración ERP | Conexión de solo lectura a la base `GI_LX` (artículos, proveedores, datos de lote). |
| Roles | `muestreador` · `analista_qc` · `qa` · `admin`, con acceso creciente en ese orden. |

---

## 3. Inventario funcional

| Módulo | Archivo backend | Qué hace | Estado |
|---|---|---|---|
| Datos Maestros | `maestros.py` | Especificaciones (límites por artículo/tipo de material, versionado, copia), catálogo de ensayos, y Testigos y Estándares: stock, vencimiento opcional, laboratorios asignados con consumo estimado por análisis, categorías y orígenes como catálogos propios, remitos de testigos. | Ampliado |
| Muestras y Envíos | `muestras.py` | Alta de muestra, envíos múltiples a distintos laboratorios en paralelo, contactos por laboratorio, remitos con constancia de recepción firmada. Al confirmar un envío, descuenta stock del testigo automáticamente según el consumo configurado. | Ampliado |
| Carga de Resultados | `resultados.py` | Bandeja de envíos pendientes, carga de valores por envío, cálculo de fuera-de-especificación (OOS). | Estable |
| Dictamen QA | `dictamenes.py` | Aprobación o rechazo de una muestra una vez completos todos sus envíos, con firma por PIN y registro append-only de aprobaciones. | Estable |
| Facturación de Laboratorios | `facturas.py` | Registro de facturas recibidas, vinculadas a los envíos que cubren; un envío no puede facturarse dos veces. Estados pendiente / pagado / anulado, con registro de pago y auditoría. | **Nuevo** |
| Solicitudes de Muestreo | `solicitudes_muestreo.py` | Asignación de solicitudes a muestreadores y orden de trabajo digital para ejecutarlas en planta. | Estable |
| Auditoría | `auditoria.py` | Trazabilidad de alta/baja/modificación sobre las entidades principales, consultable por rol admin. | Estable |
| Configuración ERP y Usuarios | `erp_config.py` · `auth.py` | Parámetros de integración editables y gestión de usuarios/roles, incluyendo acceso opcional al sistema eBR. | Estable |
| Dashboard | `dashboard.py` | Estado general, testigos por vencer, solicitudes sin ejecutar. | Corregido |

---

## 4. Cambios de esta sesión

### Módulo de Facturación de Laboratorios (nuevo)
Alta con selector de envíos sin facturar (identificados por N° de remito, código de muestra, IR, material y cantidad de ensayos), detalle con historial, registro de pago y anulación. El detalle de un envío ahora muestra si tiene factura asociada y su estado.

### Categorías y orígenes de testigos como catálogos
El origen del testigo dejó de ser un valor fijo (USP / EP / INAME) para pasar a una tabla editable, igual que categoría. Ambas se administran desde Administración con alta, edición y baja lógica.

### Consumo por laboratorio y descuento automático de stock
Cada laboratorio asignado a un testigo puede tener un consumo estimado por análisis. Al confirmar un envío que incluye ese testigo, el stock se descuenta solo si hay consumo configurado; si no, queda registrado en auditoría que no se descontó.

### Reporte de Testigos: más contexto, mejor lectura
Se agregaron columnas de laboratorio(s), categoría y origen, con sus filtros. La tabla en pantalla ahora scrollea horizontalmente sin desbordar la página; la impresión/PDF quedó igual que antes (vertical, sin cambios de tamaño de fuente).

### Dashboard: filtros que arrancaban mal
El widget de testigos y la pantalla de Testigos arrancaban con "Vencido" y "Por vencer" preseleccionados en vez de mostrar todo. Ahora ambos arrancan sin filtro de estado aplicado.

### Corrección crítica: PDFs no abrían en iPad/iPhone
Safari en iOS bloqueaba la apertura de certificados y remitos porque la ventana se abría después de la descarga (después de un `await`). Se corrigió abriendo la ventana antes de pedir el archivo — funciona igual en Safari iOS, Chrome Android y navegadores de escritorio.

---

## 5. Base de datos — migraciones de esta ronda

La cuenta de aplicación no tiene permisos de DDL: cada cambio de esquema se entrega como script idempotente y se ejecuta a mano en SSMS. Todo lo listado abajo ya está aplicado y verificado en vivo contra la base real.

| Tabla / columna | Motivo | Estado |
|---|---|---|
| `lims_testigo_laboratorios` | Relación testigo ↔ laboratorio (muchos a muchos), con `consumo_estimado` y `unidad_consumo` | ✅ Aplicada |
| `lims_testigo_categorias` | Catálogo editable de categorías de testigo | ✅ Aplicada |
| `lims_testigo_origenes` | Catálogo editable de orígenes, reemplaza el campo fijo | ✅ Aplicada |
| `lims_testigos.fecha_vencimiento` | Pasó a admitir NULL (vencimiento opcional) | ✅ Aplicada |
| `lims_facturas` / `lims_factura_envios` | Facturas de laboratorio y su vínculo con envíos | ✅ Aplicada |

**Quedan sin eliminar, a propósito:** `lims_testigos.origen` (texto libre) y `lims_testigos.id_laboratorio` (un solo laboratorio). Ambos fueron reemplazados por relaciones propias pero se conservan por compatibilidad con datos y consultas existentes.

---

## 6. Infraestructura y despliegue

| Componente | Detalle |
|---|---|
| Backend | `C:\Python312-embed\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8002` — sin autoreload, hay que reiniciarlo a mano para que tome cambios de código. |
| Frontend | `npm run build` y después reiniciar `npm run preview` (puerto 5174) — no es el dev server, es un build estático. |
| Scripts | `iniciar_backend.bat` · `iniciar_frontend.bat` · `iniciar_limss.bat` en la raíz del proyecto. |
| Acceso en red | LAN: `http://192.168.10.99:5174`. Requiere reglas de firewall abiertas para 8002 y 5174. |

> **Importante:** un cambio "terminado" en el código no queda activo hasta reiniciar backend y frontend manualmente en el servidor — un build exitoso en desarrollo no implica que ya esté en producción.

---

*Documento generado a partir del historial de commits (`git log`, `git show --stat 004b6f4`) y verificación en vivo del código y la base de datos.*
