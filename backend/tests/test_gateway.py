import asyncio
import io
import os
import subprocess
import tempfile
import unittest
import zipfile
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

import httpx


@contextmanager
def isolated_storage(main):
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        with patch.object(main, "DATA", root / "data"), \
            patch.object(main, "AUDIO", root / "data" / "audio"), \
            patch.object(main, "DB_PATH", root / "data" / "voice_studio.db"), \
            patch.object(main, "GATEWAY_CONFIG_PATH", root / "data" / "gateway.json"):
            main.init_db()
            yield


class GatewayEndpointTests(unittest.TestCase):
    def test_volcengine_provider_uses_project_api_key_and_rejects_cross_project_fallback(self):
        from app import main
        from app.providers.volcengine import VolcengineProvider

        with isolated_storage(main):
            timestamp = main.now()
            with main.db() as connection:
                connection.execute(
                    "INSERT INTO provider_accounts VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    ("pa_volc", "volcengine", "火山", "default", None, None, "active", "••••base", "", "", timestamp, timestamp, timestamp),
                )
                connection.execute(
                    """INSERT INTO provider_projects
                       (id,provider_account_id,project_name,display_name,status,has_permission,source,created_at,updated_at,last_synced_at)
                       VALUES (?,?,?,?,?,?,?,?,?,?)""",
                    ("pp_astrbot", "pa_volc", "astrbot", "Astrbot", "active", 1, "remote", timestamp, timestamp, timestamp),
                )
            with patch.object(main, "load_api_key", return_value="default-key"), \
                patch.object(main, "load_provider_credentials", return_value={"openapi_access_key": "ak", "openapi_secret_key": "sk"}), \
                patch.object(main, "load_project_api_key", return_value="astrbot-key"):
                adapter = main.provider_for("volcengine", "pa_volc", "astrbot")
            self.assertIsInstance(adapter, VolcengineProvider)
            self.assertEqual(adapter.api_key, "astrbot-key")

            with patch.object(main, "load_api_key", return_value="default-key"), \
                patch.object(main, "load_provider_credentials", return_value={"openapi_access_key": "ak", "openapi_secret_key": "sk"}), \
                patch.object(main, "load_project_api_key", return_value=None):
                with self.assertRaisesRegex(Exception, "没有已同步的语音 API Key"):
                    main.provider_for("volcengine", "pa_volc", "astrbot")

    def test_volcengine_clone_requires_and_forwards_speaker_slot(self):
        from app import main
        from app.providers.volcengine import VolcengineProvider

        async def run():
            adapter = VolcengineProvider("test-key")
            with isolated_storage(main), patch.object(main, "provider_for", return_value=adapter), \
                patch.object(
                    adapter,
                    "clone_voice",
                    return_value={"voice_id": "S_assigned123", "request_id": "clone-log", "preview_url": None},
                ) as clone:
                with main.db() as connection:
                    timestamp = main.now()
                    connection.executemany(
                        "INSERT INTO provider_accounts VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                        [
                            ("pa_volc_default", "volcengine", "默认项目", "default", None, None, "active", "••••test", "remote_auth", "", timestamp, timestamp, timestamp),
                            ("pa_volc_astrbot", "volcengine", "Astrbot 项目", "astrbot", None, None, "configured", "••••test", "remote_auth", "", timestamp, timestamp, None),
                        ],
                    )
                transport = httpx.ASGITransport(app=main.app)
                async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                    query = {
                        "provider_name": "volcengine",
                        "model_id": "seed-icl-2.0",
                        "display_name": "测试音色",
                        "public_name": "volc-clone-test",
                    }
                    missing = await client.post(
                        "/api/voices/clone",
                        params=query,
                        files={"audio": ("sample.wav", b"voice-sample", "audio/wav")},
                    )
                    created = await client.post(
                        "/api/voices/clone",
                        params={
                            **query,
                            "speaker_id": " S_assigned123 ",
                            "provider_account_id": "pa_volc_astrbot",
                            "clone_language": 2,
                        },
                        files={"audio": ("sample.wav", b"voice-sample", "audio/wav")},
                    )
                    ambiguous = await client.post(
                        "/api/voices/clone",
                        params={**query, "public_name": "volc-clone-ambiguous", "speaker_id": "S_other"},
                        files={"audio": ("sample.wav", b"voice-sample", "audio/wav")},
                    )

            self.assertEqual(missing.status_code, 400)
            self.assertIn("S_", missing.json()["error"]["message"])
            self.assertEqual(created.status_code, 200)
            self.assertEqual(created.json()["voice"]["provider_voice_id"], "S_assigned123")
            self.assertEqual(created.json()["voice"]["provider_account_id"], "pa_volc_astrbot")
            self.assertEqual(created.json()["voice"]["provider_project_name"], "astrbot")
            self.assertEqual(created.json()["voice"]["languages"], ["ja-JP"])
            self.assertEqual(ambiguous.status_code, 409)
            self.assertEqual(ambiguous.json()["error"]["code"], "provider_account_required")
            clone.assert_awaited_once_with(b"voice-sample", "wav", "S_assigned123", 2)

        asyncio.run(run())

    def test_synthesis_reuses_the_account_bound_to_a_cloned_voice(self):
        with patch.dict(os.environ, {"VOICE_STUDIO_GATEWAY_KEY": "test_gateway_key"}, clear=False):
            from app import main

            async def run():
                with isolated_storage(main):
                    with main.db() as connection:
                        connection.execute(
                            """INSERT INTO voices
                               (id,provider,model_id,provider_voice_id,display_name,public_name,voice_type,status,languages,created_at,provider_account_id,provider_project_name)
                               VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                            (
                                "voice_bound",
                                "volcengine",
                                "seed-icl-2.0",
                                "S_bound",
                                "项目音色",
                                "project-voice",
                                "cloned",
                                "active",
                                '["zh-CN"]',
                                main.now(),
                                "pa_volc_astrbot",
                                "astrbot",
                            ),
                        )
                    transport = httpx.ASGITransport(app=main.app)
                    with patch.object(main, "provider_for", return_value=main.demo_provider) as provider_factory:
                        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                            response = await client.post(
                                "/v1/audio/speech",
                                headers={"Authorization": "Bearer test_gateway_key"},
                                json={
                                    "model": "volcengine/seed-icl-2.0",
                                    "voice": "project-voice",
                                    "input": "项目绑定测试",
                                    "response_format": "wav",
                                },
                            )
                self.assertEqual(response.status_code, 200)
                provider_factory.assert_called_once_with("volcengine", "pa_volc_astrbot", "astrbot")

            asyncio.run(run())

    def test_open_storage_directory_uses_platform_opener_or_returns_headless_path(self):
        from app import main

        with tempfile.TemporaryDirectory() as directory:
            audio = Path(directory) / "audio"
            with patch.object(main, "AUDIO", audio), patch.object(main.platform, "system", return_value="Linux"), patch.dict(os.environ, {"DISPLAY": "", "WAYLAND_DISPLAY": ""}, clear=True):
                result = main.open_storage_directory()
            self.assertFalse(result["opened"])
            self.assertEqual(result["path"], str(audio.resolve()))
            self.assertIn("没有图形桌面", result["message"])

            with patch.object(main, "AUDIO", audio), patch.object(main.platform, "system", return_value="Linux"), patch.dict(os.environ, {"DISPLAY": ":0"}, clear=False), patch.object(subprocess, "Popen") as popen:
                result = main.open_storage_directory()
            self.assertTrue(result["opened"])
            popen.assert_called_once()
            self.assertEqual(popen.call_args.args[0][0], "xdg-open")

    def test_docker_environment_credentials_create_read_only_account_metadata(self):
        from app import main
        from app.credentials import CredentialStoreError, load_api_key, save_api_key

        with patch.dict(
            os.environ,
            {
                "VOICE_STUDIO_CREDENTIALS_MODE": "env",
                "VOICE_STUDIO_MIMO_API_KEY": "mimo-docker-secret",
            },
            clear=False,
        ), isolated_storage(main):
            with main.db() as connection:
                row = connection.execute("SELECT * FROM provider_accounts WHERE id='env_mimo'").fetchone()
            self.assertIsNotNone(row)
            self.assertEqual(row["status"], "configured")
            self.assertEqual(load_api_key("env_mimo"), "mimo-docker-secret")
            with self.assertRaisesRegex(CredentialStoreError, "环境变量凭据"):
                save_api_key("env_mimo", "replacement")

    def test_system_diagnostics_report_required_components(self):
        from app import main

        async def run():
            with tempfile.TemporaryDirectory() as directory:
                frontend = Path(directory) / "dist"
                frontend.mkdir()
                (frontend / "index.html").write_text("ready", encoding="utf-8")
                command_result = {"id": "tool", "label": "tool", "status": "ok", "version": "1.0", "detail": "C:/tool.exe"}
                with isolated_storage(main), \
                    patch.object(main, "FRONTEND_DIST", frontend), \
                    patch.object(main, "_command_diagnostic", side_effect=lambda command, arguments, required: {**command_result, "id": command, "label": command}), \
                    patch.object(main, "credential_store_status", return_value={"available": True, "backend": "WinVaultKeyring", "message": "可用"}):
                    transport = httpx.ASGITransport(app=main.app)
                    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                        response = await client.get("/api/system/diagnostics")
                self.assertEqual(response.status_code, 200)
                payload = response.json()
                self.assertEqual(payload["status"], "ok")
                self.assertEqual(payload["demo"]["model"], "demo/local-demo")
                self.assertTrue(any(item["id"] == "credentials" for item in payload["checks"]))
                self.assertTrue(any(item["id"] == "data" and item["status"] == "ok" for item in payload["checks"]))

        asyncio.run(run())

    def test_local_demo_speech_needs_no_provider_credentials(self):
        with patch.dict(os.environ, {"VOICE_STUDIO_GATEWAY_KEY": "test_gateway_key"}, clear=False):
            from app import main

            async def run():
                transport = httpx.ASGITransport(app=main.app)
                async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                    response = await client.post(
                        "/v1/audio/speech",
                        headers={"Authorization": "Bearer test_gateway_key"},
                        json={"model": "demo/local-demo", "voice": "local-demo", "input": "本地演示测试", "response_format": "wav"},
                    )
                    self.assertEqual(response.status_code, 200)
                    self.assertEqual(response.headers["x-voice-studio-mode"], "demo")
                    self.assertTrue(response.content.startswith(b"RIFF"))
                    stats_response = await client.get("/api/gateway/stats?window=all")
                    self.assertEqual(stats_response.status_code, 200)
                    self.assertEqual(stats_response.json()["total_requests"], 0)

            with isolated_storage(main):
                asyncio.run(run())

    def test_public_catalog_hides_demo_and_custom_voice_can_be_renamed(self):
        from app import main

        async def run():
            transport = httpx.ASGITransport(app=main.app)
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                models_response = await client.get("/api/models")
                voices_response = await client.get("/api/voices")
                rename_response = await client.patch(
                    "/api/voices/voice_custom_rename",
                    json={"display_name": "新的显示名称"},
                )
                preset_response = await client.patch(
                    "/api/voices/voice_narrator",
                    json={"display_name": "不能修改"},
                )

            self.assertTrue(all(item["provider"] != "demo" for item in models_response.json()))
            self.assertTrue(all(item["provider"] != "demo" for item in voices_response.json()))
            self.assertEqual(rename_response.status_code, 200)
            renamed = rename_response.json()["voice"]
            self.assertEqual(renamed["display_name"], "新的显示名称")
            self.assertEqual(renamed["public_name"], "stable-api-id")
            self.assertEqual(preset_response.status_code, 409)

        with isolated_storage(main):
            with main.db() as connection:
                connection.execute(
                    "INSERT INTO voices (id,provider,model_id,provider_voice_id,display_name,public_name,voice_type,status,languages,created_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
                    ("voice_custom_rename", "minimax", "speech-2.8-turbo", "remote-id", "旧名称", "stable-api-id", "cloned", "active", '["zh-CN"]', main.now()),
                )
            asyncio.run(run())

    def test_local_security_guards_and_endpoint_allowlist(self):
        from app import main

        self.assertEqual(
            main.validate_provider_endpoint("minimax", "https://api.minimaxi.com/v1/"),
            "https://api.minimaxi.com/v1",
        )
        with self.assertRaises(ValueError):
            main.validate_provider_endpoint("minimax", "https://example.com/v1")
        with self.assertRaises(ValueError):
            main.validate_provider_endpoint("mimo", "http://api.xiaomimimo.com/v1")
        with patch.dict(os.environ, {"VOICE_STUDIO_ALLOW_CUSTOM_ENDPOINTS": "1"}, clear=False):
            self.assertEqual(
                main.validate_provider_endpoint("mimo", "https://trusted-proxy.example/v1"),
                "https://trusted-proxy.example/v1",
            )
            self.assertEqual(
                main.validate_provider_endpoint("mimo", "http://127.0.0.1:9000/v1"),
                "http://127.0.0.1:9000/v1",
            )
            with self.assertRaises(ValueError):
                main.validate_provider_endpoint("mimo", "http://trusted-proxy.example/v1")

        async def run():
            transport = httpx.ASGITransport(app=main.app)
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                bad_origin = await client.get("/api/summary", headers={"Origin": "https://malicious.example"})
                self.assertEqual(bad_origin.status_code, 403)
                self.assertEqual(bad_origin.json()["error"]["code"], "untrusted_origin")
            async with httpx.AsyncClient(transport=transport, base_url="http://malicious.example") as client:
                bad_host = await client.get("/api/summary")
                self.assertEqual(bad_host.status_code, 400)

        asyncio.run(run())

    def test_spa_route_cannot_escape_frontend_directory(self):
        from app import main

        async def run():
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                frontend = root / "frontend" / "dist"
                frontend.mkdir(parents=True)
                (frontend / "index.html").write_text("safe index", encoding="utf-8")
                secret = root / "data" / "gateway.json"
                secret.parent.mkdir(parents=True)
                secret.write_text("should-never-be-served", encoding="utf-8")
                with patch.object(main, "FRONTEND_DIST", frontend):
                    transport = httpx.ASGITransport(app=main.app)
                    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                        response = await client.get("/%2e%2e/%2e%2e/data/gateway.json")
                    self.assertNotIn(b"should-never-be-served", response.content)

        asyncio.run(run())

    def test_gateway_config_and_models_require_the_generated_key(self):
        with patch.dict(os.environ, {"VOICE_STUDIO_GATEWAY_KEY": "test_gateway_key"}, clear=False):
            from app import main

            async def run():
                transport = httpx.ASGITransport(app=main.app)
                async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                    summary = await client.get("/api/summary")
                    self.assertNotIn("key_prefix", summary.json().get("gateway", {}))
                    config = await client.get("/api/gateway")
                    self.assertEqual(config.status_code, 200)
                    self.assertEqual(config.json()["key"], "test_gateway_key")
                    denied = await client.get("/v1/models")
                    self.assertEqual(denied.status_code, 401)
                    self.assertEqual(denied.json()["error"]["code"], "gateway_auth_failed")
                    self.assertNotIn("detail", denied.json())
                    allowed = await client.get("/v1/models", headers={"Authorization": "Bearer test_gateway_key"})
                    self.assertEqual(allowed.status_code, 200)
                    self.assertTrue(any(item["id"] == "tts-default" for item in allowed.json()["data"]))
                    lower_case_scheme = await client.get("/v1/models", headers={"Authorization": "bearer test_gateway_key"})
                    self.assertEqual(lower_case_scheme.status_code, 200)

            with isolated_storage(main):
                asyncio.run(run())

    def test_speech_returns_binary_audio_with_gateway_metadata(self):
        with patch.dict(os.environ, {"VOICE_STUDIO_GATEWAY_KEY": "test_gateway_key"}, clear=False):
            from app import main

            async def run():
                transport = httpx.ASGITransport(app=main.app)
                async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                    with patch.object(main, "provider_for", return_value=main.demo_provider):
                        response = await client.post(
                            "/v1/audio/speech",
                            headers={"Authorization": "Bearer test_gateway_key"},
                            json={
                                "model": "mimo/mimo-v2.5-tts",
                                "voice": "mimo-default",
                                "input": "网关契约测试",
                                "response_format": "wav",
                            },
                        )
                    self.assertEqual(response.status_code, 200)
                    self.assertEqual(response.headers["content-type"], "audio/wav")
                    self.assertEqual(response.headers["x-voice-studio-response-format"], "wav")
                    self.assertTrue(response.headers.get("x-voice-studio-job", "").startswith("job_"))
                    self.assertTrue(response.content.startswith(b"RIFF"))

            with isolated_storage(main):
                asyncio.run(run())

    def test_gateway_stats_aggregate_completed_failed_and_latency_samples(self):
        with patch.dict(os.environ, {"VOICE_STUDIO_GATEWAY_KEY": "test_gateway_key"}, clear=False):
            from app import main

            async def run():
                transport = httpx.ASGITransport(app=main.app)
                async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                    headers = {"Authorization": "Bearer test_gateway_key"}
                    with patch.object(main, "provider_for", return_value=main.demo_provider):
                        completed = await client.post(
                            "/v1/audio/speech",
                            headers=headers,
                            json={
                                "model": "mimo/mimo-v2.5-tts",
                                "voice": "mimo-default",
                                "input": "统计成功样本",
                                "response_format": "wav",
                            },
                        )
                    self.assertEqual(completed.status_code, 200)
                    failed = await client.post(
                        "/v1/audio/speech",
                        headers=headers,
                        json={
                            "model": "mimo/mimo-v2.5-tts",
                            "voice": "mimo-default",
                            "input": "统计失败样本",
                            "response_format": "ogg",
                        },
                    )
                    self.assertEqual(failed.status_code, 400)
                    stats = await client.get("/api/gateway/stats?window=all")
                    self.assertEqual(stats.status_code, 200)
                    payload = stats.json()
                    self.assertEqual(payload["total_requests"], 2)
                    self.assertEqual(payload["completed_requests"], 1)
                    self.assertEqual(payload["failed_requests"], 1)
                    self.assertEqual(payload["success_rate"], 50.0)
                    self.assertEqual(payload["total_latency"]["samples"], 2)
                    self.assertEqual(payload["first_chunk_latency"]["samples"], 0)
                    self.assertEqual(payload["errors"][0]["code"], "invalid_response_format")
                    self.assertEqual(payload["by_provider"][0]["name"], "mimo")
                    self.assertEqual(payload["by_model"][0]["name"], "mimo/mimo-v2.5-tts")

            with isolated_storage(main):
                asyncio.run(run())

    def test_model_detail_and_validation_use_openai_error_shape(self):
        with patch.dict(os.environ, {"VOICE_STUDIO_GATEWAY_KEY": "test_gateway_key"}, clear=False):
            from app import main

            async def run():
                transport = httpx.ASGITransport(app=main.app)
                async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                    headers = {"Authorization": "Bearer test_gateway_key"}
                    detail = await client.get("/v1/models/tts-default", headers=headers)
                    self.assertEqual(detail.status_code, 200)
                    self.assertEqual(detail.json()["id"], "tts-default")
                    self.assertEqual(detail.json()["owned_by"], "mimo")
                    self.assertTrue(detail.json()["voice_studio"]["native_streaming"])
                    self.assertEqual(detail.json()["voice_studio"]["native_stream_formats"], ["pcm"])

                    missing = await client.get("/v1/models/does-not-exist", headers=headers)
                    self.assertEqual(missing.status_code, 404)
                    self.assertEqual(missing.json()["error"]["code"], "model_not_found")

                    invalid = await client.post(
                        "/v1/audio/speech",
                        headers=headers,
                        json={"model": "tts-default", "voice": "alloy"},
                    )
                    self.assertEqual(invalid.status_code, 400)
                    self.assertEqual(invalid.json()["error"]["type"], "invalid_request_error")
                    self.assertNotIn("detail", invalid.json())

            with isolated_storage(main):
                asyncio.run(run())

    def test_speech_stream_returns_sse_audio_chunks_and_done_event(self):
        with patch.dict(os.environ, {"VOICE_STUDIO_GATEWAY_KEY": "test_gateway_key"}, clear=False):
            from app import main

            async def run():
                transport = httpx.ASGITransport(app=main.app)
                async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                    with patch.object(main, "provider_for", return_value=main.demo_provider):
                        response = await client.post(
                            "/v1/audio/speech/stream",
                            headers={"Authorization": "Bearer test_gateway_key"},
                            json={
                                "model": "mimo/mimo-v2.5-tts",
                                "voice": "mimo-default",
                                "input": "流式网关契约测试",
                                "response_format": "wav",
                                "chunk_size": 1024,
                            },
                        )
                    self.assertEqual(response.status_code, 200)
                    self.assertEqual(response.headers["content-type"], "text/event-stream; charset=utf-8")
                    self.assertEqual(response.headers["x-voice-studio-stream"], "sse")
                    self.assertIn("event: audio", response.text)
                    self.assertIn('"type":"audio.chunk"', response.text)
                    self.assertIn("event: done", response.text)
                    self.assertIn('"type":"audio.done"', response.text)
                    self.assertNotIn("event: error", response.text)

            with isolated_storage(main):
                asyncio.run(run())

    def test_speech_stream_rejects_unknown_format_with_openai_error_shape(self):
        with patch.dict(os.environ, {"VOICE_STUDIO_GATEWAY_KEY": "test_gateway_key"}, clear=False):
            from app import main

            async def run():
                transport = httpx.ASGITransport(app=main.app)
                async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                    response = await client.post(
                        "/v1/audio/speech/stream",
                        headers={"Authorization": "Bearer test_gateway_key"},
                        json={
                            "model": "tts-default",
                            "voice": "alloy",
                            "input": "invalid",
                            "response_format": "ogg",
                        },
                    )
                    self.assertEqual(response.status_code, 400)
                    self.assertEqual(response.json()["error"]["code"], "invalid_response_format")

            with isolated_storage(main):
                asyncio.run(run())

    def test_speech_stream_uses_native_provider_chunks_for_mp3(self):
        with patch.dict(os.environ, {"VOICE_STUDIO_GATEWAY_KEY": "test_gateway_key"}, clear=False):
            from app import main

            class NativeProvider:
                async def stream_synthesize(self, request):
                    yield {"audio": b"native-one"}
                    yield {"audio": b"native-two"}
                    yield {"done": True, "provider_request_id": "native-test"}

                async def synthesize(self, request, output):
                    raise AssertionError("native stream should be selected")

            async def run():
                transport = httpx.ASGITransport(app=main.app)
                async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                    with patch.object(main, "provider_for", return_value=NativeProvider()):
                        response = await client.post(
                            "/v1/audio/speech/stream",
                            headers={"Authorization": "Bearer test_gateway_key"},
                            json={
                                "model": "volcengine/seed-tts-2.0",
                                "voice": "volc-vivi",
                                "input": "原生流式测试",
                                "response_format": "mp3",
                                "chunk_size": 1024,
                            },
                        )
                    self.assertEqual(response.status_code, 200)
                    self.assertIn('"native":true', response.text)
                    self.assertIn('"first_chunk_latency_ms":', response.text)
                    self.assertIn('"provider_request_id":"native-test"', response.text)
                    self.assertNotIn("event: error", response.text)

            with isolated_storage(main):
                asyncio.run(run())

    def test_speech_stream_uses_native_pcm_provider_chunks(self):
        with patch.dict(os.environ, {"VOICE_STUDIO_GATEWAY_KEY": "test_gateway_key"}, clear=False):
            from app import main

            class NativePcmProvider:
                def supports_native_streaming(self, model):
                    return model == "mimo/mimo-v2.5-tts"

                def native_stream_format(self, model):
                    return "pcm"

                async def stream_synthesize(self, request):
                    yield {"audio": b"\x00\x00\x01\x00"}
                    yield {"done": True, "provider_request_id": "mimo-native-test", "duration_ms": 1, "sample_rate": 24000, "channels": 1, "bit_depth": 16}

                async def synthesize(self, request, output):
                    raise AssertionError("native PCM stream should be selected")

            async def run():
                transport = httpx.ASGITransport(app=main.app)
                async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                    with patch.object(main, "provider_for", return_value=NativePcmProvider()):
                        response = await client.post(
                            "/v1/audio/speech/stream",
                            headers={"Authorization": "Bearer test_gateway_key"},
                            json={
                                "model": "mimo/mimo-v2.5-tts",
                                "voice": "mimo-default",
                                "input": "原生 PCM 流式测试",
                                "response_format": "pcm",
                                "chunk_size": 1024,
                            },
                        )
                self.assertEqual(response.status_code, 200)
                self.assertIn('"format":"pcm"', response.text)
                self.assertIn('"native":true', response.text)
                self.assertIn('"native_streaming":true', response.text)
                self.assertIn('"sample_rate":24000', response.text)
                self.assertNotIn("event: error", response.text)

            with isolated_storage(main):
                asyncio.run(run())

    def test_speech_stream_cancellation_closes_provider_and_removes_partial_audio(self):
        from app import main

        class CancellableProvider:
            def __init__(self):
                self.closed = False

            async def stream_synthesize(self, request):
                try:
                    yield {"audio": b"partial-mp3"}
                    await asyncio.Future()
                finally:
                    self.closed = True

        async def run():
            provider = CancellableProvider()
            model = main.resolve_model("volcengine/seed-tts-2.0")
            voice = main.resolve_voice("volc-vivi", model)
            body = main.StreamingSynthesisBody(
                model=model.gateway_id,
                voice="volc-vivi",
                input="取消流式测试",
                response_format="mp3",
                chunk_size=1024,
            )
            events = main._stream_speech_events(
                body,
                model,
                voice,
                provider,
                "job_cancel_test",
                "mp3",
            )
            first_event = await anext(events)
            self.assertIn("event: audio", first_event)
            partial_path = main.AUDIO / "job_cancel_test.mp3"
            self.assertTrue(partial_path.is_file())

            pending = asyncio.create_task(anext(events))
            await asyncio.sleep(0)
            pending.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await pending

            self.assertTrue(provider.closed)
            self.assertFalse(partial_path.exists())
            with main.db() as connection:
                jobs = connection.execute(
                    "SELECT COUNT(*) FROM jobs WHERE id=?", ("job_cancel_test",)
                ).fetchone()[0]
            self.assertEqual(jobs, 0)

        with isolated_storage(main):
            asyncio.run(run())

    def test_job_history_preserves_text_filters_by_day_and_downloads_assets(self):
        with patch.dict(os.environ, {"VOICE_STUDIO_GATEWAY_KEY": "test_gateway_key"}, clear=False):
            from app import main

            async def run():
                transport = httpx.ASGITransport(app=main.app)
                async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                    with patch.object(main, "provider_for", return_value=main.demo_provider):
                        created = await client.post(
                            "/v1/audio/speech",
                            headers={"Authorization": "Bearer test_gateway_key"},
                            json={
                                "model": "mimo/mimo-v2.5-tts",
                                "voice": "mimo-default",
                                "input": "需要完整保留的任务文字",
                                "response_format": "wav",
                            },
                        )
                    self.assertEqual(created.status_code, 200)
                    job_id = created.headers["x-voice-studio-job"]

                    history = await client.get("/api/jobs")
                    self.assertEqual(history.status_code, 200)
                    job = next(item for item in history.json() if item["id"] == job_id)
                    self.assertEqual(job["input_text"], "需要完整保留的任务文字")
                    self.assertTrue(job["audio_available"])
                    self.assertEqual(job["audio_url"], f"/api/jobs/{job_id}/audio")
                    self.assertEqual(job["text_url"], f"/api/jobs/{job_id}/text")

                    filtered = await client.get("/api/jobs", params={"date": job["created_date"]})
                    self.assertEqual(filtered.status_code, 200)
                    self.assertEqual([item["id"] for item in filtered.json()], [job_id])
                    invalid_date = await client.get("/api/jobs", params={"date": "2026/08/18"})
                    self.assertEqual(invalid_date.status_code, 400)

                    audio = await client.get(job["audio_url"])
                    self.assertEqual(audio.status_code, 200)
                    self.assertTrue(audio.content.startswith(b"RIFF"))
                    self.assertIn("attachment", audio.headers["content-disposition"])
                    text = await client.get(job["text_url"])
                    self.assertEqual(text.status_code, 200)
                    self.assertEqual(text.text, "需要完整保留的任务文字")
                    self.assertIn("attachment", text.headers["content-disposition"])

                    storage = await client.get("/api/jobs/storage")
                    self.assertEqual(storage.status_code, 200)
                    self.assertEqual(storage.json()["audio_count"], 1)
                    archive = await client.post("/api/jobs/export", json={"job_ids": [job_id]})
                    self.assertEqual(archive.status_code, 200)
                    self.assertEqual(archive.headers["content-type"], "application/zip")
                    with zipfile.ZipFile(io.BytesIO(archive.content)) as bundle:
                        self.assertIn("manifest.json", bundle.namelist())
                        self.assertIn(f"text/{job_id}.txt", bundle.namelist())
                        self.assertIn(f"audio/{job_id}.wav", bundle.namelist())
                        self.assertEqual(bundle.read(f"text/{job_id}.txt").decode(), "需要完整保留的任务文字")
                    date_archive = await client.post("/api/jobs/export", json={"date": job["created_date"]})
                    self.assertEqual(date_archive.status_code, 200)

                    deleted = await client.post("/api/jobs/delete", json={"job_ids": [job_id]})
                    self.assertEqual(deleted.status_code, 200)
                    self.assertEqual(deleted.json()["deleted"], 1)
                    self.assertEqual((await client.get(f"/api/jobs/{job_id}/audio")).status_code, 404)
                    with main.db() as connection:
                        self.assertIsNone(connection.execute("SELECT 1 FROM jobs WHERE id=?", (job_id,)).fetchone())

            with isolated_storage(main):
                asyncio.run(run())

    def test_mimo_voice_design_creates_reusable_local_template_and_preview(self):
        with patch.dict(os.environ, {"VOICE_STUDIO_GATEWAY_KEY": "test_gateway_key"}, clear=False):
            from app import main

            async def run():
                transport = httpx.ASGITransport(app=main.app)
                adapter = main.MiMoProvider("test_key")

                async def fake_synthesize(request, output):
                    return await main.demo_provider.synthesize(request, output)

                with patch.object(main, "provider_for", return_value=adapter), patch.object(adapter, "synthesize", side_effect=fake_synthesize):
                    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                        response = await client.post(
                            "/api/voices/design",
                            json={
                                "provider": "mimo",
                                "model_id": "mimo-v2.5-tts-voicedesign",
                                "prompt": "成熟而温柔的女性，声音低沉、清晰，语速自然",
                                "preview_text": "这是一个设计音色试听。",
                                "display_name": "设计女声",
                                "public_name": "design-mimo-test",
                            },
                        )
                        self.assertEqual(response.status_code, 200)
                        voice = response.json()["voice"]
                        self.assertEqual(voice["voice_type"], "design")
                        self.assertEqual(voice["design_prompt"], "成熟而温柔的女性，声音低沉、清晰，语速自然")
                        self.assertTrue(voice["preview_url"])
                        preview = await client.get(voice["preview_url"])
                        self.assertEqual(preview.status_code, 200)
                        self.assertTrue(preview.content.startswith(b"RIFF"))

            with isolated_storage(main):
                asyncio.run(run())


if __name__ == "__main__":
    unittest.main()
