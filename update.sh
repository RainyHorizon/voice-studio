#!/usr/bin/env bash
set -Eeuo pipefail

REPOSITORY="RainyHorizon/voice-studio"
MANIFEST_NAME=".voice-studio-files.txt"

# Run from a temporary copy so a release update can safely replace update.sh.
if [[ "${VOICE_STUDIO_UPDATER_TEMP:-0}" != "1" ]]; then
  original_dir="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
  temporary_script="$(mktemp "${TMPDIR:-/tmp}/voice-studio-updater.XXXXXX")"
  cp "$0" "$temporary_script"
  chmod +x "$temporary_script"
  VOICE_STUDIO_UPDATER_TEMP=1 \
  VOICE_STUDIO_INSTALL_DIR="$original_dir" \
  VOICE_STUDIO_TEMP_SCRIPT="$temporary_script" \
    exec bash "$temporary_script" "$@"
fi

INSTALL_DIR="$(CDPATH= cd -- "${VOICE_STUDIO_INSTALL_DIR:?Missing install directory}" && pwd)"
CHECK_ONLY=0
ASSUME_YES=0
UPDATE_TEMP_ROOT=""

log() { printf '[Voice Studio] %s\n' "$1"; }
fail() { printf '\n更新失败：%s\n更新器不会主动删除 data 目录。\n' "$1" >&2; exit 1; }

cleanup() {
  if [[ -n "$UPDATE_TEMP_ROOT" && -d "$UPDATE_TEMP_ROOT" ]]; then
    rm -rf "$UPDATE_TEMP_ROOT"
  fi
  if [[ -n "${VOICE_STUDIO_TEMP_SCRIPT:-}" && -f "${VOICE_STUDIO_TEMP_SCRIPT:-}" ]]; then
    rm -f "$VOICE_STUDIO_TEMP_SCRIPT"
  fi
}
trap cleanup EXIT

usage() {
  cat <<'EOF'
用法：bash update.sh [选项]

选项：
  --check    只检查更新，不修改程序文件
  --yes      跳过确认提示，用于自动化环境
  --help     显示帮助
EOF
}

while (($# > 0)); do
  case "$1" in
    --check) CHECK_ONLY=1; shift ;;
    --yes) ASSUME_YES=1; shift ;;
    --help|-h) usage; exit 0 ;;
    *) fail "未知选项：$1。运行 bash update.sh --help 查看用法。" ;;
  esac
done

confirm() {
  local prompt="$1"
  ((ASSUME_YES)) && return 0
  local answer=""
  read -r -p "$prompt" answer
  [[ "$answer" =~ ^[Yy]([Ee][Ss])?$ ]]
}

voice_studio_is_running() {
  command -v pgrep >/dev/null 2>&1 || return 1
  pgrep -f "$INSTALL_DIR/backend/.venv/bin/python.*uvicorn" >/dev/null 2>&1
}

require_stopped() {
  if voice_studio_is_running; then
    fail "Voice Studio 仍在运行。请先关闭启动终端，再重新执行更新。"
  fi
}

find_python() {
  if command -v python3 >/dev/null 2>&1; then
    command -v python3
  elif command -v python >/dev/null 2>&1; then
    command -v python
  else
    fail "未找到 Python 3.11 或更高版本。"
  fi
}

