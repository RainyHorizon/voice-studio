from __future__ import annotations

import base64
import binascii
import json
import wave
from pathlib import Path
from typing import AsyncIterator

import httpx

from .base import ProviderError, ProviderModel, SpeechProvider, SynthesisRequest


DEFAULT_ENDPOINT = "https://api.xiaomimimo.com/v1"

MIMO_MODELS = [
    ProviderModel(
        "mimo",
        "mimo-v2.5-tts",
        "MiMo V2.5 TTS",
        "tts",
        "自然",
        "快",
        ["zh-CN", "en-US"],
        False,
        "provider",
        ["synthesis"],
    ),
    ProviderModel(
        "mimo",
        "mimo-v2.5-tts-voiceclone",
        "MiMo V2.5 TTS VoiceClone",
        "voice_clone",
        "复刻",
        "中",
        ["zh-CN", "en-US"],
        True,
        "provider",
        ["synthesis", "clone"],
    ),
    ProviderModel(
        "mimo",
        "mimo-v2.5-tts-voicedesign",
        "MiMo V2.5 TTS VoiceDesign",
        "voice_design",
        "设计",
        "中",
        ["zh-CN", "en-US"],
        False,
        "provider",
        ["synthesis", "design"],
    ),
]

# VoiceDesign currently returns a completed result wrapped as a stream; it does
# not provide low-latency native PCM chunks.
MIMO_STREAMING_MODELS = {"mimo-v2.5-tts", "mimo-v2.5-tts-voiceclone"}


