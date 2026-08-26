import asyncio
import json
import tempfile
import unittest
import wave
from pathlib import Path
from unittest.mock import patch

import httpx

from app.providers.base import SynthesisRequest
from app.providers.base import ProviderError
from app.providers.minimax import MINIMAX_MODELS, MiniMaxProvider


class MiniMaxProviderTests(unittest.TestCase):
    def test_voice_design_has_a_dedicated_catalog_model(self):
        models = {item.model_id: item for item in MINIMAX_MODELS}
        self.assertNotIn("design", models["speech-2.8-turbo"].operations)
        self.assertEqual(models["minimax-voice-design"].operations, ["design"])

    def test_voice_design_does_not_send_a_synthesis_model(self):
        async def handler(request: httpx.Request) -> httpx.Response:
            self.assertEqual(request.url.path, "/v1/voice_design")
            payload = json.loads(request.content)
            self.assertEqual(
                payload,
                {"prompt": "温和沉稳的成年男声", "preview_text": "你好，这是试听文本。", "voice_id": "vs_test"},
            )
            self.assertNotIn("model", payload)
            return httpx.Response(
                200,
                json={
                    "voice_id": "vs_test",
                    "trial_audio": "",
                    "trace_id": "trace-design",
                    "base_resp": {"status_code": 0},
                },
            )

        real_client = httpx.AsyncClient
        transport = httpx.MockTransport(handler)
        with patch("app.providers.minimax.httpx.AsyncClient", side_effect=lambda **kwargs: real_client(transport=transport, **kwargs)):
            result = asyncio.run(
                MiniMaxProvider("secret").create_voice_design(
                    "温和沉稳的成年男声",
                    "你好，这是试听文本。",
                    "vs_test",
                )
            )
        self.assertEqual(result["voice_id"], "vs_test")

    def test_business_error_is_preserved(self):
        async def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"data": None, "base_resp": {"status_code": 1008, "status_msg": "余额不足"}})

        real_client = httpx.AsyncClient
        transport = httpx.MockTransport(handler)
        with tempfile.TemporaryDirectory() as folder, patch("app.providers.minimax.httpx.AsyncClient", side_effect=lambda **kwargs: real_client(transport=transport, **kwargs)):
            with self.assertRaisesRegex(ProviderError, "余额不足.*1008"):
                asyncio.run(MiniMaxProvider("secret").synthesize(SynthesisRequest("minimax/speech-2.8-turbo", "presenter_male", "你好"), Path(folder) / "result.wav"))

    def test_synthesis_decodes_hex_and_writes_wav(self):
        async def handler(request: httpx.Request) -> httpx.Response:
            self.assertEqual(request.url.path, "/v1/t2a_v2")
            payload = json.loads(request.content)
            self.assertEqual(payload["model"], "speech-2.8-turbo")
            self.assertEqual(payload["voice_setting"]["voice_id"], "presenter_male")
            return httpx.Response(200, json={"data": {"audio": "49443304000000000000", "status": 2}, "extra_info": {"audio_length": 1200}, "trace_id": "trace_test", "base_resp": {"status_code": 0, "status_msg": "success"}})

        real_client = httpx.AsyncClient
        transport = httpx.MockTransport(handler)

        def run_command(command, **kwargs):
            output = Path(command[-1])
            with wave.open(str(output), "wb") as stream:
                stream.setnchannels(1)
                stream.setsampwidth(2)
                stream.setframerate(24000)
                stream.writeframes(b"\x00\x00" * 240)
            return type("Result", (), {"returncode": 0, "stdout": ""})()

        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / "result.wav"
            with patch("app.providers.minimax.httpx.AsyncClient", side_effect=lambda **kwargs: real_client(transport=transport, **kwargs)), patch("app.providers.minimax.subprocess.run", side_effect=run_command):
                result = asyncio.run(MiniMaxProvider("secret").synthesize(SynthesisRequest("minimax/speech-2.8-turbo", "presenter_male", "你好"), output))
            self.assertTrue(output.is_file())
            self.assertEqual(result["duration_ms"], 1200)
            self.assertFalse(result["demo"])

    def test_clone_uploads_audio_then_creates_voice(self):
        requests = []

        async def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request.url.path)
            if request.url.path == "/v1/files/upload":
                self.assertIn(b'name="purpose"', request.content)
                self.assertIn(b"voice_clone", request.content)
                return httpx.Response(200, json={"file": {"file_id": 12345}, "base_resp": {"status_code": 0}})
            if request.url.path == "/v1/voice_clone":
                payload = json.loads(request.content)
                self.assertEqual(payload, {"file_id": 12345, "voice_id": "vs_testvoice"})
                return httpx.Response(200, json={"demo_audio": "", "base_resp": {"status_code": 0, "status_msg": "success"}})
            return httpx.Response(404)

        real_client = httpx.AsyncClient
        transport = httpx.MockTransport(handler)
        with patch("app.providers.minimax.httpx.AsyncClient", side_effect=lambda **kwargs: real_client(transport=transport, **kwargs)):
            result = asyncio.run(MiniMaxProvider("secret").clone_voice(b"audio", "wav", "vs_testvoice", "speech-2.8-hd"))
        self.assertEqual(result["voice_id"], "vs_testvoice")
        self.assertEqual(requests, ["/v1/files/upload", "/v1/voice_clone"])

    def test_lists_only_cloned_voices(self):
        async def handler(request: httpx.Request) -> httpx.Response:
            self.assertEqual(request.url.path, "/v1/get_voice")
            self.assertEqual(json.loads(request.content), {"voice_type": "voice_cloning"})
            return httpx.Response(
                200,
                json={
                    "voice_cloning": [
                        {"voice_id": "vs_old", "created_time": "2026-01-01"},
                        {"voice_id": "vs_new", "voice_name": "我的声音", "created_time": "2026-02-01"},
                    ],
                    "base_resp": {"status_code": 0},
                },
            )

        real_client = httpx.AsyncClient
        transport = httpx.MockTransport(handler)
        with patch("app.providers.minimax.httpx.AsyncClient", side_effect=lambda **kwargs: real_client(transport=transport, **kwargs)):
            voices = asyncio.run(MiniMaxProvider("secret").list_cloned_voices())
        self.assertEqual([voice["provider_voice_id"] for voice in voices], ["vs_old", "vs_new"])
        self.assertEqual(voices[1]["display_name"], "我的声音")

    def test_native_websocket_stream_decodes_hex_audio_chunks(self):
        first = b"mini-one"
        second = b"mini-two"

        class FakeWebSocket:
            def __init__(self):
                self.sent = []
                self.responses = [
                    {"event": "task_started", "base_resp": {"status_code": 0}},
                    {"event": "task_continued", "data": {"audio": first.hex()}, "is_final": False, "base_resp": {"status_code": 0}},
                    {"event": "task_continued", "data": {"audio": second.hex()}, "is_final": True, "extra_info": {"audio_length": 2345}, "trace_id": "trace-native", "base_resp": {"status_code": 0}},
                    {"event": "task_finished", "trace_id": "trace-native", "base_resp": {"status_code": 0}},
                ]

            async def __aenter__(self):
                return self

            async def __aexit__(self, *_):
                return False

            async def send(self, message):
                self.sent.append(json.loads(message))

            async def recv(self):
                return json.dumps(self.responses.pop(0))

        websocket = FakeWebSocket()

        async def run():
            with patch("app.providers.minimax.websockets.connect", return_value=websocket):
                items = []
                async for item in MiniMaxProvider("secret").stream_synthesize(
                    SynthesisRequest("minimax/speech-2.8-turbo", "presenter_male", "你好", format="mp3")
                ):
                    items.append(item)
                return items

        items = asyncio.run(run())
        self.assertEqual(items[0]["audio"], first)
        self.assertEqual(items[1]["audio"], second)
        self.assertEqual(items[-1]["duration_ms"], 2345)
        self.assertEqual(websocket.sent[0]["event"], "task_start")
        self.assertEqual(websocket.sent[1], {"event": "task_continue", "text": "你好"})
        self.assertEqual(websocket.sent[2], {"event": "task_finish"})


if __name__ == "__main__":
    unittest.main()
