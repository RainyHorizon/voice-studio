from __future__ import annotations

import asyncio
import binascii
import json
import subprocess
import uuid
from pathlib import Path
from typing import AsyncIterator
from urllib.parse import urlsplit

import httpx
import websockets

from .base import ProviderError, ProviderModel, SpeechProvider, SynthesisRequest


DEFAULT_ENDPOINT = "https://api.minimaxi.com/v1"
SUPPORTED_MODELS = {
    "speech-2.8-hd",
    "speech-2.8-turbo",
    "speech-2.6-hd",
    "speech-2.6-turbo",
}

MINIMAX_MODELS = [
    ProviderModel("minimax", "speech-2.8-hd", "Speech 2.8 HD", "tts", "高保真", "中", ["zh-CN", "en-US", "ja-JP"], True, "provider", ["synthesis", "clone"]),
    ProviderModel("minimax", "speech-2.8-turbo", "Speech 2.8 Turbo", "tts", "均衡", "快", ["zh-CN", "en-US", "ja-JP"], True, "provider", ["synthesis", "clone", "design"]),
    ProviderModel("minimax", "speech-2.6-hd", "Speech 2.6 HD", "tts", "细腻", "中", ["zh-CN", "en-US", "ja-JP"], True, "provider", ["synthesis", "clone"]),
    ProviderModel("minimax", "speech-2.6-turbo", "Speech 2.6 Turbo", "tts", "高效", "快", ["zh-CN", "en-US", "ja-JP"], True, "provider", ["synthesis", "clone"]),
]


def _remote_message(response: httpx.Response, fallback: str) -> str:
    try:
        body = response.json()
        base = body.get("base_resp") or {}
        message = base.get("status_msg") or body.get("message") or body.get("error", {}).get("message")
        if message:
            return f"{fallback}：{str(message)[:240]}"
    except (TypeError, ValueError):
        pass
    return f"{fallback}（HTTP {response.status_code}）"


def _decode_audio(body: dict) -> bytes:
    base_resp = body.get("base_resp") or {}
    status_code = base_resp.get("status_code", 0)
    if status_code not in {0, None}:
        message = base_resp.get("status_msg") or "未知业务错误"
        auth_status = 401 if status_code == 1004 else 502
        raise ProviderError(
            f"MiniMax 语音合成失败：{message}（错误码 {status_code}）",
            code="minimax_synthesis_failed",
            status=auth_status,
        )
    try:
        encoded = (body.get("data") or {}).get("audio")
        if not encoded:
            raise ValueError("empty audio")
        return bytes.fromhex(encoded)
    except (TypeError, ValueError, binascii.Error) as exc:
        raise ProviderError("MiniMax 返回成功状态，但没有有效音频数据", code="invalid_provider_response") from exc


