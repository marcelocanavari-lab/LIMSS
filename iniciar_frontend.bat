@echo off
setlocal



REM Inicia el frontend de LIMSS ya compilado (npm run preview) en el puerto 5174.

REM Si se cambio codigo en frontend\src, correr antes "npm run build" a mano

REM (dentro de esta misma carpeta) antes de ejecutar este script.



pushd "\\LAMARSERVER\Empresa\Lamar\LIMSS\frontend"



echo Iniciando frontend LIMSS (preview) en el puerto 5174...


rem call npm run preview

popd
endlocal


npm run dev -- --host --port 5174