update_git_checkout() {
  command -v git >/dev/null 2>&1 || fail "这是 Git 源码目录，但系统中没有可用的 Git。"
  local remote_url branch upstream counts ahead behind changes commit
  remote_url="$(git -C "$INSTALL_DIR" remote get-url origin 2>/dev/null)" || fail "无法读取 Git origin。"
  case "$remote_url" in
    https://github.com/RainyHorizon/voice-studio|https://github.com/RainyHorizon/voice-studio.git|git@github.com:RainyHorizon/voice-studio|git@github.com:RainyHorizon/voice-studio.git|ssh://git@github.com/RainyHorizon/voice-studio|ssh://git@github.com/RainyHorizon/voice-studio.git) ;;
    *) fail "origin 不是 Voice Studio 官方仓库，更新器不会自动拉取：$remote_url" ;;
  esac

  branch="$(git -C "$INSTALL_DIR" branch --show-current)"
  [[ -n "$branch" ]] || fail "当前 Git 仓库处于 detached HEAD 状态，请先切换到需要更新的分支。"
  upstream="$(git -C "$INSTALL_DIR" rev-parse --abbrev-ref --symbolic-full-name '@{u}' 2>/dev/null)" \
    || fail "当前分支没有上游分支，无法自动更新。"

  printf '安装类型：Git 源码目录\n当前分支：%s\n上游分支：%s\n' "$branch" "$upstream"
  log "正在获取官方仓库更新信息..."
  git -C "$INSTALL_DIR" fetch --prune origin || fail "无法从 GitHub 获取更新信息。"
  counts="$(git -C "$INSTALL_DIR" rev-list --left-right --count "HEAD...$upstream")" \
    || fail "无法比较当前分支与上游分支。"
  read -r ahead behind <<< "$counts"

  if ((behind == 0)); then
    if ((ahead > 0)); then
      printf '当前分支比上游多 %s 个本地提交，没有可拉取的更新。\n' "$ahead"
    else
      printf '当前 Git 分支已经与上游保持一致。\n'
    fi
    return 0
  fi
  printf '检测到上游有 %s 个新提交。\n' "$behind"
  ((ahead == 0)) || fail "当前分支与上游已经分叉，无法安全快进更新。请由开发者手动处理 Git 历史。"
  ((CHECK_ONLY)) && return 0

  changes="$(git -C "$INSTALL_DIR" status --porcelain --untracked-files=normal)"
  [[ -z "$changes" ]] || fail "检测到未提交或未跟踪文件，已停止更新。请先提交、暂存或移走这些改动。"
  confirm "输入 Y 将当前分支快进到 $upstream，输入其他内容取消：" || { printf '已取消更新。\n'; return 0; }
  require_stopped
  log "正在快进更新 Git 源码..."
  git -C "$INSTALL_DIR" pull --ff-only || fail "Git 无法完成快进更新。"
  commit="$(git -C "$INSTALL_DIR" rev-parse --short HEAD)"
  printf 'Git 源码已更新，当前提交：%s\n' "$commit"
  printf '下次启动时会自动检查前端与 Python 依赖。\n'
}

update_release_package() {
  local python_bin platform_label current_version metadata_file release_info_file
  local latest_version archive_name archive_url checksum_url archive_path checksum_path
  local extract_dir backup_dir package_root_file package_root version_state
  python_bin="$(find_python)"
  command -v curl >/dev/null 2>&1 || fail "未找到 curl，无法从 GitHub 下载更新。"

  case "$(uname -s)" in
    Darwin) platform_label="macOS" ;;
    Linux) platform_label="Linux" ;;
    *) fail "当前系统不支持 Release 包自动更新。" ;;
  esac
  printf '安装类型：%s Release 包\n' "$platform_label"

  UPDATE_TEMP_ROOT="$(mktemp -d "${TMPDIR:-/tmp}/voice-studio-update.XXXXXX")"
  metadata_file="$UPDATE_TEMP_ROOT/release.json"
  release_info_file="$UPDATE_TEMP_ROOT/release-info.txt"
  log "正在查询 GitHub 最新正式版本..."
  curl --fail --silent --show-error --location --retry 2 \
    -H 'Accept: application/vnd.github+json' \
    -H 'X-GitHub-Api-Version: 2022-11-28' \
    -H 'User-Agent: Voice-Studio-Updater' \
    "https://api.github.com/repos/$REPOSITORY/releases/latest" > "$metadata_file" \
    || fail "无法访问 GitHub Releases。"

  "$python_bin" - "$metadata_file" "$platform_label" "$REPOSITORY" > "$release_info_file" <<'PY'
import json
import re
import sys

metadata_path, platform, repository = sys.argv[1:]
with open(metadata_path, "r", encoding="utf-8") as handle:
    release = json.load(handle)
if release.get("draft") or release.get("prerelease"):
    raise SystemExit("GitHub 返回的版本不是正式 Release")
version = str(release.get("tag_name", "")).strip().lstrip("v")
if not re.fullmatch(r"\d+\.\d+\.\d+", version):
    raise SystemExit("无法识别最新版本号")
