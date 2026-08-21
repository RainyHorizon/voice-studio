@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"

"%~dp0VoiceStudio.exe"
exit /b %errorlevel%