class MiMoProvider(SpeechProvider):
    key = "mimo"

    def __init__(self, api_key: str, endpoint: str = DEFAULT_ENDPOINT):
        self.api_key = api_key
        self.endpoint = endpoint.rstrip("/")

    def models(self) -> list[ProviderModel]:
        return MIMO_MODELS

    def supports_native_streaming(self, model: str) -> bool:
        """MiMo's native audio stream is PCM16 for all current TTS models."""
        return model.split("/", 1)[-1] in MIMO_STREAMING_MODELS

    def native_stream_format(self, model: str) -> str:
        return "pcm"

    @staticmethod
    def _remote_message(response: httpx.Response, fallback: str) -> str:
        try:
            body = response.json()
            remote_message = body.get("error", {}).get("message") or body.get("message")
            if remote_message:
                return f"{fallback}：{str(remote_message)[:240]}"
        except (TypeError, ValueError):
            pass
        return f"{fallback}（HTTP {response.status_code}）"

    @staticmethod
    def _stream_audio(payload: dict) -> bytes | None:
        try:
            choices = payload.get("choices") or []
            if not choices:
                return None
            choice = choices[0]
            if not isinstance(choice, dict):
                return None
            delta = choice.get("delta") or {}
            if not isinstance(delta, dict):
                return None
            audio = delta.get("audio")
            encoded = audio.get("data") if isinstance(audio, dict) else None
            if not encoded:
                return None
            return base64.b64decode(encoded, validate=True)
        except (KeyError, IndexError, TypeError, ValueError, binascii.Error) as exc:
            raise ProviderError("小米 MiMo 返回的流式音频分片无效", code="invalid_provider_response") from exc

    async def stream_synthesize(self, request: SynthesisRequest) -> AsyncIterator[dict]:
        """Yield MiMo's native SSE PCM16 chunks without buffering the full result."""
        if not self.api_key:
            raise ProviderError("尚未配置小米 MiMo API Key", code="provider_not_configured", status=409)
        model_id = request.model.split("/", 1)[-1]
        if not self.supports_native_streaming(model_id):
            raise ProviderError("当前小米 MiMo 模型不支持原生流式合成", code="unsupported_provider_model", status=400)

        instruction = request.instructions or "请用自然、清晰的语气朗读。"
        if request.speed != 1.0:
            instruction += f" 语速调整为自然语速的约 {request.speed:.1f} 倍。"
        audio: dict[str, str] = {"format": "pcm16"}
        if request.voice and model_id != "mimo-v2.5-tts-voicedesign":
            audio["voice"] = request.voice
        payload = {
            "model": model_id,
            "messages": [
                {"role": "user", "content": instruction},
                {"role": "assistant", "content": request.text},
            ],
            "audio": audio,
            "stream": True,
        }
        provider_request_id = ""
        total_bytes = 0
        emitted = False
        try:
            async with httpx.AsyncClient(timeout=180) as client:
                async with client.stream(
                    "POST",
                    self.endpoint + "/chat/completions",
                    headers={"api-key": self.api_key, "Content-Type": "application/json", "Accept": "text/event-stream"},
                    json=payload,
                ) as response:
                    if response.status_code != 200:
                        await response.aread()
                        status = 401 if response.status_code in {401, 403} else 502
                        raise ProviderError(self._remote_message(response, "小米 MiMo 流式语音合成失败"), code="mimo_stream_failed", status=status)
                    async for line in response.aiter_lines():
                        line = line.strip()
                        if not line or line.startswith(":"):
                            continue
                        if line.startswith("data:"):
                            line = line[5:].strip()
                        if line == "[DONE]":
                            break
                        try:
                            item = json.loads(line)
                        except (TypeError, ValueError) as exc:
                            raise ProviderError("小米 MiMo 流式响应不是有效 JSON", code="invalid_provider_response") from exc
                        provider_request_id = str(item.get("id") or provider_request_id)
                        chunk = self._stream_audio(item)
                        if chunk:
                            emitted = True
                            total_bytes += len(chunk)
                            yield {"audio": chunk}
        except ProviderError:
            raise
        except httpx.HTTPError as exc:
            raise ProviderError("无法连接小米 MiMo 流式语音接口", code="provider_unreachable") from exc
        if not emitted:
            raise ProviderError("小米 MiMo 流式接口没有返回音频数据", code="invalid_provider_response")
        # Official streaming output is 24 kHz, 16-bit little-endian, mono PCM.
        yield {
            "done": True,
            "provider_request_id": provider_request_id,
            "duration_ms": round(total_bytes / (24000 * 2) * 1000),
            "sample_rate": 24000,
            "channels": 1,
            "bit_depth": 16,
        }

    async def synthesize(self, request: SynthesisRequest, output: Path) -> dict:
        if not self.api_key:
            raise ProviderError("尚未配置小米 MiMo API Key", code="provider_not_configured", status=409)

        instruction = request.instructions or "请用自然、清晰的语气朗读。"
        if request.speed != 1.0:
            instruction += f" 语速调整为自然语速的约 {request.speed:.1f} 倍。"
        model_id = request.model.split("/", 1)[-1]
        audio: dict[str, str] = {"format": "wav"}
        if request.voice and model_id != "mimo-v2.5-tts-voicedesign":
            audio["voice"] = request.voice
        payload = {
            "model": model_id,
            "messages": [
                {"role": "user", "content": instruction},
                {"role": "assistant", "content": request.text},
            ],
            "audio": audio,
        }

        try:
            async with httpx.AsyncClient(timeout=120) as client:
                response = await client.post(
                    self.endpoint + "/chat/completions",
                    headers={"api-key": self.api_key, "Content-Type": "application/json"},
                    json=payload,
                )
        except httpx.HTTPError as exc:
            raise ProviderError("无法连接小米 MiMo 语音接口", code="provider_unreachable") from exc

        if response.status_code != 200:
            message = "小米 MiMo 语音合成失败"
            try:
                body = response.json()
                remote_message = body.get("error", {}).get("message") or body.get("message")
                if remote_message:
                    message += f"：{str(remote_message)[:240]}"
            except ValueError:
                pass
            status = 401 if response.status_code in {401, 403} else 502
            raise ProviderError(message, code="mimo_synthesis_failed", status=status)

        try:
            body = response.json()
            audio_data = body["choices"][0]["message"]["audio"]["data"]
            audio_bytes = base64.b64decode(audio_data, validate=True)
        except (KeyError, IndexError, TypeError, ValueError, binascii.Error) as exc:
            raise ProviderError("小米 MiMo 返回的音频数据无效", code="invalid_provider_response") from exc

        if len(audio_bytes) < 44 or audio_bytes[:4] != b"RIFF" or audio_bytes[8:12] != b"WAVE":
            raise ProviderError("小米 MiMo 返回的内容不是有效 WAV 音频", code="invalid_audio_response")

        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(audio_bytes)
        try:
            with wave.open(str(output), "rb") as stream:
                duration_ms = round(stream.getnframes() / stream.getframerate() * 1000)
        except (wave.Error, ZeroDivisionError) as exc:
            output.unlink(missing_ok=True)
            raise ProviderError("无法读取小米 MiMo 返回的 WAV 音频", code="invalid_audio_response") from exc

        return {
            "provider_request_id": body.get("id", ""),
            "duration_ms": duration_ms,
            "demo": False,
        }