archive_name = f"Voice-Studio-{version}-{platform}.tar.gz"
checksum_name = f"{archive_name}.sha256"
assets = {asset.get("name"): asset.get("browser_download_url") for asset in release.get("assets", [])}
archive_url = assets.get(archive_name)
checksum_url = assets.get(checksum_name)
if not archive_url or not checksum_url:
    raise SystemExit(f"最新 Release 缺少 {archive_name} 或 SHA256 校验文件")
trusted = f"https://github.com/{repository}/releases/download/"
if not archive_url.lower().startswith(trusted.lower()) or not checksum_url.lower().startswith(trusted.lower()):
    raise SystemExit("Release 资源地址不属于官方仓库")
print("\t".join((version, archive_name, archive_url, checksum_url)))
PY
  IFS=$'\t' read -r latest_version archive_name archive_url checksum_url < "$release_info_file"

  current_version=""
  [[ -f "$INSTALL_DIR/VERSION" ]] && current_version="$(tr -d '[:space:]' < "$INSTALL_DIR/VERSION")"
  [[ "$current_version" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] || current_version=""
  printf '当前版本：%s\n最新版本：%s\n' "${current_version:-未知（旧版未记录版本号）}" "$latest_version"
  if [[ -n "$current_version" ]]; then
    version_state="$($python_bin - "$current_version" "$latest_version" <<'PY'
import sys
current = tuple(map(int, sys.argv[1].split(".")))
latest = tuple(map(int, sys.argv[2].split(".")))
print("current" if current >= latest else "older")
PY
)"
    if [[ "$version_state" == "current" ]]; then
      printf '当前版本不低于 GitHub 最新正式版，无需更新。\n'
      return 0
    fi
  fi
  if ((CHECK_ONLY)); then
    printf '检测到可用更新：%s\n' "$latest_version"
    return 0
  fi

  confirm "输入 Y 确认更新并保留 data，输入其他内容取消：" || { printf '已取消更新。\n'; return 0; }
  require_stopped
  archive_path="$UPDATE_TEMP_ROOT/$archive_name"
  checksum_path="$UPDATE_TEMP_ROOT/$archive_name.sha256"
  log "正在下载 $archive_name..."
  curl --fail --silent --show-error --location --retry 2 "$archive_url" -o "$archive_path" \
    || fail "Release 压缩包下载失败。"
  curl --fail --silent --show-error --location --retry 2 "$checksum_url" -o "$checksum_path" \
    || fail "SHA256 校验文件下载失败。"

  "$python_bin" - "$archive_path" "$checksum_path" <<'PY'
import hashlib
import re
import sys
from pathlib import Path

archive = Path(sys.argv[1])
checksum_text = Path(sys.argv[2]).read_text(encoding="ascii", errors="strict")
match = re.search(r"(?i)\b([0-9a-f]{64})\b", checksum_text)
if not match:
    raise SystemExit("SHA256 校验文件格式无效")
digest = hashlib.sha256()
with archive.open("rb") as handle:
    for chunk in iter(lambda: handle.read(1024 * 1024), b""):
        digest.update(chunk)
if digest.hexdigest().lower() != match.group(1).lower():
    raise SystemExit("下载文件的 SHA256 不匹配")
PY
  printf 'SHA256 校验通过。\n'

  extract_dir="$UPDATE_TEMP_ROOT/extract"
  backup_dir="$UPDATE_TEMP_ROOT/backup"
  package_root_file="$UPDATE_TEMP_ROOT/package-root.txt"
  mkdir -p "$extract_dir" "$backup_dir"
  "$python_bin" - "$archive_path" "$extract_dir" "$latest_version" "$package_root_file" <<'PY'
import os
import sys
import tarfile
from pathlib import Path, PurePosixPath

archive_path, extract_path, expected_version, output_path = sys.argv[1:]
extract_root = Path(extract_path).resolve()
with tarfile.open(archive_path, "r:gz") as archive:
    for member in archive.getmembers():
        relative = PurePosixPath(member.name)
        if relative.is_absolute() or ".." in relative.parts or not relative.parts:
            raise SystemExit(f"更新包包含不安全路径：{member.name}")
        if member.issym() or member.islnk() or member.isdev():
            raise SystemExit(f"更新包包含不允许的链接或设备：{member.name}")
        target = (extract_root / Path(*relative.parts)).resolve()
        if os.path.commonpath((extract_root, target)) != str(extract_root):
            raise SystemExit(f"更新包路径越界：{member.name}")
    archive.extractall(extract_root)
