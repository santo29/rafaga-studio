@echo off
cd /d "%~dp0"
if not exist .venv (
  echo Instalando por primera vez, espera unos minutos...
  py -3 -m venv .venv
  rem Versiones exactas ya probadas y el hash de cada archivo: nada distinto de lo probado entra solo.
  rem torch va aparte y solo desde el indice oficial de PyTorch (sin mezclar indices).
  .venv\Scripts\python -m pip install --require-hashes --no-deps -r requirements-torch.lock --index-url https://download.pytorch.org/whl/cpu
  if errorlevel 1 goto fallo
  .venv\Scripts\python -m pip install --require-hashes -r requirements.lock
  if errorlevel 1 goto fallo
)
rem yt-dlp se actualiza solo y en segundo plano (sin frenar el arranque): YouTube cambia a menudo.
rem Solo versiones publicadas hace 7 dias o mas (si una sale maliciosa, da tiempo a que la retiren) y ya
rem compiladas (nada de ejecutar codigo de instalacion).
start "" .venv\Scripts\pythonw.exe -m pip install -q -U --only-binary :all: --uploaded-prior-to P7D yt-dlp yt-dlp-ejs
start "" .venv\Scripts\pythonw.exe app.py
exit /b 0

:fallo
rem Si un archivo no coincide con su hash (o se corta la red), no se deja una instalacion a medias: se borra y
rem se reintenta en el proximo arranque.
echo.
echo La instalacion fallo: revisa el mensaje de arriba (sin internet, o un archivo distinto del probado).
rmdir /s /q .venv
pause
exit /b 1
