# Guía de Despliegue: LIMSS_DEV → LIMSS (Producción)

*Runbook paso a paso para llevar cambios probados en desarrollo a producción.*

---

## Cuándo usar esta guía

Cada vez que haya trabajo terminado y probado en `LIMSS_DEV` (código + base de datos) que necesite
pasar a `LIMSS` (producción). No es para cambios puntuales de configuración de un solo entorno
(esos van directo en el `.env`/pantalla correspondiente, no necesitan este proceso).

Ver también `circuito_trabajo_limss.md` para el contexto general de por qué el proyecto está
armado con dos carpetas + dos ramas de git, y los errores típicos de ruta de red vs local.

---

## Paso 1 — Sincronizar el código (git)

### 1.1 Confirmar en qué rama está parada la carpeta

**Antes de nada**, en `LIMSS_DEV`:

```
git branch
```

Tiene que mostrar `* dev`. Si por algún motivo muestra `* main` (puede pasar después de un reinicio
del servidor o una sesión de troubleshooting anterior), **no cambiar de rama todavía** si hay
cambios sin commitear — commitear primero donde está parado, y recién después reconciliar (ver
1.4). Cambiar de rama con cambios sueltos es el error más peligroso de todo este proceso.

### 1.2 Revisar y commitear los cambios de LIMSS_DEV

```
git add .
git status
```

Revisar la lista **antes** de comittear — no debe aparecer nunca:
- `node_modules/`
- `storage/` (documentos reales: protocolos, facturas, remitos firmados)
- `.env` (con contraseñas/API keys reales — solo `.env.example` está bien)
- Cualquier carpeta de red (`Y:\...` como ruta, en vez de trabajar en `C:\ServerFolders\...`)

Si la lista se ve bien:

```
git commit -m "Descripción clara de lo que se hizo en esta tanda"
git push
```

### 1.3 Llevar `dev` a `main`

```
git checkout main
git merge dev
git push
git checkout dev
```

(El último `git checkout dev` es importante — deja la carpeta lista para seguir trabajando ahí la
próxima vez, en vez de quedar parada en `main` por error.)

### 1.4 Si `git push` es rechazado ("fetch first" / "Updates were rejected")

Significa que el remoto tiene commits que la copia local no tiene (puede pasar si alguien commiteó
algo directo en producción, o en otra sesión). Traerlos primero:

```
git pull
```

Si pide un mensaje de merge, guardar y cerrar tal cual está. Después repetir el `git push`.

### 1.5 Traer el código a producción

En la carpeta `LIMSS` (producción):

```
git status
```

Confirmar que está limpia (sin cambios locales/archivos sueltos sin trackear que puedan chocar con
lo que se va a traer — si hay archivos sueltos con el mismo nombre que algo del pull, borrarlos
primero, git los va a traer versionados correctamente).

```
git pull
```

---

## Paso 2 — Aplicar las migraciones SQL a producción

1. Reunir todos los scripts `.sql` generados durante la sesión de desarrollo (si se perdió la
   cuenta de cuáles son, pedir la lista completa).
2. Confirmar que cada uno diga `USE LIMSS;` (no `USE LIMSS_DEV;`) — si no, corregir la línea o
   simplemente seleccionar la base `LIMSS` en el desplegable de SSMS antes de ejecutar.
3. Abrir SSMS, conectar al servidor, y para cada script:
   - **Archivo → Abrir → Archivo...** (o copiar/pegar el contenido en una consulta nueva)
   - Confirmar la base `LIMSS` en el desplegable de la barra de herramientas
   - F5 para ejecutar
   - Confirmar que no haya errores en rojo antes de pasar al siguiente
4. La mayoría de las migraciones de este proyecto usan `IF COL_LENGTH(...) IS NULL` (o
   equivalente) — son seguras de correr aunque ya estén aplicadas, no hace falta llevar la cuenta
   exacta de cuál se corrió antes.
