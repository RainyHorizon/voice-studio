from __future__ import annotations

import base64
import binascii
import asyncio
import datetime as dt
import hashlib
import hmac
import json
import subprocess
from urllib.parse import quote
import uuid
from pathlib import Path
from typing import AsyncIterator

import httpx

from .base import ProviderError, ProviderModel, SpeechProvider, SynthesisRequest


DEFAULT_ENDPOINT = "https://openspeech.bytedance.com"
SYNTHESIS_PATH = "/api/v3/tts/unidirectional"
CLONE_PATH = "/api/v3/tts/voice_clone"
VOICE_STATUS_PATH = "/api/v3/tts/get_voice"
OPENAPI_ENDPOINT = "https://open.volcengineapi.com"
OPENAPI_SERVICE = "speech_saas_prod"
OPENAPI_REGION = "cn-beijing"
OPENAPI_VERSION = "2025-05-21"

VOLCENGINE_MODELS = [
    ProviderModel(
        "volcengine",
        "seed-tts-2.0",
        "Seed TTS 2.0",
        "tts",
        "细腻",
        "快",
        ["zh-CN", "en-US", "ja-JP", "es-ES"],
        False,
        "provider",
        ["synthesis"],
    ),
    ProviderModel(
        "volcengine",
        "seed-icl-2.0",
        "Seed 声音复刻 2.0",
        "voice_clone",
        "复刻",
        "中",
        ["zh-CN", "en-US", "ja-JP", "es-ES"],
        True,
        "provider",
        ["synthesis", "clone"],
    ),
]


def _is_voice_clone_2(status: dict) -> bool:
    """火山线上既返回 model_version=2/model_type=4，也有文档中的 model_type=5。"""
    return status.get("model_version") == 2 or status.get("model_type") == 5


def _remote_error(response: httpx.Response, fallback: str) -> str:
    try:
        body = response.json()
        metadata_error = (body.get("ResponseMetadata") or {}).get("Error") or {}
        result_error = (body.get("Result") or {}).get("Error") or {}
        nested_error = body.get("error") or {}
        message = (
            body.get("message")
            or body.get("Message")
            or nested_error.get("message")
            or nested_error.get("Message")
            or metadata_error.get("Message")
            or metadata_error.get("message")
            or result_error.get("Message")
            or result_error.get("message")
        )
        code = (
            body.get("code")
            or body.get("Code")
            or nested_error.get("code")
            or nested_error.get("Code")
            or metadata_error.get("Code")
            or metadata_error.get("code")
            or result_error.get("Code")
            or result_error.get("code")
        )
        if message:
            suffix = f"（{code}）" if code not in {None, 0} else ""
            return f"{fallback}：{str(message)[:220]}{suffix}"
    except (TypeError, ValueError):
        pass
    raw = (response.text or "").strip().replace("\n", " ")
    return f"{fallback}：{raw[:220]}（HTTP {response.status_code}）" if raw else f"{fallback}（HTTP {response.status_code}）"


def _speed_value(speed: float) -> int:
    if speed >= 1:
        return round(min(2.0, speed) * 100 - 100)
    return round(max(0.5, speed) * 100 - 100)


def _write_audio(audio: bytes, output: Path) -> int:
    if not audio:
        raise ProviderError("火山引擎没有返回音频数据", code="invalid_provider_response")
    output.parent.mkdir(parents=True, exist_ok=True)
    source = output.with_name(output.stem + ".source.mp3")
    source.write_bytes(audio)
    try:
        converted = subprocess.run(
            ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(source), "-acodec", "pcm_s16le", str(output)],
            capture_output=True,
            text=True,
            timeout=120,
        )
        if converted.returncode != 0:
            raise ValueError("ffmpeg failed")
        probe = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json", str(output)],
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
        raise ProviderError("火山引擎返回的内容不是有效音频", code="invalid_audio_response") from exc
    finally:
        source.unlink(missing_ok=True)


