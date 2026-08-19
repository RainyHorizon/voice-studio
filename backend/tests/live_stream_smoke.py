"""Run sequential live SSE smoke tests against configured speech providers.

The script obtains the local gateway key without printing it, selects one
compatible active voice per provider, saves the streamed audio, and checks it
with ffprobe when it is available on PATH. MiMo's native PCM16 stream is
wrapped in a WAV container before probing.
"""

from __future__ import annotations

import argparse
import base64
import http.client
import json
import shutil
import subprocess
import sys
import time
import wave
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from urllib.request import Request, urlopen


CASES = (
    ("mimo", "mimo/mimo-v2.5-tts", "pcm"),
    ("volcengine", "volcengine/seed-tts-2.0", "mp3"),
    ("dashscope", "dashscope/cosyvoice-v3-flash", "mp3"),
    ("minimax", "minimax/speech-2.8-turbo", "mp3"),
)


def get_json(url: str) -> Any:
    with urlopen(Request(url, headers={"Accept": "application/json"}), timeout=10) as response:
        return json.load(response)


def select_voice(voices: list[dict[str, Any]], provider: str, model: str) -> dict[str, Any]:
    model_id = model.split("/", 1)[1]
    candidates = [
        voice
        for voice in voices
        if voice.get("provider") == provider and voice.get("model_id") == model_id
    ]
    if not candidates:
        raise RuntimeError(f"{model} 没有可用的 active 音色")
    return candidates[0]