candidates = [path.parent for path in extract_root.rglob("start.sh") if (path.parent / "VERSION").is_file()]
if len(candidates) != 1:
    raise SystemExit("更新包结构无效：无法唯一确定 start.sh")
package_root = candidates[0]
if (package_root / "VERSION").read_text(encoding="utf-8").strip() != expected_version:
    raise SystemExit("更新包版本与 Release 标签不一致")
Path(output_path).write_text(str(package_root), encoding="utf-8")
PY
  package_root="$(cat "$package_root_file")"

  log "正在安装 $latest_version..."
  "$python_bin" - "$package_root" "$INSTALL_DIR" "$backup_dir" "$latest_version" "$MANIFEST_NAME" <<'PY'
import shutil
import sys
from pathlib import Path, PurePosixPath

package_root = Path(sys.argv[1]).resolve()
install_root = Path(sys.argv[2]).resolve()
backup_root = Path(sys.argv[3]).resolve()
expected_version = sys.argv[4]
manifest_name = sys.argv[5]

def safe_relative(raw: str) -> PurePosixPath:
    relative = PurePosixPath(raw.replace("\\", "/"))
    if relative.is_absolute() or not relative.parts or ".." in relative.parts or relative.parts[0].lower() == "data":
        raise RuntimeError(f"不安全的受管路径：{raw}")
    return relative

def read_manifest(root: Path) -> list[PurePosixPath]:
    path = root / manifest_name
    if not path.is_file():
        return []
    return [safe_relative(line.strip()) for line in path.read_text(encoding="utf-8-sig").splitlines() if line.strip()]

actual_files = []
for path in package_root.rglob("*"):
    if not path.is_file():
        continue
    relative = safe_relative(path.relative_to(package_root).as_posix())
    actual_files.append(relative)
declared = set(read_manifest(package_root))
actual_managed = {path for path in actual_files if path.as_posix() != manifest_name}
if declared != actual_managed:
    raise RuntimeError("更新包的受管文件清单与实际内容不一致")

for required in ("start.sh", "backend/app/main.py", "backend/requirements.txt", "frontend/dist/index.html"):
    if not (package_root / required).is_file():
        raise RuntimeError(f"更新包不完整，缺少：{required}")

old_files = read_manifest(install_root)
new_files = actual_files
for relative in sorted(set(old_files) | set(new_files), key=lambda item: item.as_posix()):
    current = install_root.joinpath(*relative.parts)
    if current.is_file():
        backup = backup_root.joinpath(*relative.parts)
        backup.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(current, backup)

try:
    for relative in new_files:
        source = package_root.joinpath(*relative.parts)
        destination = install_root.joinpath(*relative.parts)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
    new_set = set(new_files)
    for relative in old_files:
        if relative not in new_set:
            stale = install_root.joinpath(*relative.parts)
            if stale.is_file():
                stale.unlink()
    if (install_root / "VERSION").read_text(encoding="utf-8").strip() != expected_version:
        raise RuntimeError("安装后的版本验证失败")
except Exception:
    for relative in new_files:
        destination = install_root.joinpath(*relative.parts)
        if destination.is_file():
            destination.unlink()
    for backup in backup_root.rglob("*"):
        if backup.is_file():
            relative = backup.relative_to(backup_root)
            destination = install_root / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(backup, destination)
    raise
PY
  printf 'Voice Studio 已更新到 %s。\n' "$latest_version"
  printf '本地 data、系统凭据、虚拟环境和非程序文件均已保留。\n'
  printf '下次启动时会自动检查 Python 依赖。\n'
}

if [[ -d "$INSTALL_DIR/.git" && -f "$INSTALL_DIR/start.sh" ]]; then
  update_git_checkout
elif [[ -f "$INSTALL_DIR/start.sh" && -d "$INSTALL_DIR/backend/app" ]]; then
  update_release_package
else
  fail "无法识别当前安装类型。请确认 update.sh 位于 Voice Studio 的程序根目录。"
fi