class VolcengineProvider(SpeechProvider):
    key = "volcengine"

    def __init__(self, api_key: str, endpoint: str = DEFAULT_ENDPOINT, openapi_access_key: str | None = None,
                 openapi_secret_key: str | None = None, project_name: str | None = None):
        self.api_key = api_key
        self.endpoint = endpoint.rstrip("/")
        self.openapi_access_key = openapi_access_key or ""
        self.openapi_secret_key = openapi_secret_key or ""
        self.project_name = project_name or ""

    def models(self) -> list[ProviderModel]:
        return VOLCENGINE_MODELS

    def _headers(self, resource_id: str | None = None) -> dict[str, str]:
        headers = {
            "Content-Type": "application/json",
            "X-Api-Key": self.api_key,
            "X-Api-Request-Id": str(uuid.uuid4()),
        }
        if resource_id:
            headers["X-Api-Resource-Id"] = resource_id
        return headers

    def _request_params(self, request: SynthesisRequest) -> tuple[str, dict[str, object]]:
        model_id = request.model.split("/", 1)[-1]
        if model_id not in {"seed-tts-2.0", "seed-icl-2.0"}:
            raise ProviderError("当前火山引擎模型不受支持", code="unsupported_provider_model", status=400)
        req_params: dict[str, object] = {
            "text": request.text,
            "speaker": request.voice,
            "audio_params": {
                "format": "mp3",
                "sample_rate": 24000,
                "speech_rate": _speed_value(request.speed),
            },
        }
        if model_id == "seed-icl-2.0":
            req_params["model"] = "seed-tts-2.0-standard"
        elif request.instructions:
            req_params["context_texts"] = [request.instructions]
        return model_id, req_params

    def supports_native_streaming(self, model: str) -> bool:
        return model.split("/", 1)[-1] in {"seed-tts-2.0", "seed-icl-2.0"}

    async def stream_synthesize(self, request: SynthesisRequest) -> AsyncIterator[dict]:
        """Yield native MP3 chunks from Seed's chunked HTTP response."""
        if not self.api_key:
            raise ProviderError("尚未配置火山引擎 API Key", code="provider_not_configured", status=409)
        model_id, req_params = self._request_params(request)
        try:
            async with httpx.AsyncClient(timeout=180) as client:
                async with client.stream(
                    "POST",
                    self.endpoint + SYNTHESIS_PATH,
                    headers=self._headers(model_id),
                    json={"req_params": req_params},
                ) as response:
                    if response.status_code != 200:
                        await response.aread()
                        status = 401 if response.status_code in {401, 403} else 502
                        raise ProviderError(_remote_error(response, "火山引擎语音合成失败"), code="volcengine_synthesis_failed", status=status)
                    request_id = response.headers.get("X-Tt-Logid", "")
                    emitted = False
                    async for line in response.aiter_lines():
                        if not line.strip():
                            continue
                        try:
                            item = json.loads(line)
                        except ValueError as exc:
                            raise ProviderError("火山引擎返回了无法解析的数据", code="invalid_provider_response") from exc
                        if item.get("code") not in {None, 0, 20000000}:
                            raise ProviderError(
                                f"火山引擎语音合成失败：{str(item.get('message') or item.get('code'))[:240]}",
                                code="volcengine_synthesis_failed",
                            )
                        if item.get("data"):
                            try:
                                audio = base64.b64decode(item["data"], validate=True)
                            except (ValueError, binascii.Error) as exc:
                                raise ProviderError("火山引擎返回的音频数据无效", code="invalid_provider_response") from exc
                            if audio:
                                emitted = True
                                yield {"audio": audio}
                    if not emitted:
                        raise ProviderError("火山引擎没有返回音频数据", code="invalid_provider_response")
                    yield {"done": True, "provider_request_id": request_id}
        except ProviderError:
            raise
        except httpx.HTTPError as exc:
            raise ProviderError("无法连接火山引擎语音接口", code="provider_unreachable") from exc

    async def synthesize(self, request: SynthesisRequest, output: Path) -> dict:
        if not self.api_key:
            raise ProviderError("尚未配置火山引擎 API Key", code="provider_not_configured", status=409)

        model_id, req_params = self._request_params(request)

        try:
            async with httpx.AsyncClient(timeout=180) as client:
                async with client.stream(
                    "POST",
                    self.endpoint + SYNTHESIS_PATH,
                    headers=self._headers(model_id),
                    json={"req_params": req_params},
                ) as response:
                    if response.status_code != 200:
                        await response.aread()
                        status = 401 if response.status_code in {401, 403} else 502
                        raise ProviderError(_remote_error(response, "火山引擎语音合成失败"), code="volcengine_synthesis_failed", status=status)
                    request_id = response.headers.get("X-Tt-Logid", "")
                    chunks: list[bytes] = []
                    async for line in response.aiter_lines():
                        if not line.strip():
                            continue
                        try:
                            item = json.loads(line)
                        except ValueError as exc:
                            raise ProviderError("火山引擎返回了无法解析的数据", code="invalid_provider_response") from exc
                        if item.get("code") not in {None, 0, 20000000}:
                            raise ProviderError(
                                f"火山引擎语音合成失败：{str(item.get('message') or item.get('code'))[:240]}",
                                code="volcengine_synthesis_failed",
                            )
                        if item.get("data"):
                            try:
                                chunks.append(base64.b64decode(item["data"], validate=True))
                            except (ValueError, binascii.Error) as exc:
                                raise ProviderError("火山引擎返回的音频数据无效", code="invalid_provider_response") from exc
        except ProviderError:
            raise
        except httpx.HTTPError as exc:
            raise ProviderError("无法连接火山引擎语音接口", code="provider_unreachable") from exc

        duration_ms = _write_audio(b"".join(chunks), output)
        return {"provider_request_id": request_id, "duration_ms": duration_ms, "demo": False}

    async def clone_voice(self, audio: bytes, audio_format: str) -> dict:
        payload = {
            "speaker_id": "",
            "audio": {"data": base64.b64encode(audio).decode("ascii"), "format": audio_format},
            "language": 0,
            "extra_params": {"demo_text": "你好，这是我的声音复刻试听。"},
        }
        try:
            async with httpx.AsyncClient(timeout=240) as client:
                response = await client.post(self.endpoint + CLONE_PATH, headers=self._headers(), json=payload)
        except httpx.HTTPError as exc:
            raise ProviderError("无法连接火山引擎声音复刻接口", code="provider_unreachable") from exc
        if response.status_code != 200:
            status = 401 if response.status_code in {401, 403} else 502
            raise ProviderError(_remote_error(response, "火山引擎声音复刻失败"), code="volcengine_clone_failed", status=status)
        try:
            body = response.json()
            speaker_id = body["speaker_id"]
            clone_status = int(body["status"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ProviderError("火山引擎返回的复刻音色数据无效", code="invalid_provider_response") from exc
        for _ in range(20):
            if clone_status != 1:
                break
            await asyncio.sleep(3)
            body = await self._query_voice(speaker_id)
            try:
                clone_status = int(body["status"])
            except (KeyError, TypeError, ValueError) as exc:
                raise ProviderError("火山引擎返回的音色状态无效", code="invalid_provider_response") from exc
        if clone_status not in {2, 4}:
            messages = {0: "未找到音色", 1: "音色训练超时，请稍后从控制台导入该音色 ID", 3: "音色训练失败"}
            raise ProviderError(messages.get(clone_status, f"音色状态异常：{clone_status}"), code="volcengine_clone_not_ready", status=409)
        statuses = body.get("speaker_status") or []
        if statuses and not any(_is_voice_clone_2(item) for item in statuses):
            raise ProviderError("账号返回的音色不是声音复刻 2.0", code="invalid_provider_response")
        return {
            "voice_id": speaker_id,
            "request_id": response.headers.get("X-Tt-Logid", ""),
            "preview_url": next((item.get("demo_audio") for item in statuses if _is_voice_clone_2(item)), None),
        }

    async def _query_voice(self, speaker_id: str) -> dict:
        payload = {"speaker_id": speaker_id}
        if speaker_id.startswith("custom_"):
            payload = {"speaker_id": "custom_speaker_id", "custom_speaker_id": speaker_id}
        try:
            async with httpx.AsyncClient(timeout=60) as client:
                response = await client.post(
                    self.endpoint + VOICE_STATUS_PATH,
                    headers=self._headers(),
                    json=payload,
                )
        except httpx.HTTPError as exc:
            raise ProviderError("无法查询火山引擎音色状态", code="provider_unreachable") from exc
        if response.status_code != 200:
            raise ProviderError(_remote_error(response, "查询火山引擎音色状态失败"), code="volcengine_voice_query_failed")
        try:
            return response.json()
        except ValueError as exc:
            raise ProviderError("火山引擎返回的音色状态无效", code="invalid_provider_response") from exc

    async def validate_cloned_voice(self, speaker_id: str) -> dict:
        body = await self._query_voice(speaker_id)
        try:
            clone_status = int(body["status"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ProviderError("火山引擎返回的音色状态无效", code="invalid_provider_response") from exc
        if clone_status not in {2, 4}:
            messages = {0: "火山引擎未找到这个音色 ID", 1: "该音色仍在训练中", 3: "该音色训练失败"}
            raise ProviderError(messages.get(clone_status, f"音色状态异常：{clone_status}"), code="volcengine_voice_not_ready", status=409)
        statuses = body.get("speaker_status") or []
        if not any(_is_voice_clone_2(item) for item in statuses):
            raise ProviderError("该音色不是声音复刻 2.0，不能导入 Seed 声音复刻 2.0", code="invalid_voice_model", status=409)
        return body

    def _openapi_headers(self, query: dict[str, str], body: bytes) -> dict[str, str]:
        """Generate the Volcengine V4 signature used by the OpenAPI management APIs."""
        if not self.openapi_access_key or not self.openapi_secret_key:
            raise ProviderError("请先配置火山引擎 OpenAPI Access Key、Secret Access Key", code="volcengine_openapi_not_configured", status=409)
        now = dt.datetime.now(dt.timezone.utc)
        x_date = now.strftime("%Y%m%dT%H%M%SZ")
        short_date = now.strftime("%Y%m%d")
        canonical_query = "&".join(f"{quote(str(k), safe='-_.~')}={quote(str(v), safe='-_.~')}" for k, v in sorted(query.items()))
        payload_hash = hashlib.sha256(body).hexdigest()
        # Volcengine V4 requires every header listed in SignedHeaders to be
        # present in the canonical request. Content-Type is included for the
        # JSON management API; omitting it produces SignatureDoesNotMatch.
        content_type = "application/json; charset=UTF-8"
        canonical_headers = (
            "content-type:" + content_type + "\n"
            "host:open.volcengineapi.com\n"
            "x-content-sha256:" + payload_hash + "\n"
            "x-date:" + x_date + "\n"
        )
        signed_headers = "content-type;host;x-content-sha256;x-date"
        canonical_request = "POST\n/\n" + canonical_query + "\n" + canonical_headers + "\n" + signed_headers + "\n" + payload_hash
        scope = f"{short_date}/{OPENAPI_REGION}/{OPENAPI_SERVICE}/request"
        string_to_sign = "HMAC-SHA256\n" + x_date + "\n" + scope + "\n" + hashlib.sha256(canonical_request.encode()).hexdigest()
        def digest(key: bytes, value: str) -> bytes:
            return hmac.new(key, value.encode(), hashlib.sha256).digest()
        # Volcengine's HMAC-SHA256 V4 derivation differs from AWS SigV4:
        # start with the raw Secret Access Key (there is no ``AWS4`` prefix).
        k_date = digest(self.openapi_secret_key.encode(), short_date)
        k_region = digest(k_date, OPENAPI_REGION)
        k_service = digest(k_region, OPENAPI_SERVICE)
        signing_key = digest(k_service, "request")
        signature = hmac.new(signing_key, string_to_sign.encode(), hashlib.sha256).hexdigest()
        return {
            "Content-Type": content_type,
            "Host": "open.volcengineapi.com",
            "X-Date": x_date,
            "X-Content-Sha256": payload_hash,
            "Authorization": f"HMAC-SHA256 Credential={self.openapi_access_key}/{scope}, SignedHeaders={signed_headers}, Signature={signature}",
        }

    async def list_cloned_voices(self) -> list[dict]:
        if not self.project_name:
            raise ProviderError("请先配置火山引擎项目名称（ProjectName）", code="volcengine_project_not_configured", status=409)
        items: list[dict] = []
        for state in ("Success", "Active"):
            page = 1
            next_token = ""
            while page <= 100:
                query = {"Action": "BatchListMegaTTSTrainStatus", "Version": OPENAPI_VERSION}
                request_body: dict[str, object] = {"ProjectName": self.project_name, "State": state, "PageNumber": page, "PageSize": 100}
                if next_token:
                    request_body = {"ProjectName": self.project_name, "State": state, "NextToken": next_token, "MaxResults": 100}
                body_bytes = json.dumps(request_body, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
                try:
                    async with httpx.AsyncClient(timeout=45) as client:
                        response = await client.post(OPENAPI_ENDPOINT + "/", params=query, headers=self._openapi_headers(query, body_bytes), content=body_bytes)
                except httpx.HTTPError as exc:
                    raise ProviderError("无法连接火山引擎 OpenAPI，请检查网络和 AK/SK", code="provider_unreachable") from exc
                if response.status_code != 200:
                    raise ProviderError(_remote_error(response, "火山引擎云端音色列表查询失败"), code="volcengine_openapi_failed", status=401 if response.status_code in {401, 403} else 502)
                try:
                    body = response.json()
                except ValueError as exc:
                    raise ProviderError("火山引擎 OpenAPI 返回了无法解析的数据", code="invalid_provider_response") from exc
                if body.get("ResponseMetadata", {}).get("Error") or body.get("Result", {}).get("Error"):
                    error = body.get("ResponseMetadata", {}).get("Error") or body.get("Result", {}).get("Error")
                    raise ProviderError(str(error.get("Message") or error.get("message") or "火山引擎 OpenAPI 请求失败"), code="volcengine_openapi_failed", status=502)
                result = body.get("Result") or body.get("result") or body
                page_items = result.get("Statuses") or result.get("statuses") or []
                if isinstance(page_items, dict):
                    page_items = list(page_items.values())
                for item in page_items:
                    if not isinstance(item, dict):
                        continue
                    speaker_id = item.get("SpeakerID") or item.get("speaker_id") or item.get("SpeakerId") or item.get("speakerId")
                    status = str(item.get("State") or item.get("state") or "")
                    if not speaker_id or status not in {"Success", "Active"}:
                        continue
                    created_at = item.get("CreateTime") or item.get("create_time") or ""
                    if isinstance(created_at, (int, float)):
                        created_at = dt.datetime.fromtimestamp(created_at / 1000, tz=dt.timezone.utc).isoformat()
                    items.append({
                        "provider_voice_id": str(speaker_id),
                        "model_id": "seed-icl-2.0",
                        "display_name": item.get("Alias") or item.get("Name") or item.get("name") or f"火山复刻音色 · {speaker_id}",
                        "language": "zh",
                        "created_at": created_at,
                        "status": status,
                    })
                next_token = str(result.get("NextToken") or result.get("next_token") or "")
                if not page_items or not next_token:
                    break
                page += 1
        return items