class MiniMaxProvider(SpeechProvider):
    key = "minimax"

    def __init__(self, api_key: str, endpoint: str = DEFAULT_ENDPOINT):
        self.api_key = api_key
        self.endpoint = endpoint.rstrip("/")

    def models(self) -> list[ProviderModel]:
        return MINIMAX_MODELS

    async def create_voice_design(self, prompt: str, preview_text: str, voice_id: str | None = None) -> dict:
        payload = {"prompt": prompt, "preview_text": preview_text}
        if voice_id:
            payload["voice_id"] = voice_id
        try:
            async with httpx.AsyncClient(timeout=180) as client:
                response = await client.post(self.endpoint + "/voice_design", headers=self._headers(), json=payload)
        except httpx.HTTPError as exc:
            raise ProviderError("无法连接 MiniMax 音色设计接口", code="provider_unreachable") from exc
        if response.status_code != 200:
            raise ProviderError(_remote_message(response, "MiniMax 音色设计失败"), code="minimax_voice_design_failed", status=401 if response.status_code in {401, 403} else 502)
        try:
            body = response.json()
            base_resp = body.get("base_resp") or {}
            if base_resp.get("status_code", 0) not in {0, None}:
                raise ValueError(base_resp.get("status_msg") or base_resp.get("status_code"))
            created_voice_id = str(body["voice_id"])
            trial_audio = body.get("trial_audio") or ""
        except (KeyError, TypeError, ValueError) as exc:
            raise ProviderError(f"MiniMax 返回的设计音色数据无效：{str(exc)[:160]}", code="invalid_provider_response") from exc
        try:
            preview_audio = bytes.fromhex(trial_audio) if trial_audio else b""
        except ValueError as exc:
            raise ProviderError("MiniMax 返回的试听音频不是有效十六进制", code="invalid_provider_response") from exc
        return {"voice_id": created_voice_id, "preview_audio": preview_audio, "request_id": body.get("trace_id", "")}

    def supports_native_streaming(self, model: str) -> bool:
        return model.split("/", 1)[-1] in SUPPORTED_MODELS

    async def stream_synthesize(self, request: SynthesisRequest) -> AsyncIterator[dict]:
        """Stream MP3 chunks from MiniMax's T2A WebSocket endpoint."""
        if not self.api_key:
            raise ProviderError("尚未配置 MiniMax API Key", code="provider_not_configured", status=409)
        model_id = request.model.split("/", 1)[-1]
        if not self.supports_native_streaming(model_id):
            raise ProviderError("当前 MiniMax 模型不受支持", code="unsupported_provider_model", status=400)
        parsed = urlsplit(self.endpoint)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ProviderError("MiniMax Endpoint 无法转换为 WebSocket 地址", code="invalid_endpoint", status=400)
        websocket_scheme = "wss" if parsed.scheme == "https" else "ws"
        websocket_url = f"{websocket_scheme}://{parsed.netloc}/ws/v1/t2a_v2"
        start_payload = {
            "event": "task_start",
            "model": model_id,
            "voice_setting": {
                "voice_id": request.voice,
                "speed": max(0.5, min(2.0, request.speed)),
                "vol": 1,
                "pitch": 0,
            },
            "audio_setting": {
                "sample_rate": 32000,
                "bitrate": 128000,
                "format": "mp3",
                "channel": 1,
            },
        }
        try:
            async with websockets.connect(
                websocket_url,
                additional_headers={"Authorization": f"Bearer {self.api_key}"},
                open_timeout=20,
                close_timeout=10,
            ) as websocket:
                await websocket.send(json.dumps(start_payload, ensure_ascii=False))
                sent_text = False
                sent_finish = False
                request_id = ""
                duration_ms = 0
                emitted = False
                while True:
                    raw = await websocket.recv()
                    if isinstance(raw, bytes):
                        raw = raw.decode("utf-8")
                    try:
                        item = json.loads(raw)
                    except (TypeError, ValueError) as exc:
                        raise ProviderError("MiniMax WebSocket 返回了无法解析的数据", code="invalid_provider_response") from exc
                    base_resp = item.get("base_resp") or {}
                    status_code = base_resp.get("status_code", 0)
                    if status_code not in {0, None}:
                        status = 401 if status_code == 1004 else 502
                        raise ProviderError(
                            f"MiniMax 流式合成失败：{base_resp.get('status_msg') or status_code}",
                            code="minimax_stream_failed",
                            status=status,
                        )
                    event = item.get("event")
                    request_id = str(item.get("trace_id") or request_id)
                    if event == "task_started" and not sent_text:
                        await websocket.send(json.dumps({"event": "task_continue", "text": request.text}, ensure_ascii=False))
                        sent_text = True
                    elif event == "task_continued":
                        encoded = (item.get("data") or {}).get("audio")
                        if encoded:
                            try:
                                audio = bytes.fromhex(encoded)
                            except (TypeError, ValueError) as exc:
                                raise ProviderError("MiniMax 返回的音频分片无效", code="invalid_provider_response") from exc
                            if audio:
                                emitted = True
                                yield {"audio": audio}
                        extra_info = item.get("extra_info") or {}
                        duration_ms = int(extra_info.get("audio_length") or duration_ms or 0)
                        if item.get("is_final") and not sent_finish:
                            await websocket.send(json.dumps({"event": "task_finish"}))
                            sent_finish = True
                    elif event == "task_finished":
                        if not emitted:
                            raise ProviderError("MiniMax 没有返回音频数据", code="invalid_provider_response")
                        yield {"done": True, "provider_request_id": request_id, "duration_ms": duration_ms}
                        return
                    elif event == "task_failed":
                        raise ProviderError("MiniMax 流式合成失败", code="minimax_stream_failed")
        except ProviderError:
            raise
        except websockets.exceptions.WebSocketException as exc:
            raise ProviderError("无法连接 MiniMax WebSocket 语音接口", code="provider_unreachable") from exc
        except (OSError, asyncio.TimeoutError) as exc:
            raise ProviderError("MiniMax WebSocket 语音接口连接失败", code="provider_unreachable") from exc

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}

    async def synthesize(self, request: SynthesisRequest, output: Path) -> dict:
        model_id = request.model.split("/", 1)[-1]
        if model_id not in SUPPORTED_MODELS:
            raise ProviderError("当前 MiniMax 模型不受支持", code="unsupported_provider_model", status=400)
        payload = {
            "model": model_id,
            "text": request.text,
            "stream": False,
            "voice_setting": {"voice_id": request.voice, "speed": request.speed, "vol": 1, "pitch": 0},
            "audio_setting": {"sample_rate": 32000, "bitrate": 128000, "format": "mp3", "channel": 1},
            "output_format": "hex",
        }
        try:
            async with httpx.AsyncClient(timeout=180) as client:
                response = await client.post(self.endpoint + "/t2a_v2", headers=self._headers(), json=payload)
        except httpx.HTTPError as exc:
            raise ProviderError("无法连接 MiniMax 语音接口", code="provider_unreachable") from exc
        if response.status_code != 200:
            status = 401 if response.status_code in {401, 403} else 502
            raise ProviderError(_remote_message(response, "MiniMax 语音合成失败"), code="minimax_synthesis_failed", status=status)
        try:
            body = response.json()
        except ValueError as exc:
            raise ProviderError("MiniMax 返回了无法解析的数据", code="invalid_provider_response") from exc
        audio = _decode_audio(body)
        output.parent.mkdir(parents=True, exist_ok=True)
        source = output.with_name(output.stem + ".source.mp3")
        source.write_bytes(audio)
        try:
            converted = subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(source), "-acodec", "pcm_s16le", str(output)], capture_output=True, text=True, timeout=120)
            if converted.returncode != 0:
                raise ValueError("ffmpeg failed")
            duration = (body.get("extra_info") or {}).get("audio_length")
            if not duration:
                probe = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json", str(output)], capture_output=True, text=True, timeout=30)
                duration = round(float(json.loads(probe.stdout)["format"]["duration"]) * 1000)
        except (OSError, subprocess.SubprocessError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
            output.unlink(missing_ok=True)
            raise ProviderError("MiniMax 返回的音频无法转换", code="invalid_audio_response") from exc
        finally:
            source.unlink(missing_ok=True)
        return {"provider_request_id": body.get("trace_id", ""), "duration_ms": int(duration), "demo": False}

    async def _upload(self, audio: bytes, filename: str, purpose: str) -> int:
        try:
            async with httpx.AsyncClient(timeout=180) as client:
                response = await client.post(self.endpoint + "/files/upload", headers={"Authorization": f"Bearer {self.api_key}"}, data={"purpose": purpose}, files={"file": (filename, audio, "audio/" + Path(filename).suffix.lstrip("."))})
        except httpx.HTTPError as exc:
            raise ProviderError("无法连接 MiniMax 文件上传接口", code="provider_unreachable") from exc
        if response.status_code != 200:
            status = 401 if response.status_code in {401, 403} else 502
            raise ProviderError(_remote_message(response, "MiniMax 音频上传失败"), code="minimax_upload_failed", status=status)
        try:
            body = response.json()
            file_id = int((body.get("file") or {})["file_id"])
            return file_id
        except (KeyError, TypeError, ValueError) as exc:
            raise ProviderError("MiniMax 上传接口未返回有效 file_id", code="invalid_provider_response") from exc

    async def clone_voice(self, audio: bytes, audio_format: str, voice_id: str, model_id: str) -> dict:
        file_id = await self._upload(audio, "clone_input." + audio_format, "voice_clone")
        payload = {"file_id": file_id, "voice_id": voice_id}
        try:
            async with httpx.AsyncClient(timeout=240) as client:
                response = await client.post(self.endpoint + "/voice_clone", headers=self._headers(), json=payload)
        except httpx.HTTPError as exc:
            raise ProviderError("无法连接 MiniMax 音色复刻接口", code="provider_unreachable") from exc
        if response.status_code != 200:
            status = 401 if response.status_code in {401, 403} else 502
            raise ProviderError(_remote_message(response, "MiniMax 音色复刻失败"), code="minimax_clone_failed", status=status)
        try:
            body = response.json()
            base_resp = body.get("base_resp") or {}
            if base_resp.get("status_code", 0) not in {0, None}:
                raise ValueError(base_resp.get("status_msg") or base_resp.get("status_code"))
        except (TypeError, ValueError) as exc:
            raise ProviderError(f"MiniMax 音色复刻失败：{str(exc)[:200]}", code="minimax_clone_failed", status=502) from exc
        return {"voice_id": voice_id, "preview_url": body.get("demo_audio", ""), "request_id": body.get("trace_id", "")}

    async def list_cloned_voices(self) -> list[dict]:
        try:
            async with httpx.AsyncClient(timeout=60) as client:
                response = await client.post(
                    self.endpoint + "/get_voice",
                    headers=self._headers(),
                    json={"voice_type": "voice_cloning"},
                )
        except httpx.HTTPError as exc:
            raise ProviderError("无法连接 MiniMax 音色管理接口", code="provider_unreachable") from exc
        if response.status_code != 200:
            status = 401 if response.status_code in {401, 403} else 502
            raise ProviderError(
                _remote_message(response, "读取 MiniMax 云端音色失败"),
                code="minimax_voice_list_failed",
                status=status,
            )
        try:
            body = response.json()
            base_resp = body.get("base_resp") or {}
            if base_resp.get("status_code", 0) not in {0, None}:
                raise ProviderError(
                    f"读取 MiniMax 云端音色失败：{base_resp.get('status_msg') or '未知业务错误'}",
                    code="minimax_voice_list_failed",
                )
            items = body.get("voice_cloning") or []
            if not isinstance(items, list):
                raise ValueError("invalid voice_cloning")
        except ProviderError:
            raise
        except (TypeError, ValueError) as exc:
            raise ProviderError("MiniMax 返回的音色列表无效", code="invalid_provider_response") from exc
        return [
            {
                "provider_voice_id": str(item["voice_id"]),
                "model_id": "speech-2.8-turbo",
                "display_name": str(item.get("voice_name") or item["voice_id"]),
                "language": "",
                "created_at": str(item.get("created_time") or ""),
            }
            for item in items
            if isinstance(item, dict) and item.get("voice_id")
        ]
