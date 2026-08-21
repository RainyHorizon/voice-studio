#!/usr/bin/env bash
set -Eeuo pipefail

# Voice Studio source launcher for macOS and Linux.
# Keep this script dependency-light so it also works from a fresh checkout.
SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
BACKEND_DIR="$SCRIPT_DIR/backend"
FRONTEND_DIR="$SCRIPT_DIR/frontend"
DATA_DIR="$SCRIPT_DIR/data"
PYTHON_BIN="${PYTHON_BIN:-}"
PORT="${VOICE_STUDIO_PORT:-8765}"
OPEN_BROWSER=0

log() { printf '[Voice Studio] %s\n' "$1"; }
fail() { printf '\nVoice Studio 启动失败\n%s\n' "$1" >&2; exit 1; }

usage() {
  cat <<'EOF'
用法：./start.sh [选项]

选项：
  --port PORT       使用指定本地端口（默认 8765）
  --open-browser    服务就绪后打开默认浏览器
  --no-browser      不打开浏览器（默认）
  --help            显示帮助
EOF
}

while (($# > 0)); do
  case "$1" in
    --port)
      (($# >= 2)) || fail "--port 需要一个端口号。"
      PORT="$2"
      shift 2
      ;;
    --open-browser) OPEN_BROWSER=1; shift ;;
    --no-browser) OPEN_BROWSER=0; shift ;;
    --help|-h) usage; exit 0 ;;
    *) fail "未知选项：$1。运行 ./start.sh --help 查看用法。" ;;
  esac
done

[[ "$PORT" =~ ^[0-9]+$ ]] && ((PORT >= 1 && PORT <= 65535)) || fail "端口必须是 1 到 65535 之间的数字。"

if [[ -z "$PYTHON_BIN" ]]; then
  if command -v python3 >/dev/null 2>&1; then
    PYTHON_BIN="$(command -v python3)"
  elif command -v python >/dev/null 2>&1; then
    PYTHON_BIN="$(command -v python)"
  else
    fail "未找到 Python 3。请安装 Python 3.11 或更高版本。"
  fi
fi

PYTHON_VERSION="$($PYTHON_BIN -c 'import sys; print(".".join(map(str, sys.version_info[:3])))')" \
  || fail "Python 无法正常运行。"
PYTHON_OK="$($PYTHON_BIN -c 'import sys; print(int(sys.version_info >= (3, 11)))')"
[[ "$PYTHON_OK" == "1" ]] || fail "当前 Python 为 $PYTHON_VERSION，需要 Python 3.11 或更高版本。"
log "Python $PYTHON_VERSION 可用"

for command_name in ffmpeg ffprobe; do
  command -v "$command_name" >/dev/null 2>&1 || fail "未找到 $command_name。请安装 FFmpeg，并确保它已加入 PATH。"
  "$command_name" -version >/dev/null 2>&1 || fail "$command_name 无法正常运行。"
done
log "FFmpeg 与 FFprobe 可用"

mkdir -p "$DATA_DIR"
write_probe="$DATA_DIR/.write-test-$$"
printf 'ok' > "$write_probe" || fail "数据目录不可写：$DATA_DIR"
rm -f -- "$write_probe"
log "数据目录可写"

FRONTEND_INDEX="$FRONTEND_DIR/dist/index.html"
needs_frontend_build=0
if [[ ! -f "$FRONTEND_INDEX" ]]; then
  needs_frontend_build=1
elif find "$FRONTEND_DIR/src" -type f -newer "$FRONTEND_INDEX" -print -quit 2>/dev/null | grep -q .; then
  needs_frontend_build=1
fi
if ((needs_frontend_build)); then
  command -v node >/dev/null 2>&1 || fail "前端文件尚未构建，且未找到 Node.js。请安装 Node.js 20+ 后重试。"
  command -v npm >/dev/null 2>&1 || fail "前端文件尚未构建，且未找到 npm。请安装 Node.js 20+ 后重试。"
  log "正在准备前端"
  (cd "$FRONTEND_DIR" && [[ -d node_modules ]] || npm install)
  (cd "$FRONTEND_DIR" && npm run build)
else
  log "已找到预构建前端，无需 Node.js"
fi

VENV_DIR="$BACKEND_DIR/.venv"
VENV_PYTHON="$VENV_DIR/bin/python"
if [[ ! -x "$VENV_PYTHON" ]]; then
  log "首次运行，正在创建 Python 虚拟环境"
  "$PYTHON_BIN" -m venv "$VENV_DIR" || fail "Python 虚拟环境创建失败。"
fi

REQUIREMENTS_HASH="$(cd "$BACKEND_DIR" && "$VENV_PYTHON" -c 'import hashlib, pathlib; print(hashlib.sha256(pathlib.Path("requirements.txt").read_bytes()).hexdigest())')"
REQUIREMENTS_STAMP="$VENV_DIR/.requirements.sha256"
INSTALLED_HASH=""
[[ -f "$REQUIREMENTS_STAMP" ]] && INSTALLED_HASH="$(tr -d '[:space:]' < "$REQUIREMENTS_STAMP")"
if [[ "$REQUIREMENTS_HASH" != "$INSTALLED_HASH" ]]; then
  log "正在安装或更新后端依赖"
  (cd "$BACKEND_DIR" && "$VENV_PYTHON" -m pip install -r requirements.txt) || fail "Python 依赖安装失败，请检查网络后重试。"
  printf '%s\n' "$REQUIREMENTS_HASH" > "$REQUIREMENTS_STAMP"
else
  log "后端依赖已就绪"
fi

export PYTHONUTF8=1
export VOICE_STUDIO_ROOT="$SCRIPT_DIR"
export VOICE_STUDIO_PORT="$PORT"
export PYTHONPATH="$BACKEND_DIR${PYTHONPATH:+:$PYTHONPATH}"

credential_status="$($VENV_PYTHON -c 'from app.credentials import credential_store_status; import sys; result=credential_store_status(); print(result["message"]); sys.exit(0 if result["available"] else 1)' 2>&1)" \
  || fail "$credential_status"$'\n'"请在 macOS 启用钥匙串访问，或在 Linux 桌面会话中安装并启用 Secret Service（例如 GNOME Keyring/KWallet）。无图形服务器请使用带有可用密钥环的用户会话。"
log "$credential_status"

if ((OPEN_BROWSER)); then
  (sleep 2; "$VENV_PYTHON" -m webbrowser "http://127.0.0.1:$PORT") >/dev/null 2>&1 &
fi

printf '\nVoice Studio 已准备完成：http://127.0.0.1:%s\n' "$PORT"
printf '关闭此终端或按 Ctrl+C 即可停止服务。\n'
exec "$VENV_PYTHON" -m uvicorn app.main:app --host 127.0.0.1 --port "$PORT"
