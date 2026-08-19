from __future__ import annotations

import asyncio
import base64
import json
import subprocess
from pathlib import Path
from typing import AsyncIterator

import httpx

from .base import ProviderError, ProviderModel, SpeechProvider, SynthesisRequest


DEFAULT_ENDPOINT = "https://dashscope.aliyuncs.com"
TTS_PATH = "/api/v1/services/aigc/multimodal-generation/generation"
VOICE_PATH = "/api/v1/services/audio/tts/customization"

QWEN_MODELS = [
    ProviderModel(
        "dashscope",
        "qwen3-tts-flash",
        "Qwen3 TTS Flash",
        "tts",
        "均衡",
        "快",
        ["zh-CN", "en-US", "ja-JP", "ko-KR"],
        False,
        "provider",
        ["synthesis"],
    ),
    ProviderModel(
        "dashscope",
        "qwen3-tts-instruct-flash",
        "Qwen3 TTS Instruct Flash",
        "tts",
        "可控",
        "快",
        ["zh-CN", "en-US", "ja-JP", "ko-KR"],
        False,
        "provider",
        ["synthesis"],
    ),
    ProviderModel(
        "dashscope",
        "qwen3-tts-vc-2026-01-22",
        "Qwen3 TTS VC 2026-01-22",
        "voice_clone",
        "复刻",
        "中",
        ["zh-CN", "en-US", "ja-JP", "ko-KR", "fr-FR", "de-DE"],
        True,
        "provider",
        ["synthesis", "clone"],
    ),
    ProviderModel(
        "dashscope",
        "cosyvoice-v3-flash",
        "CosyVoice V3 Flash",
        "tts",
        "自然",
        "快",
        ["zh-CN", "en-US", "ja-JP", "ko-KR"],
        False,
        "provider",
        ["synthesis"],
    ),
    ProviderModel(
        "dashscope",
        "cosyvoice-v3-plus",
        "CosyVoice V3 Plus",
        "tts",
        "专业",
        "中",
        ["zh-CN", "en-US", "ja-JP", "ko-KR"],
        False,
        "provider",
        ["synthesis"],
    ),
    ProviderModel(
        "dashscope",
        "qwen3-tts-vd-2026-01-26",
        "Qwen3 TTS VoiceDesign 2026-01-26",
        "voice_design",
        "设计",
        "中",
        ["zh-CN", "en-US"],
        False,
        "provider",
        ["synthesis", "design"],
    ),
]


def _remote_error(response: httpx.Response, fallback: str) -> str:
    try:
        body = response.json()
        message = body.get("message") or body.get("error", {}).get("message")
        if message:
            return f"{fallback}：{str(message)[:240]}"
    except (TypeError, ValueError):
        pass
    return f"{fallback}（HTTP {response.status_code}）"


def _atempo_filter(speed: float) -> str | None:
    if abs(speed - 1.0) < 0.001:
        return None
    factors: list[float] = []
    remaining = speed
    while remaining < 0.5:
        factors.append(0.5)
        remaining /= 0.5
    while remaining > 2.0:
        factors.append(2.0)
        remaining /= 2.0
    factors.append(remaining)
    return ",".join(f"atempo={factor:.6g}" for factor in factors)