5. Como chequeo final, se puede correr `comparar_limss_dev_vs_produccion.sql` para confirmar que no
   quedó ninguna diferencia de esquema entre las dos bases.

---

## Paso 3 — Configurar el entorno de producción

Estas cosas **no viajan con git ni con la base de datos** — cada entorno mantiene la suya:

### 3.1 Variables de `.env`

Comparar `backend\.env` de producción contra `backend\.env.example` (que sí viaja con git y
muestra qué variables espera el código) y contra el `.env` de `LIMSS_DEV`. Agregar las que falten,
con los valores reales de producción (no copiar valores de desarrollo tal cual si son
específicos del entorno, como rutas o IPs).

Ejemplos vistos en esta sesión: `TESSERACT_PATH`, `ANTHROPIC_API_KEY` (opcional).

### 3.2 Dependencias de Python nuevas

Si se agregó algún paquete nuevo a `requirements.txt` (por ejemplo `pywin32`, `pytesseract`):

```
cd /d C:\ServerFolders\Empresa\Lamar\LIMSS\backend
C:\Python312-embed\python.exe -m pip install -r requirements.txt
```

### 3.3 Software instalado en el servidor

Si el desarrollo necesitó instalar algo en el servidor mismo (Tesseract, etc.), confirmar que ya
esté disponible — en este proyecto, como `LIMSS` y `LIMSS_DEV` corren en el mismo servidor físico
(`LAMARSERVER`), lo que se instaló una vez ya sirve para las dos instancias, no hace falta
reinstalar.

---

## Paso 4 — Reiniciar backend y frontend de producción

Usar los `.bat` correspondientes (`iniciar_backend.bat` / `iniciar_frontend.bat` /
`iniciar_limss.bat`), parado en la ruta **local** de producción
(`C:\ServerFolders\Empresa\Lamar\LIMSS`), nunca desde `Y:\Lamar\LIMSS`.

---

## Paso 5 — Configuración específica de producción

Datos que se cargan a mano en cada entorno por separado (no viajan con el deploy):

- Subarticulos configurados (`Requiere muestreo`, bloques por especificación)
- Impresoras (`Impresión de Etiquetas` → rutas de red / IPs reales, no las de prueba de
  `LIMSS_DEV`)
- Cualquier otro dato maestro cargado durante las pruebas en desarrollo

---

## Paso 6 — Verificación final

### 6.1 Chequeo automático de entorno

Parado en `backend\` de producción:

```
verificar_entorno.bat
```

Confirmar: `Errores: 0`. Los avisos de `ANTHROPIC_API_KEY` y `git` (si no está instalado en el
servidor) son esperables y aceptados a propósito en este proyecto — no bloquean nada.

### 6.2 Prueba de humo manual

- Login funciona
- El Dashboard carga sin errores
- Entrar a alguna pantalla nueva de la tanda que se está desplegando y confirmar que se ve/funciona
  como en `LIMSS_DEV`

---

## Errores típicos (ya nos pasaron todos, ver también `circuito_trabajo_limss.md`)

| Síntoma | Causa probable |
|---|---|
| `npm`/`pip install` lento o falla raro | Corriendo desde `Y:\...` (red) en vez de `C:\ServerFolders\...` (local) |
| Frontend apunta al puerto de API equivocado | `.env.production` faltante, o se corrió `npm run dev` en vez de `npm run build` + `npm run preview` |
| `git push` rechazado | El remoto tiene commits que la copia local no tiene — `git pull` primero |
| La carpeta quedó en la rama equivocada | Verificar con `git branch` antes de cualquier commit/merge |
| Un script SQL falla con "objeto no válido" | Corriendo contra la base equivocada — confirmar `LIMSS` vs `LIMSS_DEV` vs `GI_LX` según corresponda al script |
| Feature que depende de un ejecutable externo no funciona | Confirmar que el ejecutable (Tesseract, etc.) esté instalado en **esta** máquina específica, no en la PC de quien lo probó primero |
