import asyncio
import base64
import json
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

import httpx

from app.providers.base import SynthesisRequest
from app.providers.base import ProviderError
from app.providers.qwen import QWEN_MODELS, QwenProvider


class QwenVoiceListTests(unittest.TestCase):
    def test_catalog_exposes_only_non_realtime_design_models(self):
        design_models = {item.model_id: item for item in QWEN_MODELS if "design" in item.operations}
        self.assertEqual(
            set(design_models),
            {
                "qwen3-tts-vd-2026-01-26",
                "cosyvoice-v3-flash",
                "cosyvoice-v3-plus",
                "cosyvoice-v3.5-flash",
                "cosyvoice-v3.5-plus",
                "qwen-audio-3.0-tts-flash",
                "qwen-audio-3.0-tts-plus",
            },
        )
        self.assertFalse(any("realtime" in model_id for model_id in design_models))

    def test_voice_design_uses_design_model_and_decodes_preview_audio(self):
        preview = b"RIFFtestWAVE"

        async def handler(request: httpx.Request) -> httpx.Response:
            self.assertEqual(request.url.path, "/api/v1/services/audio/tts/customization")
            payload = json.loads(request.content)
            self.assertEqual(payload["model"], "qwen-voice-design")
            self.assertEqual(
                payload["input"],
                {
                    "action": "create",
                    "target_model": "qwen3-tts-vd-2026-01-26",
                    "preferred_name": "vs_test",
                    "voice_prompt": "清晰温和的年轻女声",
                    "preview_text": "你好，这是试听。",
                },
            )
            self.assertEqual(payload["parameters"], {"sample_rate": 24000, "response_format": "wav"})
            return httpx.Response(
                200,
                json={
                    "output": {
                        "voice": "qwen_vd_test",
                        "preview_audio": {"data": base64.b64encode(preview).decode("ascii")},
                    },
                    "request_id": "request-test",
                },
            )

        real_client = httpx.AsyncClient
        transport = httpx.MockTransport(handler)
        with patch("app.providers.qwen.httpx.AsyncClient", side_effect=lambda **kwargs: real_client(transport=transport, **kwargs)):
            result = asyncio.run(
                QwenProvider("secret").create_voice_design(
                    "清晰温和的年轻女声",
                    "你好，这是试听。",
                    "qwen3-tts-vd-2026-01-26",
                    "vs_test",
                )
            )
        self.assertEqual(result["voice_id"], "qwen_vd_test")
        self.assertEqual(result["preview_audio"], preview)
        self.assertEqual(result["request_id"], "request-test")

    def test_voice_enrollment_design_uses_voice_id_response(self):
        preview = b"RIFFtestWAVE"

        async def handler(request: httpx.Request) -> httpx.Response:
            payload = json.loads(request.content)
            self.assertEqual(payload["model"], "voice-enrollment")
            self.assertEqual(
                payload["input"],
                {
                    "action": "create_voice",
                    "target_model": "cosyvoice-v3.5-plus",
                    "voice_prompt": "沉稳的中年男性，音色低沉浑厚",
                    "preview_text": "各位听众朋友们大家好，欢迎收听本期节目",
                    "prefix": "vstest1234",
                    "language_hints": ["zh"],
                },
            )
            return httpx.Response(
                200,
                json={
                    "output": {
                        "voice_id": "cosyvoice-v3.5-plus-vd-test",
                        "preview_audio": {"data": base64.b64encode(preview).decode("ascii")},
                    },
                    "request_id": "request-enrollment",
                },
            )

        real_client = httpx.AsyncClient
        transport = httpx.MockTransport(handler)
        with patch("app.providers.qwen.httpx.AsyncClient", side_effect=lambda **kwargs: real_client(transport=transport, **kwargs)):
            result = asyncio.run(
                QwenProvider("secret").create_voice_design(
                    "沉稳的中年男性，音色低沉浑厚",
                    "各位听众朋友们大家好，欢迎收听本期节目",
                    "cosyvoice-v3.5-plus",
                    "vs_test-123456",
                )
            )
        self.assertEqual(result["voice_id"], "cosyvoice-v3.5-plus-vd-test")
        self.assertEqual(result["preview_audio"], preview)

    def test_voice_enrollment_validates_text_limits_before_request(self):
        provider = QwenProvider("secret")
        with self.assertRaisesRegex(ProviderError, "最多 500"):
            asyncio.run(provider.create_voice_design("声" * 501, "这是一段足够长的试听文本内容", "cosyvoice-v3-flash", "test"))
        with self.assertRaisesRegex(ProviderError, "15 到 200"):
            asyncio.run(provider.create_voice_design("清晰自然的年轻女声", "文本太短", "qwen-audio-3.0-tts-flash", "test"))
        with self.assertRaisesRegex(ProviderError, "15 到 200"):
            asyncio.run(provider.create_voice_design("清晰自然的年轻女声", "试" * 201, "qwen-audio-3.0-tts-flash", "test"))

    def test_qwen_audio_synthesis_downloads_returned_audio_url(self):
        requests: list[tuple[str, str]] = []
        audio = b"RIFFtestWAVE"

        async def handler(request: httpx.Request) -> httpx.Response:
            requests.append((request.method, request.url.path))
            if request.method == "POST":
                payload = json.loads(request.content)
                self.assertEqual(payload["model"], "qwen-audio-3.0-tts-flash")
                self.assertEqual(
                    payload["input"],
                    {"text": "你好", "voice": "voice-test", "format": "wav", "sample_rate": 24000},
                )
                return httpx.Response(200, json={"output": {"audio": {"url": "https://audio.example/test.wav"}}, "request_id": "request-audio"})
            return httpx.Response(200, content=audio)

        real_client = httpx.AsyncClient
        transport = httpx.MockTransport(handler)
        with tempfile.TemporaryDirectory() as folder, patch(
            "app.providers.qwen.httpx.AsyncClient",
            side_effect=lambda **kwargs: real_client(transport=transport, **kwargs),
        ), patch("app.providers.qwen._write_wav", return_value=1234) as write_wav:
            output = Path(folder) / "result.wav"
            result = asyncio.run(
                QwenProvider("secret").synthesize(
                    SynthesisRequest("dashscope/qwen-audio-3.0-tts-flash", "voice-test", "你好"),
                    output,
                )
            )
        write_wav.assert_called_once_with(audio, output, 1.0)
        self.assertEqual(result["duration_ms"], 1234)
        self.assertEqual(requests, [("POST", "/api/v1/services/audio/tts/SpeechSynthesizer"), ("GET", "/test.wav")])

    def test_lists_paginated_voices_with_bound_model(self):
        requests = []

        async def handler(request: httpx.Request) -> httpx.Response:
            payload = json.loads(request.content)
            requests.append(payload["input"])
            page = payload["input"]["page_index"]
            if page == 0:
                return httpx.Response(
                    200,
                    json={
                        "output": {
                            "page_index": 0,
                            "page_size": 1,
                            "total_count": 2,
                            "voice_list": [{"voice": "qwen_voice_1", "target_model": "qwen3-tts-vc-2026-01-22", "language": "zh", "gmt_create": "2026-01-01"}],
                        }
                    },
                )
            return httpx.Response(
                200,
                json={
                    "output": {
                        "page_index": 1,
                        "page_size": 1,
                        "total_count": 2,
                        "voice_list": [{"voice": "qwen_voice_2", "target_model": "qwen3-tts-vc-realtime-2026-01-15", "language": "zh", "gmt_create": "2026-01-02"}],
                    }
                },
            )

        real_client = httpx.AsyncClient
        transport = httpx.MockTransport(handler)
        with patch("app.providers.qwen.httpx.AsyncClient", side_effect=lambda **kwargs: real_client(transport=transport, **kwargs)):
            voices = asyncio.run(QwenProvider("secret").list_cloned_voices())
        self.assertEqual(len(voices), 2)
        self.assertEqual(voices[0]["model_id"], "qwen3-tts-vc-2026-01-22")
        self.assertEqual(requests[1]["page_index"], 1)

    def test_cosyvoice_native_stream_bridges_sdk_callbacks(self):
        class FakeSynthesizer:
            def __init__(self, **kwargs):
                self.callback = kwargs["callback"]
                self.closed = False

            def streaming_call(self, text):
                self.callback.on_data(b"cosy-one")
                self.callback.on_data(b"cosy-two")

            def streaming_complete(self):
                pass

            def get_last_request_id(self):
                return "cosy-request"

            def close(self):
                self.closed = True

        async def run():
            items = []
            with patch(
                "dashscope.audio.tts_v2.SpeechSynthesizer",
                FakeSynthesizer,
            ):
                async for item in QwenProvider("secret").stream_synthesize(
                    SynthesisRequest(
                        "dashscope/cosyvoice-v3-flash",
                        "longanyang",
                        "hello",
                        format="mp3",
                    )
                ):
                    items.append(item)
            return items

        items = asyncio.run(run())
        self.assertEqual(items[0]["audio"], b"cosy-one")
        self.assertEqual(items[1]["audio"], b"cosy-two")
        self.assertEqual(items[-1]["provider_request_id"], "cosy-request")

    def test_cosyvoice_native_stream_closes_sdk_on_cancellation(self):
        closed = threading.Event()

        class FakeSynthesizer:
            def __init__(self, **kwargs):
                self.callback = kwargs["callback"]

            def streaming_call(self, text):
                self.callback.on_data(b"first-chunk")

            def streaming_complete(self):
                closed.wait(timeout=2)

            def get_last_request_id(self):
                return "cancel-request"

            def close(self):
                closed.set()

        async def run():
            with patch("dashscope.audio.tts_v2.SpeechSynthesizer", FakeSynthesizer):
                stream = QwenProvider("secret").stream_synthesize(
                    SynthesisRequest(
                        "dashscope/cosyvoice-v3-flash",
                        "longanyang",
                        "hello",
                        format="mp3",
                    )
                )
                first = await anext(stream)
                await stream.aclose()
                return first

        first = asyncio.run(run())
        self.assertEqual(first["audio"], b"first-chunk")
        self.assertTrue(closed.is_set())


if __name__ == "__main__":
    unittest.main()
