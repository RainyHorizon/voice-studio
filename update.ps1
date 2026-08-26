param(
  [string]$InstallDirectory = "",
  [switch]$CheckOnly,
  [switch]$Yes
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
$repository = "RainyHorizon/voice-studio"
$managedManifestName = ".voice-studio-files.txt"

function Write-Step([string]$Message) {
  Write-Host "[Voice Studio] $Message" -ForegroundColor Cyan
}

function Resolve-InstallDirectory([string]$Directory) {
  if ([string]::IsNullOrWhiteSpace($Directory)) {
    return [System.IO.Path]::GetFullPath($PSScriptRoot)
  }
  return [System.IO.Path]::GetFullPath($Directory)
}

function Read-Version([string]$Root) {
  $versionFile = Join-Path $Root "VERSION"
  if (-not (Test-Path -LiteralPath $versionFile -PathType Leaf)) { return $null }
  $version = (Get-Content -LiteralPath $versionFile -Raw -Encoding UTF8).Trim()
  if ($version -notmatch '^\d+\.\d+\.\d+$') { return $null }
  return $version
}

function Get-InstallType([string]$Root) {
  if ((Test-Path -LiteralPath (Join-Path $Root ".git")) -and
      (Test-Path -LiteralPath (Join-Path $Root "start.ps1") -PathType Leaf)) {
    return "git"
  }
  if (Test-Path -LiteralPath (Join-Path $Root "VoiceStudio.exe") -PathType Leaf) {
    return "portable"
  }
  if ((Test-Path -LiteralPath (Join-Path $Root "start.ps1") -PathType Leaf) -and
      (Test-Path -LiteralPath (Join-Path $Root "backend\app") -PathType Container)) {
    return "windows"
  }
  throw "无法识别当前安装类型。请确认更新文件位于 Voice Studio 的程序根目录。"
}

function Get-LatestRelease {
  $headers = @{
    Accept = "application/vnd.github+json"
    "User-Agent" = "Voice-Studio-Updater"
    "X-GitHub-Api-Version" = "2022-11-28"
  }
  return Invoke-RestMethod `
    -UseBasicParsing `
    -Uri "https://api.github.com/repos/$repository/releases/latest" `
    -Headers $headers `
    -Method Get
}

function Get-SafeRelativePath([string]$RelativePath) {
  $normalized = $RelativePath.Replace('/', '\').TrimStart('\')
  if ([string]::IsNullOrWhiteSpace($normalized) -or
      [System.IO.Path]::IsPathRooted($normalized) -or
      $normalized -match '(^|\\)\.\.(\\|$)' -or
      $normalized -match '^(?i)data(\\|$)') {
    throw "更新包包含不安全的文件路径：$RelativePath"
  }
  return $normalized
}

function Get-RelativeFileList([string]$Root) {
  $rootPrefix = [System.IO.Path]::GetFullPath($Root).TrimEnd('\') + '\'
  return @(
    Get-ChildItem -LiteralPath $Root -File -Recurse | ForEach-Object {
      $relative = $_.FullName.Substring($rootPrefix.Length)
      if ($relative -notmatch '^(?i)data(\\|$)') {
        Get-SafeRelativePath $relative
      }
    }
  )
}

function Read-ManagedManifest([string]$Root) {
  $manifestPath = Join-Path $Root $managedManifestName
  if (-not (Test-Path -LiteralPath $manifestPath -PathType Leaf)) { return @() }
  return @(
    Get-Content -LiteralPath $manifestPath -Encoding UTF8 |
      Where-Object { -not [string]::IsNullOrWhiteSpace($_) } |
      ForEach-Object { Get-SafeRelativePath $_ }
  )
}

function Assert-ZipEntriesAreSafe([string]$ArchivePath, [string]$Destination) {
  Add-Type -AssemblyName System.IO.Compression.FileSystem
  $destinationPrefix = [System.IO.Path]::GetFullPath($Destination).TrimEnd('\') + '\'
  $archive = [System.IO.Compression.ZipFile]::OpenRead($ArchivePath)
  try {
    foreach ($entry in $archive.Entries) {
      $entryName = $entry.FullName.Replace('/', '\')
      if ([string]::IsNullOrWhiteSpace($entryName)) { continue }
      if ([System.IO.Path]::IsPathRooted($entryName)) {
        throw "更新包包含绝对路径：$entryName"
      }
      $target = [System.IO.Path]::GetFullPath((Join-Path $Destination $entryName))
      if (-not $target.StartsWith($destinationPrefix, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "更新包包含越界路径：$entryName"
      }
    }
  } finally {
    $archive.Dispose()
  }
}

function Get-RunningVoiceStudio([string]$Root) {
  $rootPrefix = [System.IO.Path]::GetFullPath($Root).TrimEnd('\') + '\'
  $processes = @(
    Get-Process -Name "VoiceStudio" -ErrorAction SilentlyContinue | Where-Object {
      try {
        $_.Path -and $_.Path.StartsWith($rootPrefix, [System.StringComparison]::OrdinalIgnoreCase)
      } catch {
        $false
      }
    }
  )
  try {
    $escapedRoot = [regex]::Escape($rootPrefix.TrimEnd('\'))
    $processes += @(
      Get-CimInstance Win32_Process -ErrorAction Stop | Where-Object {
        $_.Name -match '^(?i)python(w)?\.exe$' -and
        $_.CommandLine -match $escapedRoot -and
        $_.CommandLine -match '(?i)uvicorn'
      }
    )
  } catch {
    # Process inspection can be unavailable under restricted Windows accounts.
  }
  return @($processes)
}

function Confirm-VoiceStudioStopped([string]$Root) {
  if ((Get-RunningVoiceStudio $Root).Count -eq 0) { return }
  Write-Host "请先关闭正在运行的 Voice Studio 启动窗口。" -ForegroundColor Yellow
  if (-not $Yes) { $null = Read-Host "关闭后按 Enter 继续" }
  if ((Get-RunningVoiceStudio $Root).Count -gt 0) {
    throw "Voice Studio 仍在运行。更新没有修改任何文件。"
  }
}

function Start-VoiceStudio([string]$Root) {
  if ($Yes) { return }
  $launcher = Join-Path $Root "启动 Voice Studio.bat"
  if (-not (Test-Path -LiteralPath $launcher -PathType Leaf)) { return }
  $answer = Read-Host "现在启动 Voice Studio？输入 Y 启动，输入其他内容退出"
  if ($answer -match '^(?i)y(es)?$') {
    Start-Process -FilePath "cmd.exe" -ArgumentList @("/c", "`"$launcher`"") -WorkingDirectory $Root
  }
}

function Invoke-Git([string]$GitPath, [string]$Root, [string[]]$Arguments) {
  $previousErrorAction = $ErrorActionPreference
  $ErrorActionPreference = "Continue"
  try {
    $output = @(& $GitPath -C $Root @Arguments 2>&1)
    $exitCode = $LASTEXITCODE
  } finally {
    $ErrorActionPreference = $previousErrorAction
  }
  if ($exitCode -ne 0) {
    $detail = ($output | Select-Object -Last 5) -join [Environment]::NewLine
    throw "Git 命令失败：git $($Arguments -join ' ')`n$detail"
  }
  return @($output)
}

function Update-GitCheckout([string]$Root) {
  $git = Get-Command git.exe -ErrorAction SilentlyContinue
  if (-not $git) { $git = Get-Command git -ErrorAction SilentlyContinue }
  if (-not $git) { throw "这是 Git 源码目录，但系统中没有可用的 Git。" }

  $remoteUrl = [string](Invoke-Git $git.Source $Root @("remote", "get-url", "origin") | Select-Object -First 1)
  if ($remoteUrl.Trim() -notmatch '^(?i)(https://github\.com/RainyHorizon/voice-studio(?:\.git)?|git@github\.com:RainyHorizon/voice-studio(?:\.git)?|ssh://git@github\.com/RainyHorizon/voice-studio(?:\.git)?)$') {
    throw "origin 不是 Voice Studio 官方仓库，更新器不会自动拉取：$($remoteUrl.Trim())"
  }

  $branch = ([string](Invoke-Git $git.Source $Root @("branch", "--show-current") | Select-Object -First 1)).Trim()
  if ([string]::IsNullOrWhiteSpace($branch)) {
    throw "当前 Git 仓库处于 detached HEAD 状态，请先切换到需要更新的分支。"
  }
  $upstream = ([string](Invoke-Git $git.Source $Root @("rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}") | Select-Object -First 1)).Trim()

  Write-Host "安装类型：Git 源码目录"
  Write-Host "当前分支：$branch"
  Write-Host "上游分支：$upstream"
  Write-Step "正在获取官方仓库更新信息..."
  $null = Invoke-Git $git.Source $Root @("fetch", "--prune", "origin")
  $counts = ([string](Invoke-Git $git.Source $Root @("rev-list", "--left-right", "--count", "HEAD...$upstream") | Select-Object -First 1)).Trim()
  if ($counts -notmatch '^(\d+)\s+(\d+)$') { throw "无法比较当前分支与上游分支。" }
  $ahead = [int]$Matches[1]
  $behind = [int]$Matches[2]

  if ($behind -eq 0) {
    if ($ahead -gt 0) {
      Write-Host "当前分支比上游多 $ahead 个本地提交，没有可拉取的更新。" -ForegroundColor Green
    } else {
      Write-Host "当前 Git 分支已经与上游保持一致。" -ForegroundColor Green
    }
    return
  }
  Write-Host "检测到上游有 $behind 个新提交。" -ForegroundColor Yellow
  if ($ahead -gt 0) {
    throw "当前分支与上游已经分叉，无法安全快进更新。请由开发者手动处理 Git 历史。"
  }
  if ($CheckOnly) { return }

  $changes = @(Invoke-Git $git.Source $Root @("status", "--porcelain", "--untracked-files=normal"))
  if ($changes.Count -gt 0) {
    throw "检测到未提交或未跟踪文件，已停止更新。请先提交、暂存或移走这些改动。"
  }
  if (-not $Yes) {
    $answer = Read-Host "输入 Y 将当前分支快进到 $upstream，输入其他内容取消"
    if ($answer -notmatch '^(?i)y(es)?$') {
      Write-Host "已取消更新。"
      return
    }
  }

  Confirm-VoiceStudioStopped $Root
  Write-Step "正在快进更新 Git 源码..."
  $pullOutput = Invoke-Git $git.Source $Root @("pull", "--ff-only")
  $pullOutput | ForEach-Object { Write-Host $_ }
  $commit = ([string](Invoke-Git $git.Source $Root @("rev-parse", "--short", "HEAD") | Select-Object -First 1)).Trim()
  Write-Host "Git 源码已更新，当前提交：$commit" -ForegroundColor Green
  Write-Host "下次启动时会自动检查前端与 Python 依赖。"
  Start-VoiceStudio $Root
}

function Install-ReleaseFiles([string]$PackageRoot, [string]$InstallRoot, [string]$BackupRoot, [string]$ExpectedVersion, [string]$InstallType) {
  $newFiles = @(Get-RelativeFileList $PackageRoot)
  $declaredFiles = @(Read-ManagedManifest $PackageRoot)
  $actualManagedFiles = @($newFiles | Where-Object { $_ -ne $managedManifestName } | Sort-Object -Unique)
  if ((Compare-Object $declaredFiles $actualManagedFiles).Count -gt 0) {
    throw "更新包的受管文件清单与实际内容不一致。"
  }

  $oldFiles = @(Read-ManagedManifest $InstallRoot)
  $backupCandidates = @($oldFiles + $newFiles | Sort-Object -Unique)
  foreach ($relative in $backupCandidates) {
    $safeRelative = Get-SafeRelativePath $relative
    $existingPath = Join-Path $InstallRoot $safeRelative
    if (Test-Path -LiteralPath $existingPath -PathType Leaf) {
      $backupPath = Join-Path $BackupRoot $safeRelative
      New-Item -ItemType Directory -Force -Path (Split-Path -Parent $backupPath) | Out-Null
      Copy-Item -LiteralPath $existingPath -Destination $backupPath -Force
    }
  }

  Write-Step "正在安装 $ExpectedVersion..."
  try {
    foreach ($relative in $newFiles) {
      $sourcePath = Join-Path $PackageRoot $relative
      $destinationPath = Join-Path $InstallRoot $relative
      New-Item -ItemType Directory -Force -Path (Split-Path -Parent $destinationPath) | Out-Null
      Copy-Item -LiteralPath $sourcePath -Destination $destinationPath -Force
    }

    $newFileSet = @{}
    foreach ($relative in $newFiles) { $newFileSet[$relative.ToLowerInvariant()] = $true }
    foreach ($relative in $oldFiles) {
      if (-not $newFileSet.ContainsKey($relative.ToLowerInvariant())) {
        $stalePath = Join-Path $InstallRoot $relative
        if (Test-Path -LiteralPath $stalePath -PathType Leaf) {
          Remove-Item -LiteralPath $stalePath -Force
        }
      }
    }

    $requiredExecutable = if ($InstallType -eq "portable") { "VoiceStudio.exe" } else { "start.ps1" }
    if ((Read-Version $InstallRoot) -ne $ExpectedVersion -or
        -not (Test-Path -LiteralPath (Join-Path $InstallRoot $requiredExecutable) -PathType Leaf)) {
      throw "安装后的文件验证失败。"
    }
  } catch {
    Write-Host "安装失败，正在恢复原程序文件..." -ForegroundColor Yellow
    foreach ($relative in $newFiles) {
      $destinationPath = Join-Path $InstallRoot $relative
      if (Test-Path -LiteralPath $destinationPath -PathType Leaf) {
        Remove-Item -LiteralPath $destinationPath -Force -ErrorAction SilentlyContinue
      }
    }
    Get-ChildItem -LiteralPath $BackupRoot -File -Recurse | ForEach-Object {
      $backupPrefix = [System.IO.Path]::GetFullPath($BackupRoot).TrimEnd('\') + '\'
      $relative = $_.FullName.Substring($backupPrefix.Length)
      $restorePath = Join-Path $InstallRoot $relative
      New-Item -ItemType Directory -Force -Path (Split-Path -Parent $restorePath) | Out-Null
      Copy-Item -LiteralPath $_.FullName -Destination $restorePath -Force
    }
    throw
  }
}

function Update-ReleasePackage([string]$Root, [string]$InstallType) {
  [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
  $typeLabel = if ($InstallType -eq "portable") { "Windows Portable" } else { "Windows 轻量版或源码 ZIP" }
  $assetSuffix = if ($InstallType -eq "portable") { "Windows-Portable.zip" } else { "Windows.zip" }
  Write-Host "安装类型：$typeLabel"
  Write-Step "正在查询 GitHub 最新正式版本..."
  $release = Get-LatestRelease
  if ($release.draft -or $release.prerelease) {
    throw "GitHub 返回的版本不是正式 Release，已停止更新。"
  }

  $latestVersion = ([string]$release.tag_name).Trim().TrimStart('v')
  if ($latestVersion -notmatch '^\d+\.\d+\.\d+$') {
    throw "无法识别最新版本号：$($release.tag_name)"
  }
  $archiveName = "Voice-Studio-$latestVersion-$assetSuffix"
  $checksumName = "$archiveName.sha256"
  $archiveAsset = @($release.assets) | Where-Object { $_.name -eq $archiveName } | Select-Object -First 1
  $checksumAsset = @($release.assets) | Where-Object { $_.name -eq $checksumName } | Select-Object -First 1
  if (-not $archiveAsset -or -not $checksumAsset) {
    throw "最新 Release 缺少 $archiveName 或 SHA256 校验文件，请等待发布流程完成后重试。"
  }

  $trustedPrefix = "https://github.com/$repository/releases/download/"
  foreach ($asset in @($archiveAsset, $checksumAsset)) {
    if (-not ([string]$asset.browser_download_url).StartsWith($trustedPrefix, [System.StringComparison]::OrdinalIgnoreCase)) {
      throw "Release 资源地址不属于官方仓库，已停止下载。"
    }
  }

  $currentVersion = Read-Version $Root
  $currentLabel = if ($currentVersion) { $currentVersion } else { "未知（旧版未记录版本号）" }
  Write-Host "当前版本：$currentLabel"
  Write-Host "最新版本：$latestVersion"
  if ($currentVersion -and ([version]$currentVersion -ge [version]$latestVersion)) {
    Write-Host "当前版本不低于 GitHub 最新正式版，无需更新。" -ForegroundColor Green
    return
  }
  if ($CheckOnly) {
    Write-Host "检测到可用更新：$latestVersion" -ForegroundColor Yellow
    return
  }

  if (-not $Yes) {
    Write-Host "更新会替换程序文件，但会保留 data、API Key、虚拟环境和其他用户文件。"
    $answer = Read-Host "输入 Y 确认更新，输入其他内容取消"
    if ($answer -notmatch '^(?i)y(es)?$') {
      Write-Host "已取消更新。"
      return
    }
  }
  Confirm-VoiceStudioStopped $Root

  $temporaryRoot = Join-Path ([System.IO.Path]::GetTempPath()) ("VoiceStudio-Update-" + [guid]::NewGuid().ToString("N"))
  $downloadRoot = Join-Path $temporaryRoot "download"
  $extractRoot = Join-Path $temporaryRoot "extract"
  $backupRoot = Join-Path $temporaryRoot "backup"
  New-Item -ItemType Directory -Force -Path $downloadRoot, $extractRoot, $backupRoot | Out-Null
  $archivePath = Join-Path $downloadRoot $archiveName
  $checksumPath = Join-Path $downloadRoot $checksumName

  try {
    Write-Step "正在下载 $archiveName..."
    Invoke-WebRequest -UseBasicParsing -Uri $archiveAsset.browser_download_url -OutFile $archivePath
    Invoke-WebRequest -UseBasicParsing -Uri $checksumAsset.browser_download_url -OutFile $checksumPath
    $checksumText = Get-Content -LiteralPath $checksumPath -Raw -Encoding ASCII
    if ($checksumText -notmatch '(?i)\b([0-9a-f]{64})\b') { throw "SHA256 校验文件格式无效。" }
    $expectedHash = $Matches[1].ToUpperInvariant()
    $actualHash = (Get-FileHash -LiteralPath $archivePath -Algorithm SHA256).Hash.ToUpperInvariant()
    if ($actualHash -ne $expectedHash) { throw "下载文件的 SHA256 不匹配，已停止更新。" }
    Write-Host "SHA256 校验通过。" -ForegroundColor Green

    Assert-ZipEntriesAreSafe $archivePath $extractRoot
    Expand-Archive -LiteralPath $archivePath -DestinationPath $extractRoot -Force
    $markerName = if ($InstallType -eq "portable") { "VoiceStudio.exe" } else { "start.ps1" }
    $packageMarkers = @(Get-ChildItem -LiteralPath $extractRoot -Filter $markerName -File -Recurse)
    if ($packageMarkers.Count -ne 1) { throw "更新包结构无效：无法唯一确定 $markerName。" }
    $packageRoot = $packageMarkers[0].Directory.FullName
    if ((Read-Version $packageRoot) -ne $latestVersion) { throw "更新包版本与 Release 标签不一致。" }

    $requiredPaths = if ($InstallType -eq "portable") {
      @("VoiceStudio.exe", "frontend\dist\index.html", "tools\ffmpeg.exe", "tools\ffprobe.exe", $managedManifestName)
    } else {
      @("start.ps1", "backend\app\main.py", "backend\requirements.txt", "frontend\dist\index.html", $managedManifestName)
    }
    foreach ($requiredPath in $requiredPaths) {
      if (-not (Test-Path -LiteralPath (Join-Path $packageRoot $requiredPath) -PathType Leaf)) {
        throw "更新包不完整，缺少：$requiredPath"
      }
    }

    Install-ReleaseFiles $packageRoot $Root $backupRoot $latestVersion $InstallType
    Write-Host "Voice Studio 已更新到 $latestVersion。" -ForegroundColor Green
    Write-Host "本地 data、系统凭据和非程序文件均已保留。"
    if ($InstallType -eq "windows") {
      Write-Host "下次启动时会自动检查 Python 依赖。"
    }
    Start-VoiceStudio $Root
  } finally {
    if ($temporaryRoot -and (Test-Path -LiteralPath $temporaryRoot)) {
      Remove-Item -LiteralPath $temporaryRoot -Recurse -Force -ErrorAction SilentlyContinue
    }
  }
}

$installRoot = Resolve-InstallDirectory $InstallDirectory
try {
  $installType = Get-InstallType $installRoot
  if ($installType -eq "git") {
    Update-GitCheckout $installRoot
  } else {
    Update-ReleasePackage $installRoot $installType
  }
} catch {
  Write-Host ""
  Write-Host "更新失败：$($_.Exception.Message)" -ForegroundColor Red
  Write-Host "更新器不会主动删除 data 目录。"
  exit 1
}
