# LIMSS — Puesta en marcha del ambiente de desarrollo (LIMSS_DEV)

Esta guía monta una instancia completa en paralelo a producción, apuntando a `LIMSS_DEV` en vez de
`LIMSS`, sin tocar lo que va a estar corriendo para los usuarios reales.

## 1. Base de datos

Correr `crear_limss_dev.sql` en SSMS (ajustando las rutas de backup/restore a las reales del
servidor). Al terminar, vas a tener `LIMSS_DEV` como una copia completa e independiente de `LIMSS`.

## 2. Carpeta del proyecto

No compartas la misma carpeta de código entre producción y desarrollo — cada una necesita su propio
proceso corriendo con su propia configuración. Opciones, de más simple a más prolija:

- **Simple**: copiar toda la carpeta `LIMSS` a `LIMSS_DEV` en el servidor (ej.
  `C:\ServerFolders\Empresa\Lamar\LIMSS_DEV\`), y desde ahí trabajar en el código de desarrollo sin
  tocar la carpeta de producción.
- **Más prolija (recomendada a mediano plazo)**: usar control de versiones (git) con una rama de
  desarrollo, y dos checkouts separados — pero si hoy no hay git en el proyecto, empezar con la
  copia de carpeta es válido para no bloquear el lanzamiento.

## 3. Configuración del backend de desarrollo

Buscar el archivo de configuración de conexión a la base (`.env`, `config.py`, o donde esté definido
el connection string — revisar cómo lo lee `app/main.py` o el módulo de conexión a SQL Server) DENTRO
de la copia `LIMSS_DEV`, y cambiar:

- Nombre de base: `LIMSS` → `LIMSS_DEV`
- Puerto de uvicorn: `8002` → `8003`

## 4. Configuración del frontend de desarrollo

Dentro de la copia `LIMSS_DEV`, en la config del frontend (`.env`, `vite.config.js`, o donde esté la
URL base de la API):

- URL de la API: apuntar a `http://[IP_SERVIDOR]:8003` (el backend de desarrollo, no el de
  producción en 8002)
- Puerto de `npm run preview`: `5174` → `5175`

## 5. Scripts de arranque propios

Duplicar `iniciar_backend.bat`, `iniciar_frontend.bat` e `iniciar_limss.bat` dentro de la carpeta
`LIMSS_DEV` con otros nombres (ej. `iniciar_backend_dev.bat`) apuntando a la carpeta y puertos de
desarrollo, para no confundirlos con los de producción al arrancar el servidor.

## 6. Acceso

Una vez levantado:

- **Producción**: `http://192.168.10.99:5174` (sin cambios)
- **Desarrollo**: `http://192.168.10.99:5175`

Ambos pueden correr al mismo tiempo en el mismo servidor sin pisarse, porque usan bases de datos y
puertos distintos.

## 7. Recordatorio importante

Cualquier cambio de esquema (ALTER TABLE, etc.) que se pruebe en desarrollo hay que volver a
aplicarlo manualmente en producción cuando esté listo para pasar — las dos bases quedan
desincronizadas desde el momento de la copia, igual que ya pasa con el resto de las migraciones
manuales del proyecto.