def _write_wav(audio: bytes, output: Path, speed: float) -> int:
    output.parent.mkdir(parents=True, exist_ok=True)
    is_wav = len(audio) >= 12 and audio[:4] == b"RIFF" and audio[8:12] == b"WAVE"
    speed_filter = _atempo_filter(speed)
    if is_wav and speed_filter is None:
        output.write_bytes(audio)
    else:
        source = output.with_name(output.stem + (".source.wav" if is_wav else ".source.mp3"))
        source.write_bytes(audio)
        command = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(source)]
        if speed_filter:
            command += ["-filter:a", speed_filter]
        command += ["-acodec", "pcm_s16le", str(output)]
        try:
            completed = subprocess.run(command, capture_output=True, text=True, timeout=120)
        except (OSError, subprocess.SubprocessError) as exc:
            raise ProviderError("无法转换千问返回的音频", code="audio_conversion_failed") from exc
        finally:
            source.unlink(missing_ok=True)
        if completed.returncode != 0:
            output.unlink(missing_ok=True)
            raise ProviderError("无法转换千问返回的音频", code="audio_conversion_failed")

    try:
        probe = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "json",
                str(output),
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if probe.returncode != 0:
            raise ValueError("ffprobe failed")
        duration_ms = round(float(json.loads(probe.stdout)["format"]["duration"]) * 1000)
        if duration_ms <= 0:
            raise ValueError("invalid duration")
        return duration_ms
    except (OSError, subprocess.SubprocessError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        output.unlink(missing_ok=True)
        raise ProviderError("千问返回的内容不是有效音频", code="invalid_audio_response") from exc


class QwenProvider(SpeechProvider):
    key = "dashscope"

    def __init__(self, api_key: str, endpoint: str = DEFAULT_ENDPOINT):
        self.api_key = api_key
        self.endpoint = endpoint.rstrip("/")

    def models(self) -> list[ProviderModel]:
        return QWEN_MODELS

    async def create_voice_design(
        self,
        prompt: str,
        preview_text: str,
        target_model: str,
        preferred_name: str,
    ) -> dict:
        payload = {
            "model": "qwen-voice-design",
            "input": {
                "action": "create",
                "target_model": target_model,
                "preferred_name": preferred_name,
                "voice_prompt": prompt,
                "preview_text": preview_text,
            },
            "parameters": {"sample_rate": 24000, "response_format": "wav"},
        }
        try:
            async with httpx.AsyncClient(timeout=180) as client:
                response = await client.post(
                    self.endpoint + VOICE_PATH,
                    headers={"Authorization": "Bearer " + self.api_key, "Content-Type": "application/json"},
                    json=payload,
                )
        except httpx.HTTPError as exc:
            raise ProviderError("无法连接千问音色设计接口", code="provider_unreachable") from exc
        if response.status_code != 200:
            raise ProviderError(_remote_error(response, "千问音色设计失败"), code="qwen_voice_design_failed", status=401 if response.status_code in {401, 403} else 502)
        try:
            body = response.json()
            output = body.get("output") or {}
            voice_id = str(output["voice"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ProviderError("千问返回的设计音色数据无效", code="invalid_provider_response") from exc
        preview_audio = b""
        encoded_preview = (output.get("preview_audio") or {}).get("data")
        if encoded_preview:
            try:
                preview_audio = base64.b64decode(encoded_preview, validate=True)
            except (TypeError, ValueError):
                preview_audio = b""
        return {
            "voice_id": voice_id,
            "preview_audio": preview_audio,
            "request_id": body.get("request_id", ""),
        }

    def supports_native_streaming(self, model: str) -> bool:
        return model.split("/", 1)[-1] in {"cosyvoice-v3-flash", "cosyvoice-v3-plus"}

    async def stream_synthesize(self, request: SynthesisRequest) -> AsyncIterator[dict]:
        """Bridge CosyVoice WebSocket callbacks into the gateway async stream."""
        if not self.api_key:
            raise ProviderError("尚未配置通义千问 API Key", code="provider_not_configured", status=409)
        if self.api_key.startswith("sk-sp-"):
            raise ProviderError("Token Plan Key 不支持语音模型，请使用标准 API Key", code="invalid_key_type", status=409)
        model_id = request.model.split("/", 1)[-1]
        if not self.supports_native_streaming(model_id):
            raise ProviderError("当前千问模型不支持原生流式合成", code="native_streaming_not_supported", status=400)
        try:
            import dashscope
            from dashscope.audio.tts_v2 import AudioFormat, ResultCallback, SpeechSynthesizer
        except ImportError as exc:
            raise ProviderError("后端缺少 DashScope SDK，请重新运行启动脚本", code="missing_provider_sdk") from exc

        loop = asyncio.get_running_loop()
        queue: asyncio.Queue[tuple[str, object]] = asyncio.Queue()
        holder: dict[str, object] = {}

        def enqueue(kind: str, payload: object = None) -> None:
            loop.call_soon_threadsafe(queue.put_nowait, (kind, payload))

        class Callback(ResultCallback):
            def on_data(self, data: bytes) -> None:
                if data:
                    enqueue("audio", bytes(data))

            def on_error(self, message) -> None:
                enqueue("error", str(message))

        def call() -> None:
            request_id = ""
            try:
                dashscope.api_key = self.api_key
                dashscope.base_websocket_api_url = "wss://dashscope.aliyuncs.com/api-ws/v1/inference"
                synthesizer = SpeechSynthesizer(
                    model=model_id,
                    voice=request.voice,
                    format=AudioFormat.MP3_24000HZ_MONO_256KBPS,
                    speech_rate=max(0.5, min(2.0, request.speed)),
                    callback=Callback(),
                )
                holder["synthesizer"] = synthesizer
                # ``call`` returns immediately when a callback is configured,
                # which can emit our done marker before SDK audio callbacks run.
                # The explicit streaming lifecycle waits for the provider's
                # completion event while still delivering on_data incrementally.
                synthesizer.streaming_call(request.text)
                synthesizer.streaming_complete()
                try:
                    request_id = synthesizer.get_last_request_id() or ""
                except Exception:
                    request_id = ""
            except Exception as exc:
                enqueue("error", str(exc))
            finally:
                enqueue("done", request_id)

        task = asyncio.create_task(asyncio.to_thread(call))
        try:
            while True:
                kind, payload = await queue.get()
                if kind == "audio":
                    yield {"audio": payload}
                elif kind == "error":
                    raise ProviderError(f"CosyVoice 流式合成失败：{str(payload)[:240]}", code="cosyvoice_stream_failed")
                elif kind == "done":
                    await task
                    yield {"done": True, "provider_request_id": str(payload or "")}
                    return
        finally:
            synthesizer = holder.get("synthesizer")
            if synthesizer and not task.done():
                try:
                    synthesizer.close()
                except Exception:
                    pass

    async def synthesize(self, request: SynthesisRequest, output: Path) -> dict:
        if not self.api_key:
            raise ProviderError("尚未配置通义千问 API Key", code="provider_not_configured", status=409)
        if self.api_key.startswith("sk-sp-"):
            raise ProviderError("Token Plan Key 不支持语音模型，请使用标准 API Key", code="invalid_key_type", status=409)

        model_id = request.model.split("/", 1)[-1]
        if model_id.startswith("qwen3-tts-") and len(request.text) > 600:
            raise ProviderError("Qwen3 TTS 单次最多合成 600 个字符", code="input_too_long", status=400)
        if model_id.startswith("cosyvoice-"):
            return await self._synthesize_cosyvoice(request, output, model_id)

        input_data: dict[str, object] = {
            "text": request.text,
            "voice": request.voice,
            "language_type": "Auto",
        }
        if model_id == "qwen3-tts-instruct-flash" and request.instructions:
            input_data["instructions"] = request.instructions
            input_data["optimize_instructions"] = True
        payload = {"model": model_id, "input": input_data}

        try:
            async with httpx.AsyncClient(timeout=120, follow_redirects=True) as client:
                response = await client.post(
                    self.endpoint + TTS_PATH,
                    headers={"Authorization": "Bearer " + self.api_key, "Content-Type": "application/json"},
                    json=payload,
                )
                if response.status_code != 200:
                    status = 401 if response.status_code in {401, 403} else 502
                    raise ProviderError(
                        _remote_error(response, "通义千问语音合成失败"),
                        code="qwen_synthesis_failed",
                        status=status,
                    )
                body = response.json()
                audio_url = body.get("output", {}).get("audio", {}).get("url")
                if not audio_url:
                    raise ProviderError("千问响应中没有音频地址", code="invalid_provider_response")
                audio_response = await client.get(audio_url)
                audio_response.raise_for_status()
        except ProviderError:
            raise
        except (httpx.HTTPError, ValueError) as exc:
            raise ProviderError("无法连接通义千问语音接口", code="provider_unreachable") from exc

        duration_ms = _write_wav(audio_response.content, output, request.speed)
        return {
            "provider_request_id": body.get("request_id", ""),
            "duration_ms": duration_ms,
            "demo": False,
        }

    async def _synthesize_cosyvoice(self, request: SynthesisRequest, output: Path, model_id: str) -> dict:
        def call() -> bytes:
            try:
                import dashscope
                from dashscope.audio.tts_v2 import SpeechSynthesizer
            except ImportError as exc:
                raise ProviderError("后端缺少 DashScope SDK，请重新运行启动脚本", code="missing_provider_sdk") from exc

            dashscope.api_key = self.api_key
            dashscope.base_websocket_api_url = "wss://dashscope.aliyuncs.com/api-ws/v1/inference"
            try:
                data = SpeechSynthesizer(model=model_id, voice=request.voice).call(request.text)
            except Exception as exc:
                raise ProviderError(f"CosyVoice 合成失败：{str(exc)[:240]}", code="cosyvoice_synthesis_failed") from exc
            if not data:
                raise ProviderError("CosyVoice 没有返回音频数据", code="invalid_provider_response")
            return data

        audio = await asyncio.to_thread(call)
        duration_ms = _write_wav(audio, output, request.speed)
        return {"provider_request_id": "", "duration_ms": duration_ms, "demo": False}

    async def clone_voice(
        self,
        audio: bytes,
        mime_type: str,
        preferred_name: str,
        target_model: str,
    ) -> dict:
        data_uri = f"data:{mime_type};base64,{base64.b64encode(audio).decode('ascii')}"
        payload = {
            "model": "qwen-voice-enrollment",
            "input": {
                "action": "create",
                "target_model": target_model,
                "preferred_name": preferred_name,
                "audio": {"data": data_uri},
            },
        }
        try:
            async with httpx.AsyncClient(timeout=180) as client:
                response = await client.post(
                    self.endpoint + VOICE_PATH,
                    headers={"Authorization": "Bearer " + self.api_key, "Content-Type": "application/json"},
                    json=payload,
                )
        except httpx.HTTPError as exc:
            raise ProviderError("无法连接千问声音复刻接口", code="provider_unreachable") from exc
        if response.status_code != 200:
            status = 401 if response.status_code in {401, 403} else 502
            raise ProviderError(
                _remote_error(response, "千问声音复刻失败"),
                code="qwen_clone_failed",
                status=status,
            )
        try:
            body = response.json()
            result = body["output"]
            voice_id = result["voice"]
        except (KeyError, TypeError, ValueError) as exc:
            raise ProviderError("千问返回的克隆音色数据无效", code="invalid_provider_response") from exc
        return {
            "voice_id": voice_id,
            "request_id": body.get("request_id", ""),
            "fallback_mode": bool(result.get("fallback_mode")),
            "fallback_reason": result.get("fallback_reason", ""),
        }

    async def list_cloned_voices(self) -> list[dict]:
        voices: list[dict] = []
        page_index = 0
        page_size = 100
        try:
            async with httpx.AsyncClient(timeout=60) as client:
                while True:
                    response = await client.post(
                        self.endpoint + VOICE_PATH,
                        headers={"Authorization": "Bearer " + self.api_key, "Content-Type": "application/json"},
                        json={
                            "model": "qwen-voice-enrollment",
                            "input": {"action": "list", "page_index": page_index, "page_size": page_size},
                        },
                    )
                    if response.status_code != 200:
                        status = 401 if response.status_code in {401, 403} else 502
                        raise ProviderError(
                            _remote_error(response, "读取千问云端音色失败"),
                            code="qwen_voice_list_failed",
                            status=status,
                        )
                    body = response.json()
                    output = body.get("output") or {}
                    page = output.get("voice_list") or []
                    if not isinstance(page, list):
                        raise ValueError("invalid voice_list")
                    for item in page:
                        if not isinstance(item, dict) or not item.get("voice"):
                            continue
                        voices.append(
                            {
                                "provider_voice_id": str(item["voice"]),
                                "model_id": str(item.get("target_model") or ""),
                                "display_name": str(item["voice"]),
                                "language": str(item.get("language") or ""),
                                "created_at": str(item.get("gmt_create") or ""),
                            }
                        )
                    total_count = int(output.get("total_count") or len(voices))
                    if not page or len(voices) >= total_count:
                        break
                    page_index += 1
        except ProviderError:
            raise
        except (httpx.HTTPError, TypeError, ValueError) as exc:
            raise ProviderError("无法读取千问云端音色列表", code="provider_unreachable") from exc
        return voices

    async def delete_voice(self, voice_id: str) -> None:
        payload = {"model": "qwen-voice-enrollment", "input": {"action": "delete", "voice": voice_id}}
        try:
            async with httpx.AsyncClient(timeout=60) as client:
                response = await client.post(
                    self.endpoint + VOICE_PATH,
                    headers={"Authorization": "Bearer " + self.api_key, "Content-Type": "application/json"},
                    json=payload,
                )
        except httpx.HTTPError as exc:
            raise ProviderError("无法连接千问音色管理接口", code="provider_unreachable") from exc
        if response.status_code != 200:
            raise ProviderError(_remote_error(response, "删除千问远端音色失败"), code="qwen_voice_delete_failed")
