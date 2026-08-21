from __future__ import annotations

import argparse
import json
import os
import socket
import sys
import threading
import time
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path


DEFAULT_PORT = 8765
FALLBACK_PORTS = range(8766, 8791)

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


def application_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[1]


def port_is_available(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        try:
            listener.bind(("127.0.0.1", port))
        except OSError:
            return False
    return True


def voice_studio_is_running(port: int) -> bool:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/summary", timeout=2) as response:
            body = json.loads(response.read().decode("utf-8"))
            return response.status == 200 and body.get("application") == "voice-studio"
    except (OSError, ValueError, urllib.error.URLError):
        return False


def select_port(requested: int | None) -> tuple[int, bool]:
    port = requested or DEFAULT_PORT
    if voice_studio_is_running(port):
        return port, True
    if port_is_available(port):
        return port, False
    if requested is not None:
        raise RuntimeError(f"端口 {port} 已被其他程序占用。")
    for candidate in FALLBACK_PORTS:
        if voice_studio_is_running(candidate):
            return candidate, True
        if port_is_available(candidate):
            return candidate, False
    raise RuntimeError("端口 8765-8790 均不可用，请关闭占用端口的程序后重试。")


def prepare_environment(root: Path, port: int) -> None:
    tools = root / "tools"
    frontend = root / "frontend" / "dist" / "index.html"
    required = [tools / "ffmpeg.exe", tools / "ffprobe.exe", frontend]
    missing = [str(path.relative_to(root)) for path in required if not path.is_file()]
    if missing:
        raise RuntimeError(f"便携版文件不完整，缺少：{', '.join(missing)}")

    data = root / "data"
    data.mkdir(parents=True, exist_ok=True)
    write_probe = data / f".write-test-{os.getpid()}"
    try:
        write_probe.write_text("ok", encoding="ascii")
    finally:
        write_probe.unlink(missing_ok=True)

    os.environ["VOICE_STUDIO_ROOT"] = str(root)
    os.environ["VOICE_STUDIO_PORT"] = str(port)
    os.environ["PATH"] = f"{tools}{os.pathsep}{os.environ.get('PATH', '')}"


def open_when_ready(url: str) -> None:
    def wait_and_open() -> None:
        for _ in range(90):
            if voice_studio_is_running(int(url.rsplit(":", 1)[1])):
                webbrowser.open(url)
                return
            time.sleep(1)

    threading.Thread(target=wait_and_open, name="voice-studio-browser", daemon=True).start()


def run() -> int:
    parser = argparse.ArgumentParser(description="Voice Studio Windows 便携版")
    parser.add_argument("--port", type=int, choices=range(1, 65536), help="本地服务端口")
    parser.add_argument("--no-browser", action="store_true", help="启动后不自动打开浏览器")
    parser.add_argument("--check", action="store_true", help="只检查便携版文件和运行环境")
    args = parser.parse_args()

    root = application_root()
    port, already_running = select_port(args.port)
    url = f"http://127.0.0.1:{port}"
    if already_running:
        print(f"Voice Studio 已在运行：{url}")
        if not args.no_browser:
            webbrowser.open(url)
        return 0

    prepare_environment(root, port)
    if args.check:
        print("Voice Studio 便携版检查通过")
        print(f"程序目录：{root}")
        print(f"可用端口：{port}")
        return 0

    from app.credentials import credential_store_status

    credential = credential_store_status()
    if not credential["available"]:
        raise RuntimeError(str(credential["message"]))

    from app.main import app
    import uvicorn

    if not args.no_browser:
        open_when_ready(url)
    print("")
    print(f"Voice Studio 已准备完成：{url}")
    print("关闭此窗口即可停止服务。")
    uvicorn.run(app, host="127.0.0.1", port=port, loop="asyncio", http="h11")
    return 0


def main() -> None:
    try:
        raise SystemExit(run())
    except KeyboardInterrupt:
        raise SystemExit(0) from None
    except Exception as exc:
        print("")
        print("Voice Studio 启动失败")
        print(str(exc))
        input("按 Enter 键关闭窗口...")
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
