param(
  [string]$Version = "",
  [string]$FfmpegBinDirectory = ""
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$backendRoot = Join-Path $projectRoot "backend"
$frontendRoot = Join-Path $projectRoot "frontend"
$outputRoot = Join-Path $projectRoot "output"
$releaseRoot = Join-Path $outputRoot "releases"
$buildRoot = Join-Path $outputRoot "portable-build"
$pythonExecutable = Join-Path $backendRoot ".venv\Scripts\python.exe"
$buildRequirements = Join-Path $backendRoot "requirements-build.txt"

function Assert-ChildPath([string]$Path, [string]$Parent) {
  $resolvedParent = [System.IO.Path]::GetFullPath($Parent).TrimEnd('\') + '\'
  $resolvedPath = [System.IO.Path]::GetFullPath($Path)
  if (-not $resolvedPath.StartsWith($resolvedParent, [System.StringComparison]::OrdinalIgnoreCase)) {
    throw "构建目录不在项目 output 目录中，已停止：$resolvedPath"
  }
}

function Find-FfmpegLicense([string]$BinDirectory) {
  $candidateRoot = Split-Path -Parent $BinDirectory
  foreach ($name in @("LICENSE", "COPYING.GPLv3", "COPYING.GPLv2", "COPYING.LGPLv3", "COPYING.LGPLv2.1")) {
    $candidate = Join-Path $candidateRoot $name
    if (Test-Path -LiteralPath $candidate -PathType Leaf) { return $candidate }
  }
  throw "未在 FFmpeg 目录中找到许可证文件。请使用包含 LICENSE/COPYING 的完整 FFmpeg 发布目录。"
}

if ([string]::IsNullOrWhiteSpace($Version)) {
  $package = Get-Content -LiteralPath (Join-Path $frontendRoot "package.json") -Raw -Encoding UTF8 | ConvertFrom-Json
  $Version = [string]$package.version
}
if ($Version -notmatch '^[0-9A-Za-z][0-9A-Za-z._-]*$') {
  throw "版本号只能包含字母、数字、点、下划线和连字符。"
}

$packageName = "Voice-Studio-$Version-Windows-Portable"
$stagePath = Join-Path $buildRoot $packageName
$pyinstallerDist = Join-Path $buildRoot "pyinstaller-dist"
$pyinstallerWork = Join-Path $buildRoot "pyinstaller-work"
$archivePath = Join-Path $releaseRoot "$packageName.zip"
Assert-ChildPath $stagePath $outputRoot
Assert-ChildPath $pyinstallerDist $outputRoot
Assert-ChildPath $pyinstallerWork $outputRoot

if (-not (Test-Path -LiteralPath $pythonExecutable -PathType Leaf)) {
  $pythonCommand = Get-Command python -ErrorAction SilentlyContinue
  if (-not $pythonCommand) { throw "未找到用于构建的 Python 3.11 或更高版本。" }
  $pythonVersion = & $pythonCommand.Source -c "import sys; print('.'.join(map(str, sys.version_info[:3])))"
  if ([version]$pythonVersion -lt [version]"3.11") { throw "构建 Python 版本必须为 3.11 或更高版本。" }
  & $pythonCommand.Source -m venv (Join-Path $backendRoot ".venv")
  if ($LASTEXITCODE -ne 0) { throw "创建构建虚拟环境失败。" }
}

if ([string]::IsNullOrWhiteSpace($FfmpegBinDirectory)) {
  $preferredFfmpeg = "C:\Program Files\FFmpeg\bin"
  if (Test-Path -LiteralPath (Join-Path $preferredFfmpeg "ffmpeg.exe")) {
    $FfmpegBinDirectory = $preferredFfmpeg
  } else {
    $ffmpegCommand = Get-Command ffmpeg.exe -ErrorAction SilentlyContinue
    if (-not $ffmpegCommand) { throw "未找到 FFmpeg。可以通过 -FfmpegBinDirectory 指定其 bin 目录。" }
    $FfmpegBinDirectory = Split-Path -Parent $ffmpegCommand.Source
  }
}
$ffmpeg = Join-Path $FfmpegBinDirectory "ffmpeg.exe"
$ffprobe = Join-Path $FfmpegBinDirectory "ffprobe.exe"
if (-not (Test-Path -LiteralPath $ffmpeg -PathType Leaf) -or -not (Test-Path -LiteralPath $ffprobe -PathType Leaf)) {
  throw "指定目录中必须同时包含 ffmpeg.exe 和 ffprobe.exe。"
}
$ffmpegLicense = Find-FfmpegLicense $FfmpegBinDirectory
$ffmpegReadme = Join-Path (Split-Path -Parent $FfmpegBinDirectory) "README.txt"

Write-Host "正在构建前端..." -ForegroundColor Cyan
Push-Location $frontendRoot
try {
  if (-not (Test-Path (Join-Path $frontendRoot "node_modules"))) { npm install }
  npm run build
  if ($LASTEXITCODE -ne 0) { throw "前端构建失败。" }
} finally {
  Pop-Location
}

Write-Host "正在准备独立 Python 运行时..." -ForegroundColor Cyan
& $pythonExecutable -m pip install -r $buildRequirements
if ($LASTEXITCODE -ne 0) { throw "便携版构建依赖安装失败。" }

New-Item -ItemType Directory -Force -Path $releaseRoot | Out-Null
New-Item -ItemType Directory -Force -Path $buildRoot | Out-Null
foreach ($path in @($stagePath, $pyinstallerDist, $pyinstallerWork)) {
  if (Test-Path -LiteralPath $path) { Remove-Item -LiteralPath $path -Recurse -Force }
}

Write-Host "正在生成 VoiceStudio.exe..." -ForegroundColor Cyan
& $pythonExecutable -m PyInstaller `
  --noconfirm `
  --clean `
  --onedir `
  --name VoiceStudio `
  --paths $backendRoot `
  --collect-all keyring `
  --collect-all dashscope `
  --collect-submodules uvicorn `
  --collect-submodules websockets `
  --distpath $pyinstallerDist `
  --workpath $pyinstallerWork `
  --specpath $buildRoot `
  (Join-Path $backendRoot "portable_main.py")
if ($LASTEXITCODE -ne 0) { throw "PyInstaller 构建失败。" }

$builtApplication = Join-Path $pyinstallerDist "VoiceStudio"
if (-not (Test-Path -LiteralPath (Join-Path $builtApplication "VoiceStudio.exe") -PathType Leaf)) {
  throw "PyInstaller 未生成 VoiceStudio.exe。"
}
Move-Item -LiteralPath $builtApplication -Destination $stagePath

New-Item -ItemType Directory -Force -Path (Join-Path $stagePath "frontend") | Out-Null
Copy-Item -LiteralPath (Join-Path $frontendRoot "dist") -Destination (Join-Path $stagePath "frontend\dist") -Recurse
New-Item -ItemType Directory -Force -Path (Join-Path $stagePath "data\audio") | Out-Null
New-Item -ItemType File -Force -Path (Join-Path $stagePath "data\audio\.gitkeep") | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $stagePath "tools") | Out-Null
Copy-Item -LiteralPath $ffmpeg -Destination (Join-Path $stagePath "tools\ffmpeg.exe")
Copy-Item -LiteralPath $ffprobe -Destination (Join-Path $stagePath "tools\ffprobe.exe")
Copy-Item -LiteralPath (Join-Path $projectRoot "portable\启动 Voice Studio.bat") -Destination (Join-Path $stagePath "启动 Voice Studio.bat")
Copy-Item -LiteralPath (Join-Path $projectRoot "PORTABLE_README.md") -Destination (Join-Path $stagePath "便携版说明.md")
Copy-Item -LiteralPath (Join-Path $projectRoot "README.md") -Destination (Join-Path $stagePath "README.md")
Copy-Item -LiteralPath (Join-Path $projectRoot "LICENSE") -Destination (Join-Path $stagePath "LICENSE")
Copy-Item -LiteralPath (Join-Path $projectRoot "THIRD_PARTY_NOTICES.md") -Destination (Join-Path $stagePath "THIRD_PARTY_NOTICES.md")
New-Item -ItemType Directory -Force -Path (Join-Path $stagePath "third_party\ffmpeg") | Out-Null
Copy-Item -LiteralPath $ffmpegLicense -Destination (Join-Path $stagePath "third_party\ffmpeg\LICENSE")
if (Test-Path -LiteralPath $ffmpegReadme -PathType Leaf) {
  Copy-Item -LiteralPath $ffmpegReadme -Destination (Join-Path $stagePath "third_party\ffmpeg\README.txt")
} else {
  & $ffmpeg -version 2>&1 | Set-Content -LiteralPath (Join-Path $stagePath "third_party\ffmpeg\README.txt") -Encoding UTF8
}

$forbiddenFiles = Get-ChildItem -LiteralPath $stagePath -File -Recurse | Where-Object {
  $_.Name -in @("gateway.json", ".env") -or $_.Extension -in @(".db", ".sqlite", ".sqlite3", ".log", ".pyc", ".wav", ".mp3", ".flac", ".ogg", ".m4a")
}
if ($forbiddenFiles) {
  throw "便携版目录包含不应发布的本地文件：$($forbiddenFiles.FullName -join ', ')"
}

Write-Host "正在检查便携版..." -ForegroundColor Cyan
& (Join-Path $stagePath "VoiceStudio.exe") --check --no-browser
if ($LASTEXITCODE -ne 0) { throw "便携版运行检查失败。" }

if (Test-Path -LiteralPath $archivePath) { Remove-Item -LiteralPath $archivePath -Force }
Compress-Archive -LiteralPath $stagePath -DestinationPath $archivePath -CompressionLevel Optimal

$archive = Get-Item -LiteralPath $archivePath
$hash = Get-FileHash -LiteralPath $archivePath -Algorithm SHA256
$checksumPath = "$archivePath.sha256"
Set-Content -LiteralPath $checksumPath -Value "$($hash.Hash)  $($archive.Name)" -Encoding Ascii
Write-Host "Windows 便携版已生成：" -ForegroundColor Green
Write-Host $archive.FullName
Write-Host ("大小：{0:N2} MB" -f ($archive.Length / 1MB))
Write-Host "SHA256：$($hash.Hash)"
Write-Host "校验文件：$checksumPath"
