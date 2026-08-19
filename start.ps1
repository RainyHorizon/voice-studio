$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$backendRoot = Join-Path $projectRoot "backend"
$frontendRoot = Join-Path $projectRoot "frontend"
if (-not (Get-Command python -ErrorAction SilentlyContinue)) { throw "未找到 Python" }
if (-not (Get-Command npm -ErrorAction SilentlyContinue)) { throw "未找到 npm" }
if (-not (Test-Path (Join-Path $backendRoot ".venv\Scripts\python.exe"))) {
  python -m venv (Join-Path $backendRoot ".venv")
  & (Join-Path $backendRoot ".venv\Scripts\python.exe") -m pip install -r (Join-Path $backendRoot "requirements.txt")
}
if (-not (Test-Path (Join-Path $frontendRoot "node_modules"))) {
  Push-Location $frontendRoot
  npm install
  Pop-Location
}
Push-Location $frontendRoot
npm run build
Pop-Location
Write-Host "Voice Studio: http://127.0.0.1:8765" -ForegroundColor Green
& (Join-Path $backendRoot ".venv\Scripts\python.exe") -m uvicorn app.main:app --app-dir $backendRoot --host 127.0.0.1 --port 8765
