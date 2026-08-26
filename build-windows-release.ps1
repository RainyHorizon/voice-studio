param(
  [string]$Version = ""
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$frontendRoot = Join-Path $projectRoot "frontend"
$outputRoot = Join-Path $projectRoot "output"
$releaseRoot = Join-Path $outputRoot "releases"
$buildRoot = Join-Path $outputRoot "release-build"

if ([string]::IsNullOrWhiteSpace($Version)) {
  $package = Get-Content -LiteralPath (Join-Path $frontendRoot "package.json") -Raw -Encoding UTF8 | ConvertFrom-Json
  $Version = [string]$package.version
}
if ($Version -notmatch '^[0-9A-Za-z][0-9A-Za-z._-]*$') {
  throw "版本号只能包含字母、数字、点、下划线和连字符。"
}

$packageName = "Voice-Studio-$Version-Windows"
$stagePath = Join-Path $buildRoot $packageName
$archivePath = Join-Path $releaseRoot "$packageName.zip"
$resolvedOutput = [System.IO.Path]::GetFullPath($outputRoot).TrimEnd('\') + '\'
$resolvedStage = [System.IO.Path]::GetFullPath($stagePath)
if (-not $resolvedStage.StartsWith($resolvedOutput, [System.StringComparison]::OrdinalIgnoreCase)) {
  throw "发布暂存目录不在项目 output 目录中，已停止。"
}

Write-Host "正在构建前端..." -ForegroundColor Cyan
Push-Location $frontendRoot
try {
  if (-not (Test-Path (Join-Path $frontendRoot "node_modules"))) { npm install }
  npm run build
  if ($LASTEXITCODE -ne 0) { throw "前端构建失败。" }
} finally {
  Pop-Location
}

New-Item -ItemType Directory -Force -Path $releaseRoot | Out-Null
New-Item -ItemType Directory -Force -Path $buildRoot | Out-Null
if (Test-Path -LiteralPath $stagePath) { Remove-Item -LiteralPath $stagePath -Recurse -Force }
New-Item -ItemType Directory -Force -Path $stagePath | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $stagePath "backend") | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $stagePath "frontend") | Out-Null

Copy-Item -LiteralPath (Join-Path $projectRoot "backend\app") -Destination (Join-Path $stagePath "backend\app") -Recurse
Copy-Item -LiteralPath (Join-Path $projectRoot "backend\requirements.txt") -Destination (Join-Path $stagePath "backend\requirements.txt")
Copy-Item -LiteralPath (Join-Path $projectRoot "frontend\dist") -Destination (Join-Path $stagePath "frontend\dist") -Recurse
Copy-Item -LiteralPath (Join-Path $projectRoot "start.ps1") -Destination (Join-Path $stagePath "start.ps1")
Copy-Item -LiteralPath (Join-Path $projectRoot "启动 Voice Studio.bat") -Destination (Join-Path $stagePath "启动 Voice Studio.bat")
Copy-Item -LiteralPath (Join-Path $projectRoot "更新 Voice Studio.bat") -Destination (Join-Path $stagePath "更新 Voice Studio.bat")
Copy-Item -LiteralPath (Join-Path $projectRoot "update.ps1") -Destination (Join-Path $stagePath "update.ps1")
Copy-Item -LiteralPath (Join-Path $projectRoot "README.md") -Destination (Join-Path $stagePath "README.md")
Copy-Item -LiteralPath (Join-Path $projectRoot "LICENSE") -Destination (Join-Path $stagePath "LICENSE")
New-Item -ItemType Directory -Force -Path (Join-Path $stagePath "data\audio") | Out-Null
New-Item -ItemType File -Force -Path (Join-Path $stagePath "data\audio\.gitkeep") | Out-Null

Get-ChildItem -LiteralPath $stagePath -Directory -Recurse -Filter "__pycache__" | Remove-Item -Recurse -Force
Set-Content -LiteralPath (Join-Path $stagePath "VERSION") -Value $Version -Encoding Ascii
$managedManifestPath = Join-Path $stagePath ".voice-studio-files.txt"
$stagePrefix = [System.IO.Path]::GetFullPath($stagePath).TrimEnd('\') + '\'
$managedFiles = Get-ChildItem -LiteralPath $stagePath -File -Recurse | ForEach-Object {
  $relative = $_.FullName.Substring($stagePrefix.Length)
  if ($relative -notmatch '^(?i)data(\\|$)' -and $relative -ne ".voice-studio-files.txt") {
    $relative.Replace('\', '/')
  }
} | Sort-Object
Set-Content -LiteralPath $managedManifestPath -Value $managedFiles -Encoding UTF8

$forbiddenFiles = Get-ChildItem -LiteralPath $stagePath -File -Recurse | Where-Object {
  $_.Name -in @("gateway.json", ".env") -or $_.Extension -in @(".db", ".sqlite", ".sqlite3", ".log", ".pyc")
}
if ($forbiddenFiles) {
  throw "发布目录包含不应打包的本地文件：$($forbiddenFiles.FullName -join ', ')"
}

if (Test-Path -LiteralPath $archivePath) { Remove-Item -LiteralPath $archivePath -Force }
Compress-Archive -LiteralPath $stagePath -DestinationPath $archivePath -CompressionLevel Optimal
Remove-Item -LiteralPath $stagePath -Recurse -Force

$archive = Get-Item -LiteralPath $archivePath
$hash = Get-FileHash -LiteralPath $archivePath -Algorithm SHA256
$checksumPath = "$archivePath.sha256"
Set-Content -LiteralPath $checksumPath -Value "$($hash.Hash)  $($archive.Name)" -Encoding Ascii

Write-Host "Windows Release 已生成：" -ForegroundColor Green
Write-Host $archivePath
Write-Host "SHA256：$($hash.Hash)"
Write-Host "校验文件：$checksumPath"
