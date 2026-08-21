param(
  [ValidateRange(1, 65535)]
  [int]$Port = 0,
  [switch]$OpenBrowser,
  [switch]$PauseOnError
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$backendRoot = Join-Path $projectRoot "backend"
$frontendRoot = Join-Path $projectRoot "frontend"
$dataRoot = Join-Path $projectRoot "data"
$frontendIndex = Join-Path $frontendRoot "dist\index.html"
$pythonExecutable = Join-Path $backendRoot ".venv\Scripts\python.exe"
$requirementsFile = Join-Path $backendRoot "requirements.txt"
$requirementsStamp = Join-Path $backendRoot ".venv\.requirements.sha256"

function Write-Step([string]$Message) {
  Write-Host "[Voice Studio] $Message" -ForegroundColor Cyan
}

function Test-PortAvailable([int]$Candidate) {
  $listener = $null
  try {
    $listener = [System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Loopback, $Candidate)
    $listener.Start()
    return $true
  } catch {
    return $false
  } finally {
    if ($null -ne $listener) { $listener.Stop() }
  }
}

function Test-VoiceStudio([int]$Candidate) {
  try {
    $response = Invoke-RestMethod -Uri "http://127.0.0.1:$Candidate/api/summary" -TimeoutSec 2
    return $response.application -eq "voice-studio"
  } catch {
    return $false
  }
}

function Get-CommandVersion([string]$Command, [string[]]$Arguments) {
  $resolved = Get-Command $Command -ErrorAction SilentlyContinue
  if (-not $resolved) { throw "未找到 $Command，请先安装并加入系统 Path。" }
  $output = & $resolved.Source @Arguments 2>&1 | Select-Object -First 1
  if ($LASTEXITCODE -ne 0) { throw "$Command 无法正常运行。" }
  return [string]$output
}

try {
  Write-Host ""
  Write-Host "Voice Studio Windows 启动检查" -ForegroundColor Green
  Write-Host "--------------------------------"

  $pythonCommand = Get-Command python -ErrorAction SilentlyContinue
  if (-not $pythonCommand) { throw "未找到 Python。请安装 Python 3.11 或更高版本，并勾选 Add Python to PATH。" }
  $pythonVersion = & $pythonCommand.Source -c "import sys; print('.'.join(map(str, sys.version_info[:3])))"
  if ($LASTEXITCODE -ne 0) { throw "Python 无法正常运行。" }
  if ([version]$pythonVersion -lt [version]"3.11") { throw "Python 版本为 $pythonVersion，需要 Python 3.11 或更高版本。" }
  Write-Step "Python $pythonVersion 可用"

  $ffmpegVersion = Get-CommandVersion "ffmpeg" @("-version")
  $ffprobeVersion = Get-CommandVersion "ffprobe" @("-version")
  Write-Step ($ffmpegVersion -replace "^ffmpeg version\s+", "FFmpeg ")
  Write-Step ($ffprobeVersion -replace "^ffprobe version\s+", "FFprobe ")

  New-Item -ItemType Directory -Force -Path $dataRoot | Out-Null
  $writeProbe = Join-Path $dataRoot ".write-test-$PID"
  Set-Content -LiteralPath $writeProbe -Value "ok" -Encoding Ascii
  Remove-Item -LiteralPath $writeProbe -Force
  Write-Step "数据目录可写"

  $portWasExplicit = $PSBoundParameters.ContainsKey("Port") -or -not [string]::IsNullOrWhiteSpace($env:VOICE_STUDIO_PORT)
  if ($Port -eq 0 -and -not [string]::IsNullOrWhiteSpace($env:VOICE_STUDIO_PORT)) {
    if (-not [int]::TryParse($env:VOICE_STUDIO_PORT, [ref]$Port) -or $Port -lt 1 -or $Port -gt 65535) {
      throw "VOICE_STUDIO_PORT 必须是 1 到 65535 之间的端口号。"
    }
  }
  if ($Port -eq 0) { $Port = 8765 }

  if (Test-VoiceStudio $Port) {
    $existingUrl = "http://127.0.0.1:$Port"
    Write-Host "Voice Studio 已在运行：$existingUrl" -ForegroundColor Green
    if ($OpenBrowser) { Start-Process $existingUrl }
    exit 0
  }
  if (-not (Test-PortAvailable $Port)) {
    if ($portWasExplicit) { throw "端口 $Port 已被其他程序占用。请关闭占用程序，或使用 .\start.ps1 -Port 8766。" }
    $availablePort = 8766..8790 | Where-Object { Test-PortAvailable $_ } | Select-Object -First 1
    if (-not $availablePort) { throw "端口 8765–8790 均不可用，请关闭占用端口的程序后重试。" }
    Write-Host "[Voice Studio] 端口 8765 已被占用，自动改用 $availablePort。" -ForegroundColor Yellow
    $Port = $availablePort
  } else {
    Write-Step "端口 $Port 可用"
  }
  $env:VOICE_STUDIO_PORT = [string]$Port

  $needsFrontendBuild = -not (Test-Path $frontendIndex)
  $frontendSource = Join-Path $frontendRoot "src"
  if (-not $needsFrontendBuild -and (Test-Path $frontendSource)) {
    $latestSource = Get-ChildItem -Path $frontendSource -File -Recurse |
      Sort-Object LastWriteTimeUtc -Descending |
      Select-Object -First 1
    if ($latestSource -and $latestSource.LastWriteTimeUtc -gt (Get-Item $frontendIndex).LastWriteTimeUtc) {
      $needsFrontendBuild = $true
    }
  }
  if ($needsFrontendBuild) {
    $nodeVersion = Get-CommandVersion "node" @("--version")
    $null = Get-CommandVersion "npm" @("--version")
    Write-Step "Node.js $nodeVersion 可用，正在准备前端"
    Push-Location $frontendRoot
    try {
      if (-not (Test-Path (Join-Path $frontendRoot "node_modules"))) { npm install }
      npm run build
      if ($LASTEXITCODE -ne 0) { throw "前端构建失败。" }
    } finally {
      Pop-Location
    }
  } else {
    Write-Step "已找到预构建前端，无需 Node.js"
  }

  if (-not (Test-Path $pythonExecutable)) {
    Write-Step "首次运行，正在创建 Python 虚拟环境"
    & $pythonCommand.Source -m venv (Join-Path $backendRoot ".venv")
    if ($LASTEXITCODE -ne 0) { throw "Python 虚拟环境创建失败。" }
  }
  $requirementsHash = (Get-FileHash -LiteralPath $requirementsFile -Algorithm SHA256).Hash
  $installedHash = if (Test-Path $requirementsStamp) { (Get-Content -LiteralPath $requirementsStamp -Raw).Trim() } else { "" }
  if ($requirementsHash -ne $installedHash) {
    Write-Step "正在安装或更新后端依赖"
    & $pythonExecutable -m pip install -r $requirementsFile
    if ($LASTEXITCODE -ne 0) { throw "Python 依赖安装失败，请检查网络后重试。" }
    Set-Content -LiteralPath $requirementsStamp -Value $requirementsHash -Encoding Ascii
  } else {
    Write-Step "后端依赖已就绪"
  }

  $keyringBackend = & $pythonExecutable -c "import keyring; keyring.get_password('VoiceStudio.ProviderAccount', '__healthcheck__'); print(type(keyring.get_keyring()).__name__)"
  if ($LASTEXITCODE -ne 0) { throw "Windows Credential Manager 无法访问，请确认当前 Windows 用户配置正常。" }
  Write-Step "凭据存储可用（$keyringBackend）"

  $voiceStudioUrl = "http://127.0.0.1:$Port"
  if ($OpenBrowser) {
    $null = Start-Job -ScriptBlock {
      param($Url)
      for ($attempt = 0; $attempt -lt 90; $attempt += 1) {
        try {
          Invoke-WebRequest -UseBasicParsing -Uri "$Url/api/summary" -TimeoutSec 1 | Out-Null
          Start-Process $Url
          break
        } catch {
          Start-Sleep -Seconds 1
        }
      }
    } -ArgumentList $voiceStudioUrl
  }
  Write-Host ""
  Write-Host "Voice Studio 已准备完成：$voiceStudioUrl" -ForegroundColor Green
  Write-Host "关闭此窗口即可停止服务。" -ForegroundColor DarkGray
  & $pythonExecutable -m uvicorn app.main:app --app-dir $backendRoot --host 127.0.0.1 --port $Port
} catch {
  Write-Host ""
  Write-Host "Voice Studio 启动失败" -ForegroundColor Red
  Write-Host $_.Exception.Message -ForegroundColor Yellow
  Write-Host ""
  Write-Host "修复后重新双击“启动 Voice Studio.bat”。" -ForegroundColor DarkGray
  if ($PauseOnError) { Read-Host "按 Enter 键关闭窗口" | Out-Null }
  exit 1
}
