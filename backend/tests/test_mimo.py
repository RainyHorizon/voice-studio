import asyncio
import base64
import json
import unittest
from unittest.mock import patch

import httpx

from app.providers.base import SynthesisRequest
from app.providers.mimo import MiMoProvider


class MiMoStreamingTests(unittest.TestCase):
    def test_native_stream_decodes_delta_audio_and_requests_pcm16(self):
        first = b"\x01\x00\x02\x00"
        second = b"\x03\x00\x04\x00"
        seen = {}

        async def handler(request: httpx.Request) -> httpx.Response:
            seen.update(json.loads(request.content))
            self.assertEqual(request.url.path, "/v1/chat/completions")
            body = b"".join(
                (
                    f"data: {json.dumps({'id': 'mimo-stream-1', 'choices': [{'delta': {'audio': {'data': base64.b64encode(part).decode('ascii')}}}]})}\n\n"
                ).encode()
                for part in (first, second)
            ) + b"data: [DONE]\n\n"
            return httpx.Response(200, headers={"content-type": "text/event-stream"}, content=body)

        async def run():
            transport = httpx.MockTransport(handler)
            real_client = httpx.AsyncClient
            with patch(
                "app.providers.mimo.httpx.AsyncClient",
                side_effect=lambda **kwargs: real_client(transport=transport, **kwargs),
            ):
                items = []
                async for item in MiMoProvider("secret").stream_synthesize(
                    SynthesisRequest("mimo/mimo-v2.5-tts", "mimo_default", "你好", format="pcm")
                ):
                    items.append(item)
                return items

        items = asyncio.run(run())
        self.assertEqual([item["audio"] for item in items[:-1]], [first, second])
        self.assertEqual(items[-1]["provider_request_id"], "mimo-stream-1")
        self.assertEqual(items[-1]["sample_rate"], 24000)
        self.assertTrue(seen["stream"])
        self.assertEqual(seen["audio"]["format"], "pcm16")
        self.assertEqual(seen["messages"][1]["role"], "assistant")

    def test_all_current_models_advertise_pcm_native_streaming(self):
        provider = MiMoProvider("secret")
        for model in provider.models():
            if model.model_id == "mimo-v2.5-tts-voicedesign":
                self.assertFalse(provider.supports_native_streaming(model.gateway_id))
                continue
            self.assertTrue(provider.supports_native_streaming(model.gateway_id))
            self.assertEqual(provider.native_stream_format(model.gateway_id), "pcm")


if __name__ == "__main__":
    unittest.main()
