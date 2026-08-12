@echo off
setlocal

REM Inicia el frontend de LIMSS compilado para produccion (npm run build +
REM npm run preview) en el puerto 5174. Usa la ruta LOCAL del disco (no la
REM ruta de red) por la misma razon que el backend: instalar/operar via
REM red demostro ser poco confiable.
REM
REM IMPORTANTE: este script SIEMPRE compila antes de arrancar (npm run
REM build), para no correr nunca una version vieja del codigo por
REM accidente. Tarda unos segundos mas en arrancar a cambio de esa garantia.
REM
REM Version anterior de este script tenia un bug: el pushd/popd a la ruta
REM de red no envolvia el arranque real (popd se ejecutaba ANTES del cd
REM frontend + npm run dev de mas abajo), y ademas usaba "npm run dev"
REM en vez de "npm run preview" -- el modo dev ignora .env.production y
REM el frontend termina apuntando al puerto de API equivocado. Corregido.

cd /d "C:\ServerFolders\Empresa\Lamar\LIMSS\frontend"
if errorlevel 1 (
    echo ERROR: no se encontro la carpeta del frontend en la ruta esperada.
    echo Verificar que C:\ServerFolders\Empresa\Lamar\LIMSS\frontend exista.
    pause
    exit /b 1
)

if not exist "node_modules" (
    echo node_modules no existe, instalando dependencias por primera vez...
    call npm install
    if errorlevel 1 (
        echo ERROR: npm install fallo. Revisar el mensaje de arriba.
        pause
        exit /b 1
    )
)

echo Compilando frontend LIMSS para produccion...
call npm run build
if errorlevel 1 (
    echo ERROR: npm run build fallo. No se va a iniciar el preview con un
    echo build viejo/roto. Revisar el mensaje de arriba.
    pause
    exit /b 1
)

echo Iniciando frontend LIMSS (preview) en el puerto 5174...
call npm run preview -- --host 0.0.0.0 --port 5174

endlocal
