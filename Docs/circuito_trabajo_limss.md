# Circuito de trabajo: LIMSS_DEV → LIMSS

## Las dos instancias

| | LIMSS_DEV | LIMSS |
|---|---|---|
| Rol | Desarrollo y pruebas | Producción |
| Carpeta local | `C:\ServerFolders\Empresa\Lamar\LIMSS_DEV` | `C:\ServerFolders\Empresa\Lamar\LIMSS` |
| Base de datos | `LIMSS_DEV` | `LIMSS` |
| Backend (puerto) | 8003 | 8002 |
| Frontend (puerto) | 5175 | 5174 |
| Rama de git | `dev` | `main` |

Las dos corren en paralelo, en el mismo servidor (`LAMARSERVER`), completamente aisladas entre sí
(procesos, puertos y bases de datos distintos). Cambiar algo en una no afecta a la otra hasta que
se hace el pasaje explícito descripto abajo.

## Circuito para cada cambio

1. **Se trabaja en `LIMSS_DEV`** — Claude Code modifica código ahí, se corren las migraciones SQL
   contra la base `LIMSS_DEV`, se prueba a fondo (checklist de prueba manual de cada prompt).
2. **Se confirma que funciona** — recién ahí se considera "listo para producción".
3. **Se lleva a producción, las tres partes por separado:**
   - **Base de datos**: correr las mismas migraciones SQL, esta vez contra `LIMSS` (producción).
   - **Backend y frontend (código)**: vía git —
     ```
     :: En LIMSS_DEV
     git add .
     git status          (revisar: nada de node_modules, storage/, .env real)
     git commit -m "..."
     git push

     git checkout main
     git merge dev
     git push
     git checkout dev    (volver a dev para seguir trabajando ahí)

     :: En LIMSS (producción)
     git pull
     ```
   - **Reiniciar producción**: `iniciar_backend.bat` / `iniciar_frontend.bat` / `iniciar_limss.bat`
     desde la carpeta `LIMSS` (nunca desde `Y:\Lamar\LIMSS`, siempre la ruta local). El frontend
     compila automáticamente al arrancar, no hace falta un paso manual aparte.
4. **Configuración específica de cada entorno** (tablas de configuración como
   `lims_erp_subarticulo_config`, parámetros en `lims_erp_config`, etc.) **no viaja con el
   código** — cada base mantiene la suya. Lo que se prueba en `LIMSS_DEV` con datos de prueba hay
   que volver a cargarlo con datos reales en `LIMSS`.

## Errores típicos a evitar (ya nos pasaron todos)

- **Ruta de red (`Y:\Lamar\...`) en vez de ruta local** (`C:\ServerFolders\...`) — instalar
  dependencias (`npm install`) o compilar por la ruta de red corrompe `node_modules` silenciosamente.
  Siempre operar por la ruta local.
- **`npm run dev` en vez de `npm run build` + `npm run preview`** — el modo dev no lee
  `.env.production`, así que el frontend termina apuntando al backend equivocado.
- **Confundir en qué carpeta se está parado** (`LIMSS` vs `LIMSS_DEV`) — antes de correr un comando,
  fijarse que el prompt de la consola muestre la ruta esperada.
- **`frontend/.env.production` faltante o con el valor equivocado** — si no existe, el código cae en
  un puerto hardcodeado de respaldo (8002) sin avisar. Cada carpeta necesita su propio archivo, con
  su propio puerto, y no viaja por git (está en `.gitignore` a propósito).
- **Compilar y no reiniciar el proceso** (o viceversa) — un archivo de configuración corregido no
  tiene efecto hasta que se vuelve a compilar (`npm run build`) y se reinicia el `preview`.

## Regla de oro

Ante cualquier comportamiento raro después de un cambio, antes de sospechar del código: confirmar
**en qué carpeta** se está parado, **qué rama** de git tiene esa carpeta, y **si el backend/frontend
se reiniciaron** después del último cambio. La mayoría de los problemas de esta sesión fueron eso,
no bugs reales.
