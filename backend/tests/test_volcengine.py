import asyncio
import base64
import json
import unittest
from unittest.mock import AsyncMock, patch

import httpx

from app.providers.volcengine import VOLCENGINE_MODELS, VolcengineProvider
from app.providers.base import SynthesisRequest


class VolcengineVoiceListTests(unittest.TestCase):
    def test_voice_design_is_not_advertised(self):
        seed_tts = next(model for model in VOLCENGINE_MODELS if model.model_id == "seed-tts-2.0")
        self.assertEqual(seed_tts.operations, ["synthesis"])

    def test_lists_success_and_active_statuses(self):
        responses = [
            httpx.Response(200, json={
                "Result": {
                    "Statuses": [
                        {"SpeakerID": "S_success", "State": "Success", "Alias": "我的声音", "CreateTime": 1700000000000},
                        {"SpeakerID": "S_training", "State": "Training"},
                    ],
                    "NextToken": "next",
                }
            }),
            httpx.Response(200, json={"Result": {"Statuses": [{"SpeakerID": "S_active", "State": "Active", "Alias": "备用"}]}}),
            httpx.Response(200, json={"Result": {"Statuses": []}}),
            httpx.Response(200, json={"Result": {"Statuses": []}}),
        ]

        async def request(*args, **kwargs):
            return responses.pop(0)

        provider = VolcengineProvider("tts-key", openapi_access_key="access-key", openapi_secret_key="secret-key", project_name="default")
        with patch("httpx.AsyncClient.post", new=AsyncMock(side_effect=request)):
            voices = asyncio.run(provider.list_cloned_voices())
        self.assertEqual([item["provider_voice_id"] for item in voices], ["S_success", "S_active"])
        self.assertEqual(voices[0]["display_name"], "我的声音")

    def test_native_stream_yields_decoded_audio_chunks(self):
        first = b"mp3-part-one"
        second = b"mp3-part-two"

        async def handler(request):
            self.assertEqual(request.url.path, "/api/v3/tts/unidirectional")
            return httpx.Response(
                200,
                headers={"X-Tt-Logid": "log-native"},
                content=(
                    json.dumps({"code": 0, "data": base64.b64encode(first).decode("ascii")}) + "\n"
                    + json.dumps({"code": 0, "data": base64.b64encode(second).decode("ascii")}) + "\n"
                ).encode(),
            )

        async def run():
            transport = httpx.MockTransport(handler)
            real_client = httpx.AsyncClient
            with patch(
                "app.providers.volcengine.httpx.AsyncClient",
                side_effect=lambda **kwargs: real_client(transport=transport, **kwargs),
            ):
                provider = VolcengineProvider("tts-key")
                items = []
                async for item in provider.stream_synthesize(
                    SynthesisRequest("volcengine/seed-tts-2.0", "speaker", "hello", format="mp3")
                ):
                    items.append(item)
                return items

        items = asyncio.run(run())
        self.assertEqual(items[0]["audio"], first)
        self.assertEqual(items[1]["audio"], second)
        self.assertEqual(items[-1]["provider_request_id"], "log-native")


if __name__ == "__main__":
    unittest.main()
