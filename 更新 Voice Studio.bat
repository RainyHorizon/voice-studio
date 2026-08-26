@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"

if not exist "%~dp0update.ps1" (
  echo 更新组件不完整，缺少 update.ps1。
  echo 请从 Voice Studio 官方 GitHub Releases 重新下载 Windows Portable 版本。
  pause
  exit /b 1
)

set "VOICE_STUDIO_UPDATER=%TEMP%\VoiceStudio-Updater-%RANDOM%-%RANDOM%.ps1"
copy /y "%~dp0update.ps1" "%VOICE_STUDIO_UPDATER%" >nul
if errorlevel 1 (
  echo 无法创建临时更新程序，请检查 TEMP 目录是否可写。
  pause
  exit /b 1
)

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%VOICE_STUDIO_UPDATER%" -InstallDirectory "%~dp0."
set "VOICE_STUDIO_UPDATE_EXIT=%ERRORLEVEL%"
del /q "%VOICE_STUDIO_UPDATER%" >nul 2>&1

if not "%VOICE_STUDIO_UPDATE_EXIT%"=="0" (
  echo.
  echo 更新未完成，现有数据不会被删除。
)
pause
exit /b %VOICE_STUDIO_UPDATE_EXIT%
