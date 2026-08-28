import asyncio
import base64
import json
import unittest
from unittest.mock import AsyncMock, patch

import httpx

from app.providers.volcengine import VOLCENGINE_MODELS, VolcengineProvider
from app.providers.base import SynthesisRequest


class VolcengineVoiceListTests(unittest.TestCase):
    def test_lists_available_api_keys_for_project(self):
        async def handler(request):
            self.assertEqual(request.url.params["Action"], "ListAPIKeys")
            self.assertEqual(request.url.params["Version"], "2025-05-20")
            self.assertEqual(json.loads(request.content), {"ProjectName": "astrbot", "OnlyAvailable": True})
            self.assertIn("/speech_saas_prod/request", request.headers["Authorization"])
            return httpx.Response(200, json={"Result": {"APIKeys": [{"ID": 3, "Name": "astrbot-key", "APIKey": "project-secret", "Disable": False}]}})

        async def run():
            transport = httpx.MockTransport(handler)
            real_client = httpx.AsyncClient
            with patch(
                "app.providers.volcengine.httpx.AsyncClient",
                side_effect=lambda **kwargs: real_client(transport=transport, **kwargs),
            ):
                provider = VolcengineProvider("tts-key", openapi_access_key="access-key", openapi_secret_key="secret-key")
                return await provider.list_api_keys("astrbot")

        keys = asyncio.run(run())
        self.assertEqual(keys[0]["APIKey"], "project-secret")

    def test_lists_iam_projects_with_standard_action_query_and_iam_scope(self):
        async def handler(request):
            self.assertEqual(request.method, "POST")
            self.assertEqual(request.url.path, "/")
            self.assertEqual(request.url.params["Action"], "ListProjects")
            self.assertEqual(request.url.params["Version"], "2021-08-01")
            self.assertIn("/iam/request", request.headers["Authorization"])
            payload = json.loads(request.content)
            self.assertEqual(payload["Limit"], 100)
            return httpx.Response(200, json={"Result": {"Projects": [{"ProjectName": "default", "DisplayName": "默认项目"}], "Total": 1}})

        async def run():
            transport = httpx.MockTransport(handler)
            real_client = httpx.AsyncClient
            with patch(
                "app.providers.volcengine.httpx.AsyncClient",
                side_effect=lambda **kwargs: real_client(transport=transport, **kwargs),
            ):
                provider = VolcengineProvider("tts-key", openapi_access_key="access-key", openapi_secret_key="secret-key")
                return await provider.list_projects()

        projects = asyncio.run(run())
        self.assertEqual(projects[0]["ProjectName"], "default")

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

    def test_lists_only_available_empty_slots_for_project(self):
        response = httpx.Response(200, json={
            "Result": {
                "Statuses": [
                    {"SpeakerID": "S_ready", "State": "Unknown", "AvailableTrainingTimes": 3, "Alias": "空槽位"},
                    {"SpeakerID": "S_exhausted", "State": "Unknown", "AvailableTrainingTimes": 0},
                    {"SpeakerID": "S_expired", "State": "Unknown", "AvailableTrainingTimes": 1, "ExpireTime": 1},
                    {"SpeakerID": "S_trained", "State": "Success", "AvailableTrainingTimes": 1},
                ]
            }
        })
        request = AsyncMock(return_value=response)
        provider = VolcengineProvider(
            "tts-key",
            openapi_access_key="access-key",
            openapi_secret_key="secret-key",
            project_name="astrbot",
        )
        with patch("httpx.AsyncClient.post", new=request):
            slots = asyncio.run(provider.list_empty_voice_slots())

        self.assertEqual([item["speaker_id"] for item in slots], ["S_ready"])
        self.assertEqual(slots[0]["available_training_times"], 3)
        sent = json.loads(request.await_args.kwargs["content"])
        self.assertEqual(sent["ProjectName"], "astrbot")
        self.assertEqual(sent["State"], "Unknown")

    def test_clone_uses_v3_payload_without_legacy_model_types(self):
        async def handler(request):
            self.assertEqual(request.url.path, "/api/v3/tts/voice_clone")
            self.assertNotIn("X-Api-Resource-Id", request.headers)
            payload = json.loads(request.content)
            self.assertEqual(payload["speaker_id"], "S_assigned123")
            self.assertNotIn("model_types", payload)
            self.assertNotIn("model_type", payload)
            self.assertEqual(payload["language"], 2)
            self.assertEqual(base64.b64decode(payload["audio"]["data"]), b"voice-sample")
            return httpx.Response(
                200,
                headers={"X-Tt-Logid": "clone-log"},
                json={
                    "speaker_id": "S_assigned123",
                    "status": 2,
                    "speaker_status": [{"model_type": 4, "demo_audio": "https://example.test/demo.mp3"}],
                },
            )

        async def run():
            transport = httpx.MockTransport(handler)
            real_client = httpx.AsyncClient
            with patch(
                "app.providers.volcengine.httpx.AsyncClient",
                side_effect=lambda **kwargs: real_client(transport=transport, **kwargs),
            ):
                return await VolcengineProvider("tts-key").clone_voice(
                    b"voice-sample", "wav", "S_assigned123", 2
                )

        result = asyncio.run(run())
        self.assertEqual(result["voice_id"], "S_assigned123")
        self.assertEqual(result["request_id"], "clone-log")
        self.assertEqual(result["preview_url"], "https://example.test/demo.mp3")

    def test_clone_maps_no_speaker_error_to_audio_guidance(self):
        response = httpx.Response(400, json={"code": 45001122, "message": "no speaker detected"})
        request = AsyncMock(return_value=response)
        with patch("httpx.AsyncClient.post", new=request):
            with self.assertRaisesRegex(Exception, "14–30 秒"):
                asyncio.run(VolcengineProvider("tts-key").clone_voice(b"sample", "wav", "S_slot"))

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
