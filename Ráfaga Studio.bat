@echo off
rem UTF-8: los textos llevan tildes y sin esto cmd las enseña rotas
chcp 65001 >nul
cd /d "%~dp0"
rem La copia instalada con instalador\rafaga.iss lleva su Python en python\tools
if exist python\tools\pythonw.exe (
  start "" python\tools\pythonw.exe -s -E app.py
  exit /b 0
)
if not exist .venv (
  rem Dentro de este bloque, un parentesis en un echo lo cierra antes de tiempo y el .bat no arranca: van con ^
  echo Ráfaga Studio · © 2026 Santo Montilla. Tus proyectos y claves se guardan en tu PC; las funciones
  echo de IA usan servicios de internet ^(lee PRIVACIDAD.md^).
  echo Lee PRIVACIDAD.md y TERMINOS.md: al abrir la app verás el aviso de privacidad.
  echo Instalando por primera vez, espera unos minutos...
  py -3 -m venv .venv
  rem Versiones exactas ya probadas y el hash de cada archivo: nada distinto de lo probado entra solo. Solo archivos
  rem ya compilados: compilar uno bajaria herramientas de compilacion sin hash. -s -E: nada de PYTHONPATH ajenos.
  rem torch va aparte y solo desde el indice oficial de PyTorch (sin mezclar indices).
  .venv\Scripts\python -s -E -m pip install --only-binary :all: --require-hashes --no-deps -r requirements-torch.lock --index-url https://download.pytorch.org/whl/cpu
  if errorlevel 1 goto fallo
  .venv\Scripts\python -s -E -m pip install --only-binary :all: --require-hashes -r requirements.lock
  if errorlevel 1 goto fallo
)
rem yt-dlp se actualiza solo al abrir la app (ver app.py).
start "" .venv\Scripts\pythonw.exe -s -E app.py
exit /b 0

:fallo
rem Si un archivo no coincide con su hash (o se corta la red), no se deja una instalacion a medias: se borra y
rem se reintenta en el proximo arranque.
echo.
echo La instalación falló: revisa el mensaje de arriba (sin internet, o un archivo distinto del probado).
rmdir /s /q .venv
pause
exit /b 1
