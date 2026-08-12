@echo off
setlocal

REM Inicia el frontend de LIMSS_DEV compilado para produccion (npm run
REM build + npm run preview) en el puerto 5175. Usa la ruta LOCAL del
REM disco (no la ruta de red) porque instalar/operar via red demostro
REM ser poco confiable.
REM
REM IMPORTANTE: este script SIEMPRE compila antes de arrancar (npm run
REM build), para no correr nunca una version vieja del codigo por
REM accidente.

cd /d "C:\ServerFolders\Empresa\Lamar\LIMSS_DEV\frontend"
if errorlevel 1 (
    echo ERROR: no se encontro la carpeta del frontend en la ruta esperada.
    echo Verificar que C:\ServerFolders\Empresa\Lamar\LIMSS_DEV\frontend exista.
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

echo Compilando frontend LIMSS_DEV para produccion...
call npm run build
if errorlevel 1 (
    echo ERROR: npm run build fallo. No se va a iniciar el preview con un
    echo build viejo/roto. Revisar el mensaje de arriba.
    pause
    exit /b 1
)

echo Iniciando frontend LIMSS_DEV (preview) en el puerto 5175...
call npm run preview -- --host 0.0.0.0 --port 5175

endlocal
