@echo off
setlocal
cd /d "%~dp0"

set "VOICE_STUDIO_URL=http://127.0.0.1:8765"

curl.exe --silent --fail --max-time 2 "%VOICE_STUDIO_URL%/api/summary" >nul 2>&1
if not errorlevel 1 (
  echo Voice Studio is already running.
  start "" "%VOICE_STUDIO_URL%"
  exit /b 0
)

echo Starting Voice Studio...
start "Voice Studio Server" powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0start.ps1"

for /l %%I in (1,1,60) do (
  curl.exe --silent --fail --max-time 1 "%VOICE_STUDIO_URL%/api/summary" >nul 2>&1
  if not errorlevel 1 goto ready
  timeout /t 1 /nobreak >nul
)

echo.
echo Voice Studio did not start within 60 seconds.
echo Check the "Voice Studio Server" window for details.
pause
exit /b 1

:ready
echo Voice Studio is ready.
start "" "%VOICE_STUDIO_URL%"
exit /b 0