def ffprobe(path: Path) -> dict[str, Any]:
    executable = shutil.which("ffprobe")
    if not executable:
        return {"ok": None, "message": "PATH 中未找到 ffprobe"}
    process = subprocess.run(
        [
            executable,
            "-v",
            "error",
            "-select_streams",
            "a:0",
            "-show_entries",
            "stream=codec_name,sample_rate,channels,duration",
            "-of",
            "json",
            str(path),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=20,
        check=False,
    )
    if process.returncode != 0:
        return {"ok": False, "message": (process.stderr or "ffprobe 失败").strip()[:300]}
    streams = json.loads(process.stdout).get("streams") or []
    return {"ok": bool(streams), "stream": streams[0] if streams else None}


def save_stream_audio(audio: bytes, response_format: str, done: dict[str, Any], output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if response_format != "pcm":
        output_path.write_bytes(audio)
        return output_path
    pcm = done.get("pcm") or {}
    sample_rate = int(pcm.get("sample_rate") or 24000)
    channels = int(pcm.get("channels") or 1)
    bit_depth = int(pcm.get("bit_depth") or 16)
    encoding = str(pcm.get("encoding") or "s16le")
    if encoding != "s16le" or bit_depth != 16:
        raise RuntimeError(f"网关返回了不支持的 PCM 参数：{encoding}/{bit_depth}bit")
    with wave.open(str(output_path), "wb") as container:
        container.setnchannels(channels)
        container.setsampwidth(2)
        container.setframerate(sample_rate)
        container.writeframes(audio)
    return output_path


def run_case(
    base_url: str,
    gateway_key: str,
    provider: str,
    model: str,
    voice: dict[str, Any],
    output_dir: Path,
    text: str,
    response_format: str,
) -> dict[str, Any]:
    parsed = urlparse(base_url)
    connection_class = http.client.HTTPSConnection if parsed.scheme == "https" else http.client.HTTPConnection
    connection = connection_class(parsed.hostname, parsed.port, timeout=90)
    endpoint = (parsed.path.rstrip("/") or "/v1") + "/audio/speech/stream"
    body = json.dumps(
        {
            "model": model,
            "voice": voice["public_name"],
            "input": text,
            "response_format": response_format,
            "chunk_size": 4096,
        },
        ensure_ascii=False,
    ).encode("utf-8")
    headers = {
        "Authorization": "Bearer " + gateway_key,
        "Content-Type": "application/json; charset=utf-8",
        "Accept": "text/event-stream",
    }
    started = time.perf_counter()
    connection.request("POST", endpoint, body=body, headers=headers)
    response = connection.getresponse()
    if response.status != 200:
        message = response.read().decode("utf-8", errors="replace")[:600]
        connection.close()
        raise RuntimeError(f"HTTP {response.status}: {message}")

    audio = bytearray()
    first_chunk_ms: int | None = None
    chunks = 0
    done: dict[str, Any] | None = None
    current_event = "message"
    data_lines: list[str] = []

    def process_event() -> None:
        nonlocal first_chunk_ms, chunks, done, current_event, data_lines
        if not data_lines:
            current_event = "message"
            return
        payload = json.loads("\n".join(data_lines))
        if current_event == "audio":
            chunk = base64.b64decode(payload["audio"], validate=True)
            if first_chunk_ms is None:
                first_chunk_ms = round((time.perf_counter() - started) * 1000)
            audio.extend(chunk)
            chunks += 1
        elif current_event == "done":
            done = payload
        elif current_event == "error":
            error = payload.get("error") or {}
            raise RuntimeError(f"{error.get('code', 'stream_error')}: {error.get('message', '流式请求失败')}")
        current_event = "message"
        data_lines = []

    try:
        while True:
            raw_line = response.readline()
            if not raw_line:
                process_event()
                break
            line = raw_line.decode("utf-8", errors="replace").rstrip("\r\n")
            if not line:
                process_event()
                if done is not None:
                    break
            elif line.startswith("event:"):
                current_event = line[6:].strip()
            elif line.startswith("data:"):
                data_lines.append(line[5:].lstrip())
    finally:
        connection.close()

    if not done:
        raise RuntimeError("SSE 连接结束，但没有收到 done 事件")
    output_path = output_dir / f"{provider}-{model.rsplit('/', 1)[1]}.{'wav' if response_format == 'pcm' else response_format}"
    save_stream_audio(bytes(audio), response_format, done, output_path)
    total_ms = round((time.perf_counter() - started) * 1000)
    return {
        "provider": provider,
        "model": model,
        "voice": voice.get("display_name") or voice["public_name"],
        "first_chunk_ms": first_chunk_ms,
        "total_ms": total_ms,
        "chunks": chunks,
        "bytes": len(audio),
        "native_streaming": bool(done.get("native_streaming")),
        "response_format": response_format,
        "provider_request_id": done.get("provider_request_id") or None,
        "gateway_job_id": done.get("job_id") or None,
        "output": str(output_path.resolve()),
        "ffprobe": ffprobe(output_path),
    }


def run_cancel_case(
    base_url: str,
    gateway_key: str,
    provider: str,
    model: str,
    voice: dict[str, Any],
    text: str,
    cancel_after_chunks: int,
    response_format: str,
) -> dict[str, Any]:
    """Disconnect after a bounded number of chunks and verify local cleanup."""
    parsed = urlparse(base_url)
    connection_class = http.client.HTTPSConnection if parsed.scheme == "https" else http.client.HTTPConnection
    connection = connection_class(parsed.hostname, parsed.port, timeout=90)
    endpoint = (parsed.path.rstrip("/") or "/v1") + "/audio/speech/stream"
    body = json.dumps(
        {
            "model": model,
            "voice": voice["public_name"],
            "input": text,
            "response_format": response_format,
            "chunk_size": 4096,
        },
        ensure_ascii=False,
    ).encode("utf-8")
    started = time.perf_counter()
    connection.request(
        "POST",
        endpoint,
        body=body,
        headers={
            "Authorization": "Bearer " + gateway_key,
            "Content-Type": "application/json; charset=utf-8",
            "Accept": "text/event-stream",
        },
    )
    response = connection.getresponse()
    if response.status != 200:
        message = response.read().decode("utf-8", errors="replace")[:600]
        connection.close()
        raise RuntimeError(f"HTTP {response.status}: {message}")

    job_id = response.getheader("X-Voice-Studio-Job") or ""
    chunks = 0
    bytes_received = 0
    first_chunk_ms: int | None = None
    event = "message"
    data_lines: list[str] = []
    try:
        while chunks < cancel_after_chunks:
            raw_line = response.readline()
            if not raw_line:
                raise RuntimeError("SSE 在取消点之前已经结束")
            line = raw_line.decode("utf-8", errors="replace").rstrip("\r\n")
            if line.startswith("event:"):
                event = line[6:].strip()
            elif line.startswith("data:"):
                data_lines.append(line[5:].lstrip())
            elif not line and data_lines:
                payload = json.loads("\n".join(data_lines))
                if event == "error":
                    error = payload.get("error") or {}
                    raise RuntimeError(f"{error.get('code', 'stream_error')}: {error.get('message', '流式请求失败')}")
                if event == "done":
                    raise RuntimeError("厂商在取消点之前已经完成合成")
                if event == "audio":
                    audio = base64.b64decode(payload["audio"], validate=True)
                    if first_chunk_ms is None:
                        first_chunk_ms = round((time.perf_counter() - started) * 1000)
                    chunks += 1
                    bytes_received += len(audio)
                event = "message"
                data_lines = []
    finally:
        response.close()
        connection.close()

    time.sleep(1.5)
    server_root = f"{parsed.scheme}://{parsed.hostname}:{parsed.port}"
    jobs = get_json(server_root + "/api/jobs")
    job_recorded = any(item.get("id") == job_id for item in jobs)
    partial_path = Path(__file__).resolve().parents[2] / "data" / "audio" / f"{job_id}.{response_format}"
    partial_file_exists = partial_path.exists()
    return {
        "provider": provider,
        "model": model,
        "voice": voice.get("display_name") or voice["public_name"],
        "cancelled_after_chunks": chunks,
        "first_chunk_ms": first_chunk_ms,
        "bytes_before_cancel": bytes_received,
        "gateway_job_id": job_id or None,
        "job_recorded": job_recorded,
        "partial_file_exists": partial_file_exists,
        "ok": bool(job_id and chunks == cancel_after_chunks and not job_recorded and not partial_file_exists),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Voice Studio 真实流式厂商冒烟验证")
    parser.add_argument("--server", default="http://127.0.0.1:8765")
    parser.add_argument("--text", default="你好，这是一段流式语音测试。")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path(__file__).resolve().parents[2] / "output" / "live-stream-smoke",
    )
    parser.add_argument(
        "--provider",
        choices=[provider for provider, _, _ in CASES],
        action="append",
        help="只验证指定厂商，可重复传入；默认依次验证四家",
    )
    parser.add_argument(
        "--cancel-after-chunks",
        type=int,
        choices=range(1, 11),
        metavar="N",
        help="收到 N 个音频分片后主动断开，并验证任务与半成品已清理",
    )
    args = parser.parse_args()

    gateway = get_json(args.server.rstrip("/") + "/api/gateway")
    voices = get_json(args.server.rstrip("/") + "/api/voices")
    gateway_key = gateway.get("key")
    if not gateway_key:
        raise RuntimeError("本地网关没有可用 Key")
    args.output_dir.mkdir(parents=True, exist_ok=True)

    selected = set(args.provider or [])
    results: list[dict[str, Any]] = []
    failed = False
    for provider, model, response_format in CASES:
        if selected and provider not in selected:
            continue
        try:
            voice = select_voice(voices, provider, model)
            if args.cancel_after_chunks:
                result = run_cancel_case(
                    gateway["base_url"],
                    gateway_key,
                    provider,
                    model,
                    voice,
                    args.text,
                    args.cancel_after_chunks,
                    response_format,
                )
            else:
                result = run_case(
                    gateway["base_url"], gateway_key, provider, model, voice, args.output_dir, args.text, response_format
                )
                result["ok"] = bool(result["bytes"] and result["native_streaming"] and result["ffprobe"].get("ok"))
        except Exception as exc:  # Keep later providers testable after one vendor fails.
            failed = True
            result = {"provider": provider, "model": model, "ok": False, "error": str(exc)}
        results.append(result)
        print(json.dumps(result, ensure_ascii=False), flush=True)

    if not results:
        print(json.dumps({"ok": False, "error": "没有选择需要验证的厂商"}, ensure_ascii=False))
        return 2
    if any(not result.get("ok") for result in results):
        failed = True
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
