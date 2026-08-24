from __future__ import annotations

import base64
import asyncio
import hashlib
import json
import mimetypes
import os
import platform
import secrets
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
import uuid
import wave
import zipfile
from contextlib import contextmanager, suppress
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, AsyncIterator
from urllib.parse import urlparse

import httpx
from fastapi import Depends, FastAPI, File, Header, HTTPException, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette.background import BackgroundTask
from starlette.middleware.trustedhost import TrustedHostMiddleware

from .credentials import CredentialStoreError, credential_store_name, credential_store_status, delete_api_key, environment_credentials_enabled, environment_provider_credentials, load_api_key, load_provider_credentials, save_api_key, save_provider_credentials
from .providers.base import ProviderError, SynthesisRequest
from .providers.demo import DemoProvider
from .providers.mimo import DEFAULT_ENDPOINT as MIMO_ENDPOINT
from .providers.mimo import MIMO_MODELS, MiMoProvider
from .providers.qwen import DEFAULT_ENDPOINT as QWEN_ENDPOINT
from .providers.qwen import QWEN_MODELS, QwenProvider
from .providers.volcengine import DEFAULT_ENDPOINT as VOLCENGINE_ENDPOINT
from .providers.volcengine import VOLCENGINE_MODELS, VolcengineProvider
from .providers.minimax import DEFAULT_ENDPOINT as MINIMAX_PROVIDER_ENDPOINT
from .providers.minimax import MINIMAX_MODELS, MiniMaxProvider
from .storage import (
    automatic_cleanup_due,
    build_cleanup_plan,
    cleanup_preview,
    execute_cleanup,
    init_storage_schema,
    read_policy,
    storage_snapshot,
    write_policy,
)

ROOT = Path(os.getenv("VOICE_STUDIO_ROOT", Path(__file__).resolve().parents[2])).expanduser().resolve()
DATA = ROOT / "data"
AUDIO = DATA / "audio"
DB_PATH = DATA / "voice_studio.db"
FRONTEND_DIST = ROOT / "frontend" / "dist"
GATEWAY_CONFIG_PATH = DATA / "gateway.json"
try:
    APP_PORT = int(os.getenv("VOICE_STUDIO_PORT", "8765"))
except ValueError:
    APP_PORT = 8765
if not 1 <= APP_PORT <= 65535:
    APP_PORT = 8765
LOCAL_BASE_URL = f"http://127.0.0.1:{APP_PORT}"
MINIMAX_ENDPOINT = MINIMAX_PROVIDER_ENDPOINT
PROVIDER_SPECS = {
    "dashscope": {"display_name": "通义千问", "secret_label": "标准 API Key", "default_endpoint": QWEN_ENDPOINT, "endpoint_note": "中国大陆站官方地址", "verification": "remote_auth"},
    "volcengine": {"display_name": "火山引擎", "secret_label": "API Key", "default_endpoint": VOLCENGINE_ENDPOINT, "endpoint_note": "新版豆包语音 API 官方地址", "verification": "remote_auth", "openapi_note": "云端音色同步需要额外的 OpenAPI AK/SK 与项目名称"},
    "minimax": {"display_name": "MiniMax", "secret_label": "API Key", "default_endpoint": MINIMAX_ENDPOINT, "endpoint_note": "中国大陆站官方地址，必须包含 /v1", "verification": "credential_storage"},
    "mimo": {"display_name": "小米 MiMo", "secret_label": "API Key", "default_endpoint": MIMO_ENDPOINT, "endpoint_note": "官方公共 API 地址", "verification": "remote_auth"},
}
OFFICIAL_ENDPOINT_HOSTS = {
    "dashscope": {"dashscope.aliyuncs.com", "dashscope-intl.aliyuncs.com", "dashscope-us.aliyuncs.com"},
    "volcengine": {"openspeech.bytedance.com"},
    "minimax": {"api.minimaxi.com", "api.minimax.io"},
    "mimo": {"api.xiaomimimo.com"},
}
LOCAL_BROWSER_ORIGINS = {
    "http://127.0.0.1:5173",
    "http://localhost:5173",
    LOCAL_BASE_URL,
    f"http://localhost:{APP_PORT}",
}
LOCAL_BROWSER_ORIGINS.update(
    origin.strip()
    for origin in os.getenv("VOICE_STUDIO_ALLOWED_ORIGINS", "").split(",")
    if origin.strip()
)
TRUSTED_HOSTS = ["127.0.0.1", "localhost", "test"]
TRUSTED_HOSTS.extend(
    host.strip()
    for host in os.getenv("VOICE_STUDIO_ALLOWED_HOSTS", "").split(",")
    if host.strip()
)

app = FastAPI(title="Voice Studio Gateway", version=os.getenv("VOICE_STUDIO_VERSION", "0.7.0"))
app.add_middleware(CORSMiddleware, allow_origins=sorted(LOCAL_BROWSER_ORIGINS), allow_methods=["*"], allow_headers=["*"])
app.add_middleware(TrustedHostMiddleware, allowed_hosts=TRUSTED_HOSTS)
demo_provider = DemoProvider()
storage_cleanup_task: asyncio.Task[None] | None = None


@app.middleware("http")
async def reject_untrusted_browser_origin(request: Request, call_next):
    origin = request.headers.get("origin")
    if origin and origin not in LOCAL_BROWSER_ORIGINS:
        return JSONResponse(
            status_code=403,
            content={"error": {"message": "不允许的浏览器来源", "type": "authentication_error", "code": "untrusted_origin"}},
        )
    return await call_next(request)


@app.exception_handler(HTTPException)
async def openai_http_exception_handler(_, exc: HTTPException):
    detail = exc.detail
    if isinstance(detail, dict) and isinstance(detail.get("error"), dict):
        content = detail
    elif isinstance(detail, dict):
        content = {
            "error": {
                "message": str(detail.get("message") or detail),
                "type": "authentication_error" if exc.status_code == 401 else "invalid_request_error",
                "code": str(detail.get("code") or "request_failed"),
            }
        }
    else:
        content = {
            "error": {
                "message": str(detail),
                "type": "authentication_error" if exc.status_code == 401 else "invalid_request_error",
                "code": "authentication_error" if exc.status_code == 401 else "request_failed",
            }
        }
    return JSONResponse(status_code=exc.status_code, content=content, headers=exc.headers)


@app.exception_handler(RequestValidationError)
async def openai_validation_exception_handler(_, exc: RequestValidationError):
    messages = [str(item.get("msg") or "参数无效") for item in exc.errors()]
    return JSONResponse(
        status_code=400,
        content={
            "error": {
                "message": "; ".join(messages),
                "type": "invalid_request_error",
                "code": "invalid_request",
            }
        },
    )


def gateway_key() -> str:
    configured = os.getenv("VOICE_STUDIO_GATEWAY_KEY", "").strip()
    if configured:
        return configured
    try:
        if GATEWAY_CONFIG_PATH.exists():
            content = json.loads(GATEWAY_CONFIG_PATH.read_text(encoding="utf-8"))
            value = str(content.get("key") or "").strip()
            if value:
                return value
    except (OSError, json.JSONDecodeError, AttributeError):
        pass
    value = "vs_" + secrets.token_urlsafe(24)
    DATA.mkdir(parents=True, exist_ok=True)
    temp_path = GATEWAY_CONFIG_PATH.with_suffix(".tmp")
    temp_path.write_text(json.dumps({"key": value}, ensure_ascii=False, indent=2), encoding="utf-8")
    temp_path.replace(GATEWAY_CONFIG_PATH)
    return value


def gateway_key_source() -> str:
    return "环境变量 VOICE_STUDIO_GATEWAY_KEY" if os.getenv("VOICE_STUDIO_GATEWAY_KEY", "").strip() else "本地 gateway.json"


def available_models():
    return [*demo_provider.models(), *QWEN_MODELS, *VOLCENGINE_MODELS, *MINIMAX_MODELS, *MIMO_MODELS]


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sync_environment_accounts(connection: sqlite3.Connection) -> None:
    """Expose explicitly configured Docker credentials as read-only account metadata."""
    if not environment_credentials_enabled():
        return
    provider_names = {"dashscope": "通义千问", "volcengine": "火山引擎", "minimax": "MiniMax", "mimo": "小米 MiMo"}
    for provider, display_name in provider_names.items():
        credentials = environment_provider_credentials(provider)
        if not credentials.get("api_key"):
            continue
        account_id = "env_" + provider
        timestamp = now()
        project_name = os.getenv("VOICE_STUDIO_VOLCENGINE_PROJECT_NAME", "").strip() if provider == "volcengine" else None
        connection.execute(
            """INSERT INTO provider_accounts
               (id, provider, display_name, account_ref, region, endpoint, status, secret_hint,
                verification_scope, verification_message, created_at, updated_at, last_verified_at)
               VALUES (?, ?, ?, ?, NULL, ?, 'configured', ?, 'environment', ?, ?, ?, NULL)
               ON CONFLICT(id) DO UPDATE SET display_name=excluded.display_name,
                 account_ref=excluded.account_ref, endpoint=excluded.endpoint,
                 status='configured', secret_hint=excluded.secret_hint,
                 verification_scope='environment', verification_message=excluded.verification_message,
                 updated_at=excluded.updated_at, last_verified_at=NULL""",
            (
                account_id,
                provider,
                f"{display_name} · Docker 环境变量",
                project_name,
                PROVIDER_SPECS[provider]["default_endpoint"],
                "••••" + credentials["api_key"][-4:],
                "由 Docker 环境变量提供，不能在页面中修改。",
                timestamp,
                timestamp,
            ),
        )


@contextmanager
def db():
    DATA.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def init_db() -> None:
    with db() as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS voices (id TEXT PRIMARY KEY, provider TEXT NOT NULL, model_id TEXT NOT NULL,
              provider_voice_id TEXT, display_name TEXT NOT NULL, public_name TEXT NOT NULL, voice_type TEXT NOT NULL,
              status TEXT NOT NULL, languages TEXT NOT NULL, created_at TEXT NOT NULL, preview_asset TEXT,
              design_prompt TEXT NOT NULL DEFAULT '');
            CREATE TABLE IF NOT EXISTS jobs (id TEXT PRIMARY KEY, model TEXT NOT NULL, voice TEXT NOT NULL,
              input_chars INTEGER NOT NULL, status TEXT NOT NULL, duration_ms INTEGER, audio_path TEXT, created_at TEXT NOT NULL,
              source TEXT NOT NULL, demo INTEGER NOT NULL DEFAULT 1, input_text TEXT NOT NULL DEFAULT '');
            CREATE TABLE IF NOT EXISTS gateway_clients (id TEXT PRIMARY KEY, display_name TEXT NOT NULL, key_hash TEXT NOT NULL,
              key_prefix TEXT NOT NULL, status TEXT NOT NULL, created_at TEXT NOT NULL, last_used_at TEXT);
            CREATE TABLE IF NOT EXISTS gateway_requests (id TEXT PRIMARY KEY, endpoint TEXT NOT NULL, provider TEXT,
              model TEXT, voice TEXT, status TEXT NOT NULL, status_code INTEGER NOT NULL, error_code TEXT,
              first_chunk_latency_ms INTEGER, total_latency_ms INTEGER, chunk_count INTEGER NOT NULL DEFAULT 0,
              audio_bytes INTEGER NOT NULL DEFAULT 0, input_chars INTEGER NOT NULL DEFAULT 0,
              response_format TEXT, native_streaming INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL);
            CREATE INDEX IF NOT EXISTS idx_gateway_requests_created_at ON gateway_requests(created_at);
            CREATE INDEX IF NOT EXISTS idx_gateway_requests_provider_model ON gateway_requests(provider, model);
            CREATE TABLE IF NOT EXISTS provider_accounts (id TEXT PRIMARY KEY, provider TEXT NOT NULL, display_name TEXT NOT NULL,
              account_ref TEXT, region TEXT, endpoint TEXT, status TEXT NOT NULL, secret_hint TEXT NOT NULL,
              verification_scope TEXT NOT NULL, verification_message TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
              last_verified_at TEXT);
            """
        )
        voice_columns = {row[1] for row in connection.execute("PRAGMA table_info(voices)").fetchall()}
        if "design_prompt" not in voice_columns:
            connection.execute("ALTER TABLE voices ADD COLUMN design_prompt TEXT NOT NULL DEFAULT ''")
        job_columns = {row[1] for row in connection.execute("PRAGMA table_info(jobs)").fetchall()}
        if "input_text" not in job_columns:
            connection.execute("ALTER TABLE jobs ADD COLUMN input_text TEXT NOT NULL DEFAULT ''")
        if "audio_cleaned_at" not in job_columns:
            connection.execute("ALTER TABLE jobs ADD COLUMN audio_cleaned_at TEXT")
        if "audio_cleanup_reason" not in job_columns:
            connection.execute("ALTER TABLE jobs ADD COLUMN audio_cleanup_reason TEXT")
        init_storage_schema(connection)
        if connection.execute("SELECT COUNT(*) FROM voices").fetchone()[0] == 0:
            seed = [
                ("voice_narrator", "minimax", "speech-2.8-turbo", "narrator", "旁白 · 沉稳", "narrator", "preset", "active", ["zh-CN", "en-US"]),
                ("voice_coral", "dashscope", "qwen3-tts-flash", "coral", "Coral · 清亮", "coral", "preset", "active", ["zh-CN"]),
                ("voice_nova", "volcengine", "seed-tts-2.0", "zh_female_vv_uranus_bigtts", "Vivi 2.0 · 通用女声", "volc-vivi", "preset", "active", ["zh-CN", "en-US"]),
            ]
            connection.executemany(
                "INSERT INTO voices (id,provider,model_id,provider_voice_id,display_name,public_name,voice_type,status,languages,created_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
                [(a,b,c,d,e,f,g,h,json.dumps(i, ensure_ascii=False),now()) for a,b,c,d,e,f,g,h,i in seed],
            )
        connection.execute(
            "INSERT OR IGNORE INTO voices (id,provider,model_id,provider_voice_id,display_name,public_name,voice_type,status,languages,created_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
            ("voice_local_demo", "demo", "local-demo", "local-demo", "本地演示音色", "local-demo", "preset", "active", json.dumps(["zh-CN", "en-US"], ensure_ascii=False), now()),
        )
        mimo_voices = [
            ("voice_mimo_default", "mimo_default", "MiMo 默认", "mimo-default", ["zh-CN", "en-US"]),
            ("voice_mimo_bingtang", "冰糖", "冰糖 · 清甜女声", "bingtang", ["zh-CN"]),
            ("voice_mimo_moli", "茉莉", "茉莉 · 自然女声", "moli", ["zh-CN"]),
            ("voice_mimo_suda", "苏打", "苏打 · 清朗男声", "suda", ["zh-CN"]),
            ("voice_mimo_baihua", "白桦", "白桦 · 沉稳男声", "baihua", ["zh-CN"]),
            ("voice_mimo_mia", "Mia", "Mia · English", "mia", ["en-US"]),
            ("voice_mimo_chloe", "Chloe", "Chloe · English", "chloe", ["en-US"]),
            ("voice_mimo_milo", "Milo", "Milo · English", "milo", ["en-US"]),
            ("voice_mimo_dean", "Dean", "Dean · English", "dean", ["en-US"]),
        ]
        connection.executemany(
            "INSERT OR IGNORE INTO voices (id,provider,model_id,provider_voice_id,display_name,public_name,voice_type,status,languages,created_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
            [(voice_id, "mimo", "mimo-v2.5-tts", remote_id, name, alias, "preset", "active", json.dumps(languages, ensure_ascii=False), now()) for voice_id,remote_id,name,alias,languages in mimo_voices],
        )
        qwen_voices = [
            ("Cherry", "Cherry · 明快女声", "cherry", ["zh-CN", "en-US"]),
            ("Serena", "Serena · 温柔女声", "serena", ["zh-CN", "en-US"]),
            ("Ethan", "Ethan · 温暖男声", "ethan", ["zh-CN", "en-US"]),
            ("Chelsie", "Chelsie · 灵动女声", "chelsie", ["zh-CN", "en-US"]),
        ]
        for model_id, prefix in (("qwen3-tts-flash", "qwen_flash"), ("qwen3-tts-instruct-flash", "qwen_instruct")):
            connection.executemany(
                "INSERT OR IGNORE INTO voices (id,provider,model_id,provider_voice_id,display_name,public_name,voice_type,status,languages,created_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
                [
                    (
                        f"voice_{prefix}_{remote_id.lower()}",
                        "dashscope",
                        model_id,
                        remote_id,
                        display_name,
                        f"{prefix.replace('_', '-')}-{alias}",
                        "preset",
                        "active",
                        json.dumps(languages, ensure_ascii=False),
                        now(),
                    )
                    for remote_id, display_name, alias, languages in qwen_voices
                    if not (model_id == "qwen3-tts-flash" and remote_id == "Cherry")
                ],
            )
        cosy_voices = [
            ("longanyang", "龙安阳 · 阳光男声", "longanyang"),
            ("longanhuan", "龙安欢 · 活力女声", "longanhuan"),
            ("longhuhu_v3", "龙呼呼 · 灵动女声", "longhuhu"),
        ]
        for model_id, prefix in (("cosyvoice-v3-flash", "cosy_flash"), ("cosyvoice-v3-plus", "cosy_plus")):
            connection.executemany(
                "INSERT OR IGNORE INTO voices (id,provider,model_id,provider_voice_id,display_name,public_name,voice_type,status,languages,created_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
                [
                    (
                        f"voice_{prefix}_{alias}",
                        "dashscope",
                        model_id,
                        remote_id,
                        display_name,
                        f"{prefix.replace('_', '-')}-{alias}",
                        "preset",
                        "active",
                        json.dumps(["zh-CN", "en-US"], ensure_ascii=False),
                        now(),
                    )
                    for remote_id, display_name, alias in cosy_voices
                ],
            )
        connection.executemany(
            "UPDATE voices SET model_id=?,provider_voice_id=?,display_name=? WHERE id=?",
            [
                ("speech-2.8-turbo", "presenter_male", "男性主持人", "voice_narrator"),
                ("qwen3-tts-flash", "Cherry", "Cherry · 明快女声", "voice_coral"),
                ("seed-tts-2.0", "zh_female_vv_uranus_bigtts", "Vivi 2.0 · 通用女声", "voice_nova"),
            ],
        )
        volcengine_voices = [
            ("voice_volc_vivi", "zh_female_vv_uranus_bigtts", "Vivi 2.0 · 通用女声", "volc-vivi"),
            ("voice_volc_xiaohe", "zh_female_xiaohe_uranus_bigtts", "小何 2.0 · 自然女声", "volc-xiaohe"),
            ("voice_volc_yunzhou", "zh_male_m191_uranus_bigtts", "云舟 2.0 · 稳重男声", "volc-yunzhou"),
            ("voice_volc_xiaotian", "zh_male_taocheng_uranus_bigtts", "小天 2.0 · 清朗男声", "volc-xiaotian"),
            ("voice_volc_sophie", "zh_female_sophie_uranus_bigtts", "魅力苏菲 2.0", "volc-sophie"),
            ("voice_volc_narrator", "zh_male_jieshuoxiaoming_uranus_bigtts", "解说小明 2.0", "volc-narrator"),
        ]
        connection.executemany(
            "INSERT OR IGNORE INTO voices (id,provider,model_id,provider_voice_id,display_name,public_name,voice_type,status,languages,created_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
            [(voice_id, "volcengine", "seed-tts-2.0", remote_id, name, alias, "preset", "active", json.dumps(["zh-CN", "en-US"], ensure_ascii=False), now()) for voice_id,remote_id,name,alias in volcengine_voices],
        )
        connection.execute("DELETE FROM voices WHERE id='voice_nova'")
        connection.execute(
            "UPDATE voices SET status='legacy' WHERE provider='minimax' AND status='active' AND (model_id='speech-demo' OR provider_voice_id LIKE 'reference_%')"
        )
        connection.execute("UPDATE voices SET status='legacy' WHERE id='voice_minimax_presenter-male'")
        minimax_voices = [
            ("male-qn-qingse", "青涩青年音色", "qingse"),
            ("female-shaonv", "少女音色", "shaonv"),
            ("presenter_female", "女性主持人", "presenter-female"),
        ]
        connection.executemany(
            "INSERT OR IGNORE INTO voices (id,provider,model_id,provider_voice_id,display_name,public_name,voice_type,status,languages,created_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
            [
                (f"voice_minimax_{alias}", "minimax", "speech-2.8-turbo", remote_id, display_name, f"minimax-{alias}", "preset", "active", json.dumps(["zh-CN", "en-US"], ensure_ascii=False), now())
                for remote_id, display_name, alias in minimax_voices
            ],
        )
        sync_environment_accounts(connection)
        if connection.execute("SELECT COUNT(*) FROM gateway_clients").fetchone()[0] == 0:
            key = gateway_key()
            connection.execute("INSERT INTO gateway_clients VALUES (?,?,?,?,?,?,?)", ("client_demo", "本地演示客户端", hashlib.sha256(key.encode()).hexdigest(), key[:10], "active", now(), None))


@app.on_event("startup")
async def startup() -> None:
    global storage_cleanup_task
    init_db()
    await asyncio.to_thread(run_scheduled_storage_cleanup)
    storage_cleanup_task = asyncio.create_task(storage_cleanup_loop())


@app.on_event("shutdown")
async def shutdown() -> None:
    global storage_cleanup_task
    if storage_cleanup_task is None:
        return
    storage_cleanup_task.cancel()
    with suppress(asyncio.CancelledError):
        await storage_cleanup_task
    storage_cleanup_task = None


def run_scheduled_storage_cleanup() -> dict[str, Any] | None:
    with db() as connection:
        if not automatic_cleanup_due(connection):
            return None
        return execute_cleanup(
            connection,
            ROOT,
            AUDIO,
            trigger="automatic",
            run_id="cleanup_" + uuid.uuid4().hex[:12],
        )


async def storage_cleanup_loop() -> None:
    while True:
        await asyncio.sleep(60 * 60)
        try:
            await asyncio.to_thread(run_scheduled_storage_cleanup)
        except Exception as exc:
            print(f"Storage cleanup check failed: {exc}")


class SynthesisBody(BaseModel):
    model: str = Field(min_length=1, max_length=200)
    voice: str = Field(min_length=1, max_length=200)
    input: str = Field(min_length=1, max_length=10000)
    response_format: str = Field(default="mp3")
    speed: float = Field(default=1.0, ge=0.25, le=4.0)
    instructions: str | None = Field(default=None, max_length=2000)
    voice_studio: dict[str, Any] | None = None


class StreamingSynthesisBody(SynthesisBody):
    """Request body for the gateway's SSE audio stream."""

    chunk_size: int = Field(default=8192, ge=1024, le=65536)


class ImportVoiceBody(BaseModel):
    provider: str
    model_id: str
    provider_voice_id: str
    display_name: str
    public_name: str
    languages: list[str] = ["zh-CN"]


class ImportVoicesBody(BaseModel):
    voices: list[ImportVoiceBody] = Field(min_length=1, max_length=100)


class JobBatchBody(BaseModel):
    job_ids: list[str] = Field(default_factory=list, max_length=500)
    date: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")


class StoragePolicyBody(BaseModel):
    automatic_enabled: bool = False
    retention_days: int = Field(default=30, ge=1, le=3650)
    capacity_limit_bytes: int = Field(default=5 * 1024 * 1024 * 1024, ge=100 * 1024 * 1024, le=10 * 1024 * 1024 * 1024 * 1024)
    interval: str = Field(default="daily", pattern=r"^(daily|weekly)$")
    cleanup_scope: str = Field(default="audio_only", pattern=r"^(audio_only|jobs)$")


class ProviderAccountBody(BaseModel):
    provider: str
    display_name: str = Field(min_length=1, max_length=80)
    api_key: str | None = Field(default=None, min_length=6, max_length=4096)
    endpoint: str | None = Field(default=None, max_length=500)
    openapi_access_key: str | None = Field(default=None, max_length=4096)
    openapi_secret_key: str | None = Field(default=None, max_length=4096)
    project_name: str | None = Field(default=None, max_length=200)


class VoiceDesignBody(BaseModel):
    provider: str
    model_id: str
    prompt: str = Field(min_length=8, max_length=2000)
    preview_text: str = Field(min_length=1, max_length=2000)
    display_name: str = Field(min_length=1, max_length=100)
    public_name: str = Field(min_length=1, max_length=100)


def error(message: str, type_: str = "invalid_request_error", code: str = "invalid_request", status_code: int = 400) -> JSONResponse:
    return JSONResponse(status_code=status_code, content={"error": {"message": message, "type": type_, "code": code}})


def record_gateway_request(
    *,
    request_id: str,
    endpoint: str,
    status: str,
    status_code: int,
    provider: str | None = None,
    model: str | None = None,
    voice: str | None = None,
    error_code: str | None = None,
    first_chunk_latency_ms: int | None = None,
    total_latency_ms: int | None = None,
    chunk_count: int = 0,
    audio_bytes: int = 0,
    input_chars: int = 0,
    response_format: str | None = None,
    native_streaming: bool = False,
) -> None:
    with db() as connection:
        connection.execute(
            """INSERT OR REPLACE INTO gateway_requests
               (id,endpoint,provider,model,voice,status,status_code,error_code,first_chunk_latency_ms,total_latency_ms,
                chunk_count,audio_bytes,input_chars,response_format,native_streaming,created_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                request_id,
                endpoint,
                provider,
                model,
                voice,
                status,
                status_code,
                error_code,
                first_chunk_latency_ms,
                total_latency_ms,
                chunk_count,
                audio_bytes,
                input_chars,
                response_format,
                int(native_streaming),
                now(),
            ),
        )


def percentile(values: list[int], fraction: float) -> int | None:
    if not values:
        return None
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, int((len(ordered) - 1) * fraction + 0.5)))
    return ordered[index]


def latency_summary(rows: list[sqlite3.Row], column: str) -> dict[str, int | None]:
    values = [int(row[column]) for row in rows if row[column] is not None]
    return {"p50": percentile(values, 0.5), "p95": percentile(values, 0.95), "samples": len(values)}


def require_gateway_key(authorization: str | None = Header(default=None)) -> None:
    scheme, _, token = (authorization or "").partition(" ")
    if scheme.lower() != "bearer" or not secrets.compare_digest(token.strip(), gateway_key()):
        raise HTTPException(status_code=401, detail={"error": {"message": "无效的网关 Key", "type": "authentication_error", "code": "gateway_auth_failed"}})


def resolve_model(model_id: str):
    aliases = {"tts-default": "mimo/mimo-v2.5-tts", "tts-fast": "dashscope/qwen3-tts-flash", "tts-hq": "mimo/mimo-v2.5-tts"}
    target = aliases.get(model_id, model_id)
    for model in available_models():
        if model.gateway_id == target:
            return model
    return None


def openai_model_item(model, requested_id: str | None = None) -> dict[str, Any]:
    operations = list(model.operations)
    if "synthesis" in operations and "streaming" not in operations:
        operations.append("streaming")
    native_streaming = (
        model.provider == "volcengine"
        or model.provider == "minimax"
        or (model.provider == "mimo" and model.model_id != "mimo-v2.5-tts-voicedesign")
        or (model.provider == "dashscope" and model.model_id in {"cosyvoice-v3-flash", "cosyvoice-v3-plus"})
    )
    return {
        "id": requested_id or model.gateway_id,
        "object": "model",
        "created": int(time.time()),
        "owned_by": model.provider,
        "voice_studio": {
            "mode": model.mode,
            "operations": operations,
            "supports_clone": model.supports_clone,
            "native_streaming": native_streaming,
            "native_stream_formats": ["pcm"] if (model.provider == "mimo" and model.model_id != "mimo-v2.5-tts-voicedesign") else (["mp3"] if native_streaming else []),
        },
    }


def resolve_voice(voice_id: str, model):
    if model.provider == "mimo" and model.model_id == "mimo-v2.5-tts":
        aliases = {"alloy": "mimo-default", "coral": "bingtang", "nova": "suda", "shimmer": "moli"}
    elif model.provider == "dashscope" and model.model_id == "qwen3-tts-flash":
        aliases = {"alloy": "Ethan", "coral": "Cherry", "nova": "Serena", "shimmer": "Chelsie"}
    elif model.provider == "dashscope" and model.model_id == "qwen3-tts-instruct-flash":
        aliases = {"alloy": "Ethan", "coral": "Cherry", "nova": "Serena", "shimmer": "Chelsie"}
    elif model.provider == "volcengine" and model.model_id == "seed-tts-2.0":
        aliases = {"alloy": "volc-yunzhou", "coral": "volc-vivi", "nova": "volc-xiaohe", "shimmer": "volc-sophie"}
    else:
        aliases = {"alloy": "voice_narrator", "coral": "voice_coral", "nova": "voice_nova"}
    target = aliases.get(voice_id, voice_id)
    with db() as connection:
        if model.mode == "demo":
            row = connection.execute(
                "SELECT * FROM voices WHERE provider=? AND (id=? OR public_name=? OR provider_voice_id=?)",
                (model.provider, target, target, target),
            ).fetchone()
        elif model.provider == "minimax":
            row = connection.execute(
                "SELECT * FROM voices WHERE provider='minimax' AND (id=? OR public_name=? OR provider_voice_id=?) AND status='active'",
                (target, target, target),
            ).fetchone()
        else:
            row = connection.execute(
                "SELECT * FROM voices WHERE provider=? AND model_id=? AND (id=? OR public_name=? OR provider_voice_id=?)",
                (model.provider, model.model_id, target, target, target),
            ).fetchone()
    if row:
        if model.mode == "demo" and row["provider"] == model.provider:
            return row
        if model.provider != "minimax" and f"{row['provider']}/{row['model_id']}" != model.gateway_id:
            return None
    return row


def voice_payload(model, voice: sqlite3.Row, fallback: str) -> str:
    if model.provider == "mimo" and model.model_id == "mimo-v2.5-tts-voicedesign":
        return ""
    if model.provider == "mimo" and model.model_id == "mimo-v2.5-tts-voiceclone":
        asset_path = voice["preview_asset"]
        if not asset_path:
            raise ProviderError("该复刻音色缺少本地参考音频", code="missing_reference_audio", status=409)
        asset = (ROOT / asset_path).resolve()
        try:
            asset.relative_to(AUDIO.resolve())
        except ValueError as exc:
            raise ProviderError("复刻音色的参考音频路径无效", code="invalid_reference_audio", status=409) from exc
        if not asset.is_file():
            raise ProviderError("找不到复刻音色的本地参考音频", code="missing_reference_audio", status=409)
        mime_type = mimetypes.guess_type(asset.name)[0] or "audio/wav"
        return f"data:{mime_type};base64,{base64.b64encode(asset.read_bytes()).decode('ascii')}"
    return voice["provider_voice_id"] or fallback


def provider_for(model_provider: str):
    if model_provider not in {"dashscope", "mimo", "volcengine", "minimax"}:
        return demo_provider
    with db() as connection:
        row = connection.execute(
            "SELECT * FROM provider_accounts WHERE provider=? ORDER BY CASE status WHEN 'active' THEN 0 ELSE 1 END, created_at LIMIT 1",
            (model_provider,),
        ).fetchone()
    provider_name = {"dashscope": "通义千问", "mimo": "小米 MiMo", "volcengine": "火山引擎", "minimax": "MiniMax"}[model_provider]
    if not row:
        raise ProviderError(f"尚未在设置中配置{provider_name} API Key", code="provider_not_configured", status=409)
    try:
        api_key = load_api_key(row["id"])
    except CredentialStoreError as exc:
        raise ProviderError(str(exc), code="credential_store_error", status=503) from exc
    if not api_key:
        raise ProviderError(f"{credential_store_name()}中没有找到{provider_name}凭据", code="provider_not_configured", status=409)
    try:
        endpoint = validate_provider_endpoint(model_provider, row["endpoint"] or PROVIDER_SPECS[model_provider]["default_endpoint"])
    except ValueError as exc:
        raise ProviderError(str(exc), code="unsafe_provider_endpoint", status=409) from exc
    if model_provider == "dashscope":
        return QwenProvider(api_key, endpoint)
    if model_provider == "volcengine":
        try:
            credentials = load_provider_credentials(row["id"])
        except CredentialStoreError as exc:
            raise ProviderError(str(exc), code="credential_store_error", status=503) from exc
        return VolcengineProvider(api_key, endpoint, credentials.get("openapi_access_key"), credentials.get("openapi_secret_key"), row["account_ref"])
    if model_provider == "minimax":
        return MiniMaxProvider(api_key, endpoint)
    return MiMoProvider(api_key, endpoint)


def convert_audio(wav_path: Path, output_format: str) -> tuple[Path, str]:
    if output_format == "wav":
        return wav_path, "audio/wav"
    mime_types = {"mp3": "audio/mpeg", "opus": "audio/ogg", "aac": "audio/aac", "flac": "audio/flac", "pcm": "application/octet-stream"}
    target = wav_path.with_suffix("." + output_format)
    command = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(wav_path)]
    if output_format == "pcm":
        command += ["-f", "s16le", "-acodec", "pcm_s16le"]
    elif output_format == "opus":
        command += ["-c:a", "libopus"]
    command.append(str(target))
    completed = subprocess.run(command, capture_output=True, text=True, timeout=60)
    if completed.returncode != 0:
        raise ProviderError("音频格式转换失败", code="audio_conversion_failed")
    return target, mime_types[output_format]


def audio_metadata(wav_path: Path) -> dict[str, int]:
    try:
        with wave.open(str(wav_path), "rb") as stream:
            return {"sample_rate": stream.getframerate(), "channels": stream.getnchannels(), "sample_width": stream.getsampwidth()}
    except (OSError, wave.Error):
        return {}


def storage_path(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


@app.get("/api/summary")
def summary():
    with db() as connection:
        voices = connection.execute("SELECT COUNT(*) FROM voices WHERE status='active'").fetchone()[0]
        jobs = connection.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
        successful = connection.execute("SELECT COUNT(*) FROM jobs WHERE status='completed'").fetchone()[0]
    key = gateway_key()
    return {"application": "voice-studio", "version": app.version, "voices": voices, "jobs": jobs, "successful_jobs": successful, "gateway": {"enabled": True, "base_url": "/v1", "key_prefix": key[:10]}}


def _command_diagnostic(command: str, arguments: list[str], required: bool) -> dict[str, Any]:
    path = shutil.which(command)
    if not path:
        return {
            "id": command,
            "label": command,
            "status": "error" if required else "warning",
            "version": "",
            "detail": f"未找到 {command}，请安装后加入系统 Path。" if required else f"未找到 {command}；使用预构建版本时不影响运行。",
        }
    try:
        completed = subprocess.run([path, *arguments], capture_output=True, text=True, timeout=10)
        output = (completed.stdout or completed.stderr).splitlines()
        if completed.returncode != 0:
            raise OSError(f"exit code {completed.returncode}")
        return {"id": command, "label": command, "status": "ok", "version": output[0] if output else "可用", "detail": path}
    except (OSError, subprocess.SubprocessError) as exc:
        return {"id": command, "label": command, "status": "error" if required else "warning", "version": "", "detail": f"{command} 无法正常运行：{exc}"}


def system_diagnostics() -> dict[str, Any]:
    checks: list[dict[str, Any]] = [
        {
            "id": "python",
            "label": "Python",
            "status": "ok" if sys.version_info >= (3, 11) else "error",
            "version": platform.python_version(),
            "detail": sys.executable,
        },
        _command_diagnostic("ffmpeg", ["-version"], True),
        _command_diagnostic("ffprobe", ["-version"], True),
    ]
    frontend_ready = (FRONTEND_DIST / "index.html").is_file()
    checks.append({
        "id": "frontend",
        "label": "前端文件",
        "status": "ok" if frontend_ready else "error",
        "version": "已构建" if frontend_ready else "缺失",
        "detail": str(FRONTEND_DIST),
    })
    node = _command_diagnostic("node", ["--version"], False)
    if frontend_ready:
        node["detail"] = f"{node['detail']} 当前前端已构建，日常启动不依赖 Node.js。"
    checks.append(node)
    credential = credential_store_status()
    checks.append({
        "id": "credentials",
        "label": "凭据存储",
        "status": "ok" if credential["available"] else "error",
        "version": credential["backend"],
        "detail": credential["message"],
    })
    try:
        DATA.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(prefix="voice-studio-", dir=DATA):
            pass
        data_check = {"id": "data", "label": "数据目录", "status": "ok", "version": "可写", "detail": str(DATA)}
    except OSError as exc:
        data_check = {"id": "data", "label": "数据目录", "status": "error", "version": "不可写", "detail": str(exc)}
    checks.append(data_check)
    required_failures = sum(item["status"] == "error" for item in checks)
    return {
        "status": "error" if required_failures else ("warning" if any(item["status"] == "warning" for item in checks) else "ok"),
        "platform": platform.platform(),
        "base_url": LOCAL_BASE_URL,
        "port": APP_PORT,
        "checks": checks,
        "required_failures": required_failures,
        "demo": {"model": "demo/local-demo", "voice": "local-demo", "available": True},
    }


@app.get("/api/system/diagnostics")
def get_system_diagnostics():
    return system_diagnostics()


@app.get("/api/providers")
def list_providers():
    names = {"dashscope": "通义千问", "volcengine": "火山引擎", "minimax": "MiniMax", "mimo": "小米 MiMo"}
    return [
        {
            "id": provider_id,
            "display_name": names[provider_id],
            "status": "provider",
            "models": [{**item.__dict__, "gateway_id": item.gateway_id} for item in available_models() if item.provider == provider_id],
        }
        for provider_id in names
    ]


def account_response(row: sqlite3.Row) -> dict[str, Any]:
    result = {**dict(row), "has_secret": True}
    if row["provider"] == "volcengine":
        try:
            credentials = load_provider_credentials(row["id"])
        except CredentialStoreError:
            credentials = {}
        access_key = credentials.get("openapi_access_key") or ""
        result.update({"project_name": row["account_ref"] or "", "openapi_access_key_hint": ("••••" + access_key[-4:]) if access_key else "", "has_openapi_secret": bool(credentials.get("openapi_secret_key"))})
    return result


def validate_provider_endpoint(provider: str, endpoint: str) -> str:
    normalized = endpoint.strip().rstrip("/")
    parsed = urlparse(normalized)
    if not parsed.netloc or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError("Endpoint 必须是有效地址，且不能包含账号、密码、查询参数或片段")
    custom_allowed = os.getenv("VOICE_STUDIO_ALLOW_CUSTOM_ENDPOINTS", "").strip().lower() in {"1", "true", "yes"}
    hostname = (parsed.hostname or "").lower()
    loopback_http = custom_allowed and parsed.scheme == "http" and hostname in {"127.0.0.1", "localhost", "::1"}
    if parsed.scheme != "https" and not loopback_http:
        raise ValueError("Endpoint 必须使用 HTTPS；仅显式启用自定义端点后允许本机 HTTP")
    if not custom_allowed and hostname not in OFFICIAL_ENDPOINT_HOSTS.get(provider, set()):
        raise ValueError("为防止 API Key 外传，Endpoint 只能使用该厂商的官方域名")
    return normalized


def normalize_account(body: ProviderAccountBody) -> tuple[dict[str, Any], dict[str, Any]]:
    spec = PROVIDER_SPECS.get(body.provider)
    if not spec:
        raise HTTPException(400, "不支持的厂商")
    try:
        endpoint = validate_provider_endpoint(body.provider, body.endpoint or spec["default_endpoint"])
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    values = {
        "provider": body.provider,
        "display_name": body.display_name.strip(),
        "account_ref": body.project_name.strip() if body.provider == "volcengine" and body.project_name else None,
        "region": None,
        "endpoint": endpoint or None,
    }
    return spec, values


@app.get("/api/provider-specs")
def provider_specs():
    return PROVIDER_SPECS


@app.get("/api/provider-accounts")
def list_provider_accounts():
    with db() as connection:
        rows = connection.execute("SELECT * FROM provider_accounts ORDER BY created_at").fetchall()
    return [account_response(row) for row in rows]


@app.post("/api/provider-accounts")
def create_provider_account(body: ProviderAccountBody):
    spec, values = normalize_account(body)
    if not body.api_key:
        raise HTTPException(400, "首次创建账号必须填写 API Key")
    account_id = "pa_" + uuid.uuid4().hex[:12]
    try:
        save_provider_credentials(account_id, api_key=body.api_key, **({"openapi_access_key": body.openapi_access_key, "openapi_secret_key": body.openapi_secret_key} if body.provider == "volcengine" else {}))
        timestamp = now()
        with db() as connection:
            connection.execute(
                "INSERT INTO provider_accounts VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (account_id, values["provider"], values["display_name"], values["account_ref"], values["region"], values["endpoint"], "configured", "••••" + body.api_key[-4:], spec["verification"], "凭据已安全保存，尚未完成真实鉴权。", timestamp, timestamp, None),
            )
            row = connection.execute("SELECT * FROM provider_accounts WHERE id=?", (account_id,)).fetchone()
    except CredentialStoreError as exc:
        raise HTTPException(503, str(exc)) from exc
    return account_response(row)


@app.put("/api/provider-accounts/{account_id}")
def update_provider_account(account_id: str, body: ProviderAccountBody):
    spec, values = normalize_account(body)
    with db() as connection:
        current = connection.execute("SELECT * FROM provider_accounts WHERE id=?", (account_id,)).fetchone()
    if not current:
        raise HTTPException(404, "厂商账号不存在")
    if body.api_key:
        try:
            save_api_key(account_id, body.api_key)
        except CredentialStoreError as exc:
            raise HTTPException(503, str(exc)) from exc
        secret_hint = "••••" + body.api_key[-4:]
    else:
        secret_hint = current["secret_hint"]
    if body.provider == "volcengine":
        try:
            save_provider_credentials(account_id, **({"openapi_access_key": body.openapi_access_key, "openapi_secret_key": body.openapi_secret_key} if body.openapi_access_key or body.openapi_secret_key else {}))
        except CredentialStoreError as exc:
            raise HTTPException(503, str(exc)) from exc
    with db() as connection:
        connection.execute(
            "UPDATE provider_accounts SET provider=?,display_name=?,account_ref=?,region=?,endpoint=?,status=?,secret_hint=?,verification_scope=?,verification_message=?,updated_at=?,last_verified_at=NULL WHERE id=?",
            (values["provider"], values["display_name"], values["account_ref"], values["region"], values["endpoint"], "configured", secret_hint, spec["verification"], "配置已更新，等待重新验证。", now(), account_id),
        )
        row = connection.execute("SELECT * FROM provider_accounts WHERE id=?", (account_id,)).fetchone()
    return account_response(row)


@app.delete("/api/provider-accounts/{account_id}")
def remove_provider_account(account_id: str):
    with db() as connection:
        row = connection.execute("SELECT id FROM provider_accounts WHERE id=?", (account_id,)).fetchone()
    if not row:
        raise HTTPException(404, "厂商账号不存在")
    try:
        delete_api_key(account_id)
    except CredentialStoreError as exc:
        raise HTTPException(503, str(exc)) from exc
    with db() as connection:
        connection.execute("DELETE FROM provider_accounts WHERE id=?", (account_id,))
    return {"deleted": True, "id": account_id}


@app.post("/api/provider-accounts/{account_id}/test")
async def test_provider_account(account_id: str):
    with db() as connection:
        row = connection.execute("SELECT * FROM provider_accounts WHERE id=?", (account_id,)).fetchone()
    if not row:
        raise HTTPException(404, "厂商账号不存在")
    try:
        api_key = load_api_key(account_id)
    except CredentialStoreError as exc:
        raise HTTPException(503, str(exc)) from exc
    if not api_key:
        raise HTTPException(409, f"{credential_store_name()}中没有找到该账号的凭据")
    try:
        endpoint = validate_provider_endpoint(row["provider"], row["endpoint"] or PROVIDER_SPECS[row["provider"]]["default_endpoint"])
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc

    status = "configured"
    verified_at = now()
    if row["provider"] == "minimax":
        try:
            async with httpx.AsyncClient(timeout=20) as client:
                response = await client.get(
                    endpoint.rstrip("/") + "/files/list",
                    headers={"Authorization": "Bearer " + api_key},
                    params={"purpose": "voice_clone"},
                )
            if response.status_code == 200 and (response.json().get("base_resp") or {}).get("status_code", 0) == 0:
                status = "active"
                message = "MiniMax API Key 真实鉴权通过，文件接口可用。"
            elif response.status_code in {401, 403}:
                status = "error"
                message = "MiniMax 鉴权失败，请检查 API Key。"
            else:
                status = "error"
                try:
                    detail = (response.json().get("base_resp") or {}).get("status_msg")
                except ValueError:
                    detail = None
                message = f"MiniMax 鉴权探针返回 HTTP {response.status_code}" + (f"：{str(detail)[:160]}" if detail else "。")
        except (httpx.HTTPError, ValueError):
            status = "error"
            message = "无法读取 MiniMax 文件列表，请检查网络和 Endpoint。"
    elif row["provider"] == "dashscope":
        if api_key.startswith("sk-sp-"):
            status = "error"
            message = "Token Plan Key 不支持 TTS，请使用千问控制台创建的标准 sk- API Key。"
        else:
            try:
                async with httpx.AsyncClient(timeout=20) as client:
                    response = await client.post(
                        endpoint.rstrip("/") + "/compatible-mode/v1/chat/completions",
                        headers={"Authorization": "Bearer " + api_key, "Content-Type": "application/json"},
                        json={"model": "qwen-turbo", "messages": [{"role": "user", "content": "Hi"}], "max_tokens": 1},
                    )
                if response.status_code == 200:
                    status = "active"
                    message = "千问标准 API Key 真实鉴权通过。"
                elif response.status_code in {401, 403}:
                    status = "error"
                    message = "千问鉴权失败，请检查 Key 来源、有效期和账号权限。"
                else:
                    status = "error"
                    message = f"千问鉴权探针返回 HTTP {response.status_code}，未判定为可用。"
            except httpx.HTTPError:
                status = "error"
                message = "无法连接千问 Endpoint，请检查网络和地址。"
    elif row["provider"] == "volcengine":
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                async with client.stream(
                    "POST",
                    endpoint.rstrip("/") + "/api/v3/tts/unidirectional",
                    headers={"X-Api-Key": api_key, "X-Api-Resource-Id": "seed-tts-2.0", "X-Api-Request-Id": str(uuid.uuid4()), "Content-Type": "application/json"},
                    json={"req_params": {"text": "Hello", "speaker": "zh_female_vv_uranus_bigtts", "audio_params": {"format": "mp3", "sample_rate": 24000}}},
                ) as response:
                    if response.status_code == 200:
                        items = [json.loads(line) async for line in response.aiter_lines() if line.strip()]
                        failed = next((item for item in items if item.get("code") not in {None, 0, 20000000}), None)
                        if failed:
                            status = "error"
                            message = f"火山引擎鉴权通过，但 Seed TTS 2.0 探针失败：{str(failed.get('message') or failed.get('code'))[:160]}"
                        elif any(item.get("data") for item in items):
                            status = "active"
                            message = "火山引擎 API Key 真实鉴权通过，账号可调用 Seed TTS 2.0。"
                        else:
                            status = "error"
                            message = "火山引擎鉴权探针未返回音频数据，未判定为可用。"
                    elif response.status_code in {401, 403}:
                        status = "error"
                        message = "火山引擎鉴权失败，请检查新版豆包语音 API Key。"
                    else:
                        await response.aread()
                        status = "error"
                        try:
                            detail = response.json().get("message")
                        except ValueError:
                            detail = None
                        message = f"火山引擎鉴权探针返回 HTTP {response.status_code}" + (f"：{str(detail)[:160]}" if detail else "。")
        except httpx.HTTPError:
            status = "error"
            message = "无法连接火山引擎 Endpoint，请检查网络和地址。"
    elif row["provider"] == "mimo":
        try:
            async with httpx.AsyncClient(timeout=20) as client:
                response = await client.get(endpoint.rstrip("/") + "/models", headers={"api-key": api_key})
            if response.status_code == 200:
                model_ids = {item.get("id") for item in response.json().get("data", [])}
                if "mimo-v2.5-tts" in model_ids:
                    status = "active"
                    message = "MiMo API Key 真实鉴权通过，账号已开放 MiMo V2.5 TTS。"
                else:
                    status = "error"
                    message = "MiMo 鉴权通过，但当前账号的模型列表中没有 MiMo V2.5 TTS。"
            elif response.status_code in {401, 403}:
                status = "error"
                message = "MiMo 鉴权失败，请检查 API Key。"
            else:
                status = "error"
                message = f"MiMo 鉴权探针返回 HTTP {response.status_code}，未判定为可用。"
        except (httpx.HTTPError, ValueError):
            status = "error"
            message = "无法读取 MiMo 模型列表，请检查网络和 Endpoint。"
    else:
        message = f"凭据已从{credential_store_name()}成功读取；真实鉴权将在该厂商适配器接入后启用。"

    with db() as connection:
        connection.execute("UPDATE provider_accounts SET status=?,verification_message=?,last_verified_at=?,updated_at=? WHERE id=?", (status, message, verified_at, now(), account_id))
        updated = connection.execute("SELECT * FROM provider_accounts WHERE id=?", (account_id,)).fetchone()
    return account_response(updated)


@app.get("/api/models")
def list_models():
    return [{**m.__dict__, "gateway_id": m.gateway_id} for m in available_models()]


@app.get("/api/voices")
def list_voices():
    with db() as connection:
        rows = connection.execute("SELECT * FROM voices WHERE status='active' ORDER BY created_at DESC").fetchall()
    return [
        {
            **dict(row),
            "languages": json.loads(row["languages"]),
            "preview_url": f"/api/voices/{row['id']}/preview" if row["preview_asset"] else None,
        }
        for row in rows
    ]


def voice_already_imported(provider: str, model_id: str, provider_voice_id: str) -> bool:
    with db() as connection:
        if provider == "minimax":
            row = connection.execute(
                "SELECT 1 FROM voices WHERE provider=? AND provider_voice_id=? AND status='active'",
                (provider, provider_voice_id),
            ).fetchone()
        else:
            row = connection.execute(
                "SELECT 1 FROM voices WHERE provider=? AND model_id=? AND provider_voice_id=? AND status='active'",
                (provider, model_id, provider_voice_id),
            ).fetchone()
    return row is not None


@app.get("/api/voices/cloud/{provider}")
async def list_cloud_voices(provider: str):
    if provider not in {"dashscope", "minimax", "volcengine"}:
        raise HTTPException(400, "当前仅支持同步通义千问、火山引擎和 MiniMax 云端音色")
    try:
        adapter = provider_for(provider)
        if provider == "dashscope" and isinstance(adapter, QwenProvider):
            items = await adapter.list_cloned_voices()
        elif provider == "minimax" and isinstance(adapter, MiniMaxProvider):
            items = await adapter.list_cloned_voices()
        elif provider == "volcengine" and isinstance(adapter, VolcengineProvider):
            items = await adapter.list_cloned_voices()
        else:
            raise ProviderError("厂商适配器不可用", code="provider_not_configured", status=409)
    except ProviderError as exc:
        raise HTTPException(exc.status, detail={"message": str(exc), "code": exc.code}) from exc

    supported_models = {
        model.model_id: model
        for model in available_models()
        if model.provider == provider and model.supports_clone and "clone" in model.operations
    }
    result = []
    for item in items:
        model_id = item["model_id"]
        compatible = provider == "minimax" or model_id in supported_models
        result.append(
            {
                **item,
                "compatible": compatible,
                "compatibility_message": "" if compatible else "Voice Studio 尚未接入这个音色绑定的模型",
                "imported": voice_already_imported(provider, model_id, item["provider_voice_id"]),
            }
        )
    return {"provider": provider, "voices": result}


@app.post("/api/voices/import")
async def import_voice(body: ImportVoiceBody):
    model = resolve_model(f"{body.provider}/{body.model_id}")
    if not model:
        raise HTTPException(400, "所选模型不存在")
    if "clone" not in model.operations or not model.supports_clone:
        raise HTTPException(400, "请选择支持声音复刻的目标模型")
    if body.provider not in {"dashscope", "volcengine", "minimax"}:
        raise HTTPException(400, "当前仅支持导入千问、火山引擎或 MiniMax 的远端复刻音色 ID")
    provider_voice_id = body.provider_voice_id.strip()
    public_name = body.public_name.strip()
    display_name = body.display_name.strip()
    if not provider_voice_id or not public_name or not display_name:
        raise HTTPException(400, "音色 ID、显示名称和兼容别名不能为空")
    with db() as connection:
        if connection.execute("SELECT 1 FROM voices WHERE public_name=? AND status='active'", (public_name,)).fetchone():
            raise HTTPException(409, "兼容别名已存在，请换一个名称")
        if voice_already_imported(body.provider, body.model_id, provider_voice_id):
            raise HTTPException(409, "这个厂商音色 ID 已经导入")
    if body.provider == "volcengine":
        try:
            adapter = provider_for("volcengine")
            if not isinstance(adapter, VolcengineProvider):
                raise ProviderError("火山引擎适配器不可用", code="provider_not_configured", status=409)
            await adapter.validate_cloned_voice(provider_voice_id)
        except ProviderError as exc:
            raise HTTPException(exc.status, detail={"message": str(exc), "code": exc.code}) from exc
    voice_id = "voice_" + uuid.uuid4().hex[:10]
    with db() as connection:
        connection.execute("INSERT INTO voices (id,provider,model_id,provider_voice_id,display_name,public_name,voice_type,status,languages,created_at,preview_asset) VALUES (?,?,?,?,?,?,?,?,?,?,?)", (voice_id, body.provider, body.model_id, provider_voice_id, display_name, public_name, "imported", "active", json.dumps(body.languages, ensure_ascii=False), now(), None))
    return {"id": voice_id, "message": "已有厂商音色已导入，可以直接在合成工作台选择。", "voice": next(v for v in list_voices() if v["id"] == voice_id)}


@app.post("/api/voices/import/batch")
async def import_voices(body: ImportVoicesBody):
    normalized = []
    aliases: set[str] = set()
    remote_ids: set[tuple[str, str, str]] = set()
    for item in body.voices:
        model = resolve_model(f"{item.provider}/{item.model_id}")
        if not model or not model.supports_clone or "clone" not in model.operations:
            raise HTTPException(400, f"{item.provider_voice_id} 没有兼容的目标模型")
        if item.provider not in {"dashscope", "minimax", "volcengine"}:
            raise HTTPException(400, "云端批量导入当前仅支持通义千问、火山引擎和 MiniMax")
        provider_voice_id = item.provider_voice_id.strip()
        display_name = item.display_name.strip()
        public_name = item.public_name.strip()
        if not provider_voice_id or not display_name or not public_name:
            raise HTTPException(400, "音色 ID、显示名称和兼容别名不能为空")
        remote_key = (item.provider, "" if item.provider == "minimax" else item.model_id, provider_voice_id)
        if public_name in aliases:
            raise HTTPException(409, f"批量导入中存在重复兼容别名：{public_name}")
        if remote_key in remote_ids:
            raise HTTPException(409, f"批量导入中存在重复厂商音色：{provider_voice_id}")
        aliases.add(public_name)
        remote_ids.add(remote_key)
        normalized.append((item, provider_voice_id, display_name, public_name))

    with db() as connection:
        for item, provider_voice_id, _, public_name in normalized:
            if connection.execute(
                "SELECT 1 FROM voices WHERE public_name=? AND status='active'", (public_name,)
            ).fetchone():
                raise HTTPException(409, f"兼容别名已存在：{public_name}")
            if item.provider == "minimax":
                duplicate = connection.execute(
                    "SELECT 1 FROM voices WHERE provider=? AND provider_voice_id=? AND status='active'",
                    (item.provider, provider_voice_id),
                ).fetchone()
            else:
                duplicate = connection.execute(
                    "SELECT 1 FROM voices WHERE provider=? AND model_id=? AND provider_voice_id=? AND status='active'",
                    (item.provider, item.model_id, provider_voice_id),
                ).fetchone()
            if duplicate:
                raise HTTPException(409, f"厂商音色已经导入：{provider_voice_id}")

        created_ids = []
        for item, provider_voice_id, display_name, public_name in normalized:
            voice_id = "voice_" + uuid.uuid4().hex[:10]
            created_ids.append(voice_id)
            connection.execute(
                "INSERT INTO voices (id,provider,model_id,provider_voice_id,display_name,public_name,voice_type,status,languages,created_at,preview_asset) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (
                    voice_id,
                    item.provider,
                    item.model_id,
                    provider_voice_id,
                    display_name,
                    public_name,
                    "imported",
                    "active",
                    json.dumps(item.languages, ensure_ascii=False),
                    now(),
                    None,
                ),
            )
    voices_by_id = {item["id"]: item for item in list_voices()}
    created = [voices_by_id[voice_id] for voice_id in created_ids]
    return {
        "voices": created,
        "message": f"已从厂商云端导入 {len(created)} 个音色。",
    }


@app.delete("/api/voices/{voice_id}")
def remove_voice(voice_id: str):
    with db() as connection:
        voice = connection.execute("SELECT * FROM voices WHERE id=? AND status='active'", (voice_id,)).fetchone()
        if not voice:
            raise HTTPException(404, "音色不存在或已经移除")
        connection.execute("UPDATE voices SET status='deleted' WHERE id=?", (voice_id,))
    asset_path = voice["preview_asset"]
    if asset_path:
        asset = (ROOT / asset_path).resolve()
        try:
            asset.relative_to(AUDIO.resolve())
            asset.unlink(missing_ok=True)
        except ValueError:
            pass
    return {"deleted": True, "id": voice_id, "message": "已从 Voice Studio 音色库移除；厂商云端音色未删除。"}


@app.post("/api/voices/clone")
async def clone_voice(provider_name: str, model_id: str, display_name: str, public_name: str, audio: UploadFile = File(...)):
    model = resolve_model(f"{provider_name}/{model_id}")
    if not model:
        raise HTTPException(400, "所选克隆模型不存在")
    if "clone" not in model.operations or not model.supports_clone:
        raise HTTPException(400, "所选模型不支持声音克隆")
    if not audio.filename:
        raise HTTPException(400, "需要参考音频")
    raw = await audio.read()
    if not raw:
        raise HTTPException(400, "参考音频不能为空")
    max_size = 10 * 1024 * 1024 if provider_name in {"dashscope", "volcengine"} else 20 * 1024 * 1024
    if len(raw) > max_size:
        raise HTTPException(400, f"该模型的参考音频不能超过 {max_size // 1024 // 1024} MB")
    suffix = Path(audio.filename).suffix.lower()
    if provider_name == "dashscope" and suffix not in {".wav", ".mp3", ".m4a"}:
        raise HTTPException(400, "千问声音复刻仅支持 WAV、MP3 或 M4A")
    if provider_name == "volcengine" and suffix not in {".wav", ".mp3", ".ogg", ".m4a", ".aac", ".pcm"}:
        raise HTTPException(400, "火山引擎声音复刻仅支持 WAV、MP3、OGG、M4A、AAC 或 PCM")
    if provider_name == "minimax" and suffix not in {".wav", ".mp3", ".m4a"}:
        raise HTTPException(400, "MiniMax 声音复刻仅支持 WAV、MP3 或 M4A")
    with db() as connection:
        if connection.execute("SELECT 1 FROM voices WHERE public_name=?", (public_name,)).fetchone():
            raise HTTPException(409, "兼容别名已存在，请换一个名称")

    AUDIO.mkdir(parents=True, exist_ok=True)
    provider_voice_id = "reference_" + uuid.uuid4().hex[:8]
    asset_path: str | None = None
    clone_result: dict[str, Any] | None = None
    if provider_name == "dashscope":
        mime_types = {".wav": "audio/wav", ".mp3": "audio/mpeg", ".m4a": "audio/mp4"}
        try:
            adapter = provider_for("dashscope")
            if not isinstance(adapter, QwenProvider):
                raise ProviderError("千问适配器不可用", code="provider_not_configured", status=409)
            clone_result = await adapter.clone_voice(
                raw,
                mime_types[suffix],
                "vs_" + uuid.uuid4().hex[:12],
                model_id,
            )
            provider_voice_id = clone_result["voice_id"]
        except ProviderError as exc:
            raise HTTPException(exc.status, detail={"message": str(exc), "code": exc.code}) from exc
    elif provider_name == "volcengine":
        try:
            adapter = provider_for("volcengine")
            if not isinstance(adapter, VolcengineProvider):
                raise ProviderError("火山引擎适配器不可用", code="provider_not_configured", status=409)
            clone_result = await adapter.clone_voice(raw, suffix.lstrip("."))
            provider_voice_id = clone_result["voice_id"]
        except ProviderError as exc:
            raise HTTPException(exc.status, detail={"message": str(exc), "code": exc.code}) from exc
    elif provider_name == "minimax":
        try:
            adapter = provider_for("minimax")
            if not isinstance(adapter, MiniMaxProvider):
                raise ProviderError("MiniMax 适配器不可用", code="provider_not_configured", status=409)
            provider_voice_id = "vs_" + uuid.uuid4().hex[:12]
            clone_result = await adapter.clone_voice(raw, suffix.lstrip("."), provider_voice_id, model_id)
            provider_voice_id = clone_result["voice_id"]
        except ProviderError as exc:
            raise HTTPException(exc.status, detail={"message": str(exc), "code": exc.code}) from exc
    else:
        asset = AUDIO / f"reference_{uuid.uuid4().hex}_{suffix or '.wav'}"
        asset.write_bytes(raw)
        asset_path = str(asset.relative_to(ROOT))

    voice_id = "voice_" + uuid.uuid4().hex[:10]
    with db() as connection:
        connection.execute(
            "INSERT INTO voices (id,provider,model_id,provider_voice_id,display_name,public_name,voice_type,status,languages,created_at,preview_asset) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (voice_id, provider_name, model_id, provider_voice_id, display_name, public_name, "cloned", "active", json.dumps(model.languages, ensure_ascii=False), now(), asset_path),
        )
    if provider_name == "dashscope":
        message = "千问远端克隆音色已创建，可直接使用所选模型合成。"
        if clone_result and clone_result.get("fallback_mode"):
            message += " 厂商提示样本质量可能影响复刻效果。"
    elif provider_name == "volcengine":
        message = "火山引擎声音复刻 2.0 音色已创建，可直接使用所选模型合成。首次正式合成可能触发厂商音色槽位计费。"
    elif provider_name == "minimax":
        message = "MiniMax 远端克隆音色已创建，可直接使用所选模型合成。"
    elif model.mode == "provider":
        message = "参考音色已创建，可直接使用所选模型合成。"
    else:
        message = "已创建本地演示音色。"
    return {"id": voice_id, "message": message, "mode": model.mode, "voice": next(v for v in list_voices() if v["id"] == voice_id)}


@app.post("/api/voices/design")
async def design_voice(body: VoiceDesignBody):
    model = resolve_model(f"{body.provider}/{body.model_id}")
    if not model or "design" not in model.operations:
        raise HTTPException(400, "所选模型不支持音色设计")
    display_name = body.display_name.strip()
    public_name = body.public_name.strip()
    prompt = body.prompt.strip()
    preview_text = body.preview_text.strip()
    with db() as connection:
        if connection.execute("SELECT 1 FROM voices WHERE public_name=? AND status='active'", (public_name,)).fetchone():
            raise HTTPException(409, "兼容别名已存在，请换一个名称")

    voice_id = "voice_" + uuid.uuid4().hex[:10]
    provider_voice_id = ""
    preview_asset: str | None = None
    request_id = ""
    message = ""
    adapter = provider_for(body.provider)
    try:
        if body.provider == "dashscope" and isinstance(adapter, QwenProvider):
            result = await adapter.create_voice_design(
                prompt,
                preview_text,
                body.model_id,
                "vs_" + uuid.uuid4().hex[:12],
            )
            provider_voice_id = result["voice_id"]
            request_id = result.get("request_id", "")
            if result.get("preview_audio"):
                asset = AUDIO / f"design_{voice_id}.wav"
                asset.parent.mkdir(parents=True, exist_ok=True)
                asset.write_bytes(result["preview_audio"])
                preview_asset = storage_path(asset)
            message = "千问设计音色已创建并保存到音色库。"
        elif body.provider == "minimax" and isinstance(adapter, MiniMaxProvider):
            result = await adapter.create_voice_design(prompt, preview_text, "vs_" + uuid.uuid4().hex[:12])
            provider_voice_id = result["voice_id"]
            request_id = result.get("request_id", "")
            if result.get("preview_audio"):
                asset = AUDIO / f"design_{voice_id}.mp3"
                asset.parent.mkdir(parents=True, exist_ok=True)
                asset.write_bytes(result["preview_audio"])
                preview_asset = storage_path(asset)
            message = "MiniMax 设计音色已创建并保存到音色库。"
        elif body.provider == "mimo" and isinstance(adapter, MiMoProvider):
            asset = AUDIO / f"design_{voice_id}.wav"
            result = await adapter.synthesize(
                SynthesisRequest(model.gateway_id, "", preview_text, 1.0, "wav", prompt),
                asset,
            )
            request_id = result.get("provider_request_id", "")
            preview_asset = storage_path(asset)
            message = "MiMo 音色描述模板已保存，可在合成工作台重复使用。"
        else:
            raise ProviderError("音色设计适配器不可用", code="provider_not_configured", status=409)
    except HTTPException:
        raise
    except ProviderError as exc:
        raise HTTPException(exc.status, detail={"message": str(exc), "code": exc.code}) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(502, detail={"message": "无法下载厂商返回的试听音频", "code": "preview_download_failed"}) from exc

    if not preview_asset and provider_voice_id:
        asset = AUDIO / f"design_{voice_id}.wav"
        try:
            await adapter.synthesize(SynthesisRequest(model.gateway_id, provider_voice_id, preview_text, 1.0, "wav"), asset)
            preview_asset = storage_path(asset)
        except ProviderError:
            asset.unlink(missing_ok=True)
            message += " 音色已创建，但本地试听生成失败，可直接到合成工作台使用。"

    with db() as connection:
        connection.execute(
            """INSERT INTO voices
               (id,provider,model_id,provider_voice_id,display_name,public_name,voice_type,status,languages,created_at,preview_asset,design_prompt)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            (voice_id, body.provider, body.model_id, provider_voice_id, display_name, public_name, "design", "active", json.dumps(model.languages, ensure_ascii=False), now(), preview_asset, prompt),
        )
    voice = next(item for item in list_voices() if item["id"] == voice_id)
    return {"id": voice_id, "message": message, "request_id": request_id, "persistent": body.provider != "mimo", "voice": voice}


@app.get("/api/voices/{voice_id}/preview")
def voice_preview(voice_id: str):
    with db() as connection:
        voice = connection.execute("SELECT * FROM voices WHERE id=? AND status='active'", (voice_id,)).fetchone()
    if not voice or not voice["preview_asset"]:
        raise HTTPException(404, "该音色没有本地试听音频")
    asset = (ROOT / voice["preview_asset"]).resolve()
    try:
        asset.relative_to(AUDIO.resolve())
    except ValueError as exc:
        raise HTTPException(404, "试听音频路径无效") from exc
    if not asset.is_file():
        raise HTTPException(404, "试听音频已不存在")
    return FileResponse(asset, media_type=mimetypes.guess_type(asset.name)[0] or "application/octet-stream")


@app.get("/v1/models", dependencies=[Depends(require_gateway_key)])
def openai_models():
    items = [openai_model_item(m) for m in available_models()]
    items += [{"id": "tts-default", "object": "model", "created": int(time.time()), "owned_by": "voice-studio"}, {"id": "tts-fast", "object": "model", "created": int(time.time()), "owned_by": "voice-studio"}, {"id": "tts-hq", "object": "model", "created": int(time.time()), "owned_by": "voice-studio"}]
    return {"object": "list", "data": items}


@app.get("/v1/models/{model_id:path}", dependencies=[Depends(require_gateway_key)])
def openai_model(model_id: str):
    model = resolve_model(model_id)
    if not model:
        return error(f"模型 {model_id} 不存在", code="model_not_found", status_code=404)
    return openai_model_item(model, model_id)


@app.post("/v1/audio/speech", dependencies=[Depends(require_gateway_key)])
async def openai_speech(body: SynthesisBody):
    request_id = "req_" + uuid.uuid4().hex[:12]
    started = time.perf_counter()
    model_id = body.model.strip()
    voice_id = body.voice.strip()
    response_format = body.response_format.strip().lower()
    model = resolve_model(model_id)
    if not model:
        record_gateway_request(
            request_id=request_id, endpoint="speech", status="failed", status_code=400,
            model=model_id, voice=voice_id, error_code="model_not_found",
            total_latency_ms=int((time.perf_counter() - started) * 1000), input_chars=len(body.input),
            response_format=response_format,
        )
        return error(f"模型 {model_id} 不存在", code="model_not_found")
    if "synthesis" not in model.operations:
        record_gateway_request(
            request_id=request_id, endpoint="speech", status="failed", status_code=400,
            provider=model.provider, model=model.gateway_id, voice=voice_id,
            error_code="unsupported_model_operation", total_latency_ms=int((time.perf_counter() - started) * 1000),
            input_chars=len(body.input), response_format=response_format,
        )
        return error(f"模型 {model_id} 不支持语音合成", code="unsupported_model_operation")
    resolved_model = model.gateway_id
    resolved_voice = resolve_voice(voice_id, model)
    if not resolved_voice:
        record_gateway_request(
            request_id=request_id, endpoint="speech", status="failed", status_code=400,
            provider=model.provider, model=resolved_model, voice=voice_id, error_code="invalid_voice_scope",
            total_latency_ms=int((time.perf_counter() - started) * 1000), input_chars=len(body.input),
            response_format=response_format,
        )
        return error(f"音色 {voice_id} 与模型 {model_id} 不兼容", code="invalid_voice_scope")
    if response_format not in {"wav", "mp3", "opus", "aac", "flac", "pcm"}:
        record_gateway_request(
            request_id=request_id, endpoint="speech", status="failed", status_code=400,
            provider=model.provider, model=resolved_model, voice=voice_id, error_code="invalid_response_format",
            total_latency_ms=int((time.perf_counter() - started) * 1000), input_chars=len(body.input),
            response_format=response_format,
        )
        return error("response_format 仅支持 wav、mp3、opus、aac、flac、pcm", code="invalid_response_format")
    job_id = "job_" + uuid.uuid4().hex[:12]
    wav_path = AUDIO / f"{job_id}.wav"
    design_instructions = body.instructions or (resolved_voice["design_prompt"] if "design" in model.operations else None)
    try:
        adapter = demo_provider if model.mode == "demo" else provider_for(model.provider)
        provider_voice = voice_payload(model, resolved_voice, voice_id)
        result = await adapter.synthesize(SynthesisRequest(resolved_model, provider_voice, body.input, body.speed, "wav", design_instructions), wav_path)
        wav_info = audio_metadata(wav_path)
        output_path, media_type = convert_audio(wav_path, response_format)
    except ProviderError as exc:
        elapsed = int((time.perf_counter() - started) * 1000)
        record_gateway_request(
            request_id=request_id, endpoint="speech", status="failed", status_code=exc.status,
            provider=model.provider, model=resolved_model, voice=voice_id, error_code=exc.code,
            total_latency_ms=elapsed, input_chars=len(body.input), response_format=response_format,
        )
        return JSONResponse(
            status_code=exc.status,
            content={"error": {"message": str(exc), "type": "provider_error", "code": exc.code}},
        )
    elapsed = int((time.perf_counter() - started) * 1000)
    output_size = output_path.stat().st_size
    with db() as connection:
        connection.execute(
            "INSERT INTO jobs (id,model,voice,input_chars,status,duration_ms,audio_path,created_at,source,demo,input_text) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (job_id, resolved_model, voice_id, len(body.input), "completed", result["duration_ms"], storage_path(output_path), now(), "openai", int(result.get("demo", True)), body.input),
        )
    record_gateway_request(
        request_id=request_id, endpoint="speech", status="completed", status_code=200,
        provider=model.provider, model=resolved_model, voice=voice_id, total_latency_ms=elapsed,
        audio_bytes=output_size, input_chars=len(body.input), response_format=response_format,
    )
    headers = {
        "X-Voice-Studio-Job": job_id,
        "X-Voice-Studio-Latency-Ms": str(elapsed),
        "X-Voice-Studio-Mode": "demo" if result.get("demo") else "provider",
        "X-Voice-Studio-Response-Format": response_format,
    }
    if response_format == "pcm":
        headers.update(
            {
                "X-Voice-Studio-PCM-Encoding": "s16le",
                "X-Voice-Studio-PCM-Sample-Rate": str(wav_info.get("sample_rate", "unknown")),
                "X-Voice-Studio-PCM-Channels": str(wav_info.get("channels", "unknown")),
                "X-Voice-Studio-PCM-Bit-Depth": "16",
            }
        )
    return FileResponse(output_path, media_type=media_type, filename=output_path.name, headers=headers)


def _sse(event: str, payload: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(payload, ensure_ascii=False, separators=(',', ':'))}\n\n"


async def _stream_speech_events(
    body: StreamingSynthesisBody,
    model,
    resolved_voice: sqlite3.Row,
    adapter,
    job_id: str,
    response_format: str,
) -> AsyncIterator[str]:
    """Yield a stable SSE envelope around gateway audio chunks.

    Native MP3 adapters are forwarded as provider data arrives. Other formats
    are synthesized and converted first, then emitted in bounded chunks without
    changing the client-facing event contract.
    """
    wav_path = AUDIO / f"{job_id}.wav"
    request_id = "req_" + job_id.removeprefix("job_")
    started = time.perf_counter()
    output_path: Path | None = None
    total_bytes = 0
    chunk_index = 0
    first_chunk_latency_ms: int | None = None
    completed = False
    can_native_stream = False
    use_native_stream = False
    native_format = "mp3"
    try:
        provider_voice = voice_payload(model, resolved_voice, body.voice.strip())
        design_instructions = body.instructions or (resolved_voice["design_prompt"] if "design" in model.operations else None)
        synthesis_request = SynthesisRequest(model.gateway_id, provider_voice, body.input, body.speed, "wav", design_instructions)
        native_stream = getattr(adapter, "stream_synthesize", None)
        native_support = getattr(adapter, "supports_native_streaming", None)
        native_format_fn = getattr(adapter, "native_stream_format", None)
        can_native_stream = callable(native_stream) and (
            not callable(native_support) or native_support(model.gateway_id)
        )
        if callable(native_format_fn):
            native_format = str(native_format_fn(model.gateway_id)).strip().lower() or "mp3"
        use_native_stream = can_native_stream and response_format == native_format
        if use_native_stream:
            output_path = AUDIO / f"{job_id}.{native_format}"
            output_path.parent.mkdir(parents=True, exist_ok=True)
            native_result: dict[str, Any] = {}
            with output_path.open("wb") as output:
                async for item in native_stream(
                    SynthesisRequest(model.gateway_id, provider_voice, body.input, body.speed, native_format, design_instructions)
                ):
                    if item.get("audio"):
                        audio = item["audio"]
                        if first_chunk_latency_ms is None:
                            first_chunk_latency_ms = int((time.perf_counter() - started) * 1000)
                        output.write(audio)
                        total_bytes += len(audio)
                        for offset in range(0, len(audio), body.chunk_size):
                            chunk = audio[offset : offset + body.chunk_size]
                            yield _sse(
                                "audio",
                                {
                                    "type": "audio.chunk",
                                    "index": chunk_index,
                                    "audio": base64.b64encode(chunk).decode("ascii"),
                                    "format": native_format,
                                    "native": True,
                                },
                            )
                            chunk_index += 1
                    if item.get("done"):
                        native_result = item
            if total_bytes <= 0:
                raise ProviderError("流式适配器没有返回音频数据", code="invalid_provider_response")
            elapsed = int((time.perf_counter() - started) * 1000)
            with db() as connection:
                connection.execute(
                    "INSERT INTO jobs (id,model,voice,input_chars,status,duration_ms,audio_path,created_at,source,demo,input_text) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                    (job_id, model.gateway_id, body.voice.strip(), len(body.input), "completed", int(native_result.get("duration_ms") or 0), storage_path(output_path), now(), "openai-stream", 0, body.input),
                )
            completed = True
            record_gateway_request(
                request_id=request_id, endpoint="speech/stream", status="completed", status_code=200,
                provider=model.provider, model=model.gateway_id, voice=body.voice.strip(),
                first_chunk_latency_ms=first_chunk_latency_ms, total_latency_ms=elapsed,
                chunk_count=chunk_index, audio_bytes=total_bytes, input_chars=len(body.input),
                response_format=native_format, native_streaming=True,
            )
            done_pcm = {}
            if native_format == "pcm":
                done_pcm = {
                    "pcm": {
                        "encoding": "s16le",
                        "sample_rate": native_result.get("sample_rate", 24000),
                        "channels": native_result.get("channels", 1),
                        "bit_depth": native_result.get("bit_depth", 16),
                    }
                }
            yield _sse(
                "done",
                {
                    "type": "audio.done",
                    "job_id": job_id,
                    "model": model.gateway_id,
                    "voice": body.voice.strip(),
                    "format": native_format,
                    "bytes": total_bytes,
                    "chunks": chunk_index,
                    "first_chunk_latency_ms": first_chunk_latency_ms,
                    "duration_ms": int(native_result.get("duration_ms") or 0),
                    "latency_ms": elapsed,
                    "mode": "provider",
                    "native_streaming": True,
                    "provider_request_id": native_result.get("provider_request_id", ""),
                    **done_pcm,
                },
            )
            return
        result = await adapter.synthesize(
            synthesis_request,
            wav_path,
        )
        wav_info = audio_metadata(wav_path)
        output_path, _ = convert_audio(wav_path, response_format)
        with output_path.open("rb") as stream:
            while True:
                chunk = stream.read(body.chunk_size)
                if not chunk:
                    break
                if first_chunk_latency_ms is None:
                    first_chunk_latency_ms = int((time.perf_counter() - started) * 1000)
                total_bytes += len(chunk)
                yield _sse(
                    "audio",
                    {
                        "type": "audio.chunk",
                        "index": chunk_index,
                        "audio": base64.b64encode(chunk).decode("ascii"),
                        "format": response_format,
                    },
                )
                chunk_index += 1

        elapsed = int((time.perf_counter() - started) * 1000)
        with db() as connection:
            connection.execute(
                "INSERT INTO jobs (id,model,voice,input_chars,status,duration_ms,audio_path,created_at,source,demo,input_text) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (job_id, model.gateway_id, body.voice.strip(), len(body.input), "completed", result["duration_ms"], storage_path(output_path), now(), "openai-stream", int(result.get("demo", True)), body.input),
            )
        done: dict[str, Any] = {
            "type": "audio.done",
            "job_id": job_id,
            "model": model.gateway_id,
            "voice": body.voice.strip(),
            "format": response_format,
            "bytes": total_bytes,
            "chunks": chunk_index,
            "first_chunk_latency_ms": first_chunk_latency_ms,
            "duration_ms": result.get("duration_ms", 0),
            "latency_ms": elapsed,
            "mode": "demo" if result.get("demo") else "provider",
            "native_streaming": False,
        }
        if response_format == "pcm":
            done["pcm"] = {
                "encoding": "s16le",
                "sample_rate": wav_info.get("sample_rate"),
                "channels": wav_info.get("channels"),
                "bit_depth": 16,
            }
        completed = True
        record_gateway_request(
            request_id=request_id, endpoint="speech/stream", status="completed", status_code=200,
            provider=model.provider, model=model.gateway_id, voice=body.voice.strip(),
            first_chunk_latency_ms=first_chunk_latency_ms, total_latency_ms=elapsed,
            chunk_count=chunk_index, audio_bytes=total_bytes, input_chars=len(body.input),
            response_format=response_format, native_streaming=False,
        )
        yield _sse("done", done)
    except ProviderError as exc:
        if not completed:
            record_gateway_request(
                request_id=request_id, endpoint="speech/stream", status="failed", status_code=exc.status,
                provider=model.provider, model=model.gateway_id, voice=body.voice.strip(), error_code=exc.code,
                first_chunk_latency_ms=first_chunk_latency_ms, total_latency_ms=int((time.perf_counter() - started) * 1000),
                chunk_count=chunk_index, audio_bytes=total_bytes, input_chars=len(body.input),
                response_format=response_format,
                native_streaming=use_native_stream,
            )
        yield _sse("error", {"type": "error", "error": {"message": str(exc), "type": "provider_error", "code": exc.code}})
    except asyncio.CancelledError:
        if not completed:
            record_gateway_request(
                request_id=request_id, endpoint="speech/stream", status="cancelled", status_code=499,
                provider=model.provider, model=model.gateway_id, voice=body.voice.strip(), error_code="client_cancelled",
                first_chunk_latency_ms=first_chunk_latency_ms, total_latency_ms=int((time.perf_counter() - started) * 1000),
                chunk_count=chunk_index, audio_bytes=total_bytes, input_chars=len(body.input),
                response_format=response_format,
                native_streaming=use_native_stream,
            )
        raise
    except Exception as exc:
        if not completed:
            record_gateway_request(
                request_id=request_id, endpoint="speech/stream", status="failed", status_code=500,
                provider=model.provider, model=model.gateway_id, voice=body.voice.strip(), error_code="stream_failed",
                first_chunk_latency_ms=first_chunk_latency_ms, total_latency_ms=int((time.perf_counter() - started) * 1000),
                chunk_count=chunk_index, audio_bytes=total_bytes, input_chars=len(body.input),
                response_format=response_format,
                native_streaming=use_native_stream,
            )
        yield _sse("error", {"type": "error", "error": {"message": str(exc) or "流式音频生成失败", "type": "gateway_error", "code": "stream_failed"}})
    finally:
        if not completed:
            if output_path is not None:
                output_path.unlink(missing_ok=True)
            wav_path.unlink(missing_ok=True)


@app.post("/v1/audio/speech/stream", dependencies=[Depends(require_gateway_key)])
async def openai_speech_stream(body: StreamingSynthesisBody):
    started = time.perf_counter()
    request_id = "req_" + uuid.uuid4().hex[:12]
    model_id = body.model.strip()
    voice_id = body.voice.strip()
    response_format = body.response_format.strip().lower()
    model = resolve_model(model_id)
    if not model:
        record_gateway_request(
            request_id=request_id, endpoint="speech/stream", status="failed", status_code=400,
            model=model_id, voice=voice_id, error_code="model_not_found",
            total_latency_ms=int((time.perf_counter() - started) * 1000), input_chars=len(body.input),
            response_format=response_format,
        )
        return error(f"模型 {model_id} 不存在", code="model_not_found")
    if "synthesis" not in model.operations:
        record_gateway_request(
            request_id=request_id, endpoint="speech/stream", status="failed", status_code=400,
            provider=model.provider, model=model.gateway_id, voice=voice_id,
            error_code="unsupported_model_operation", total_latency_ms=int((time.perf_counter() - started) * 1000),
            input_chars=len(body.input), response_format=response_format,
        )
        return error(f"模型 {model_id} 不支持语音合成", code="unsupported_model_operation")
    if response_format not in {"wav", "mp3", "opus", "aac", "flac", "pcm"}:
        record_gateway_request(
            request_id=request_id, endpoint="speech/stream", status="failed", status_code=400,
            provider=model.provider, model=model.gateway_id, voice=voice_id,
            error_code="invalid_response_format", total_latency_ms=int((time.perf_counter() - started) * 1000),
            input_chars=len(body.input), response_format=response_format,
        )
        return error("response_format 仅支持 wav、mp3、opus、aac、flac、pcm", code="invalid_response_format")
    resolved_voice = resolve_voice(voice_id, model)
    if not resolved_voice:
        record_gateway_request(
            request_id=request_id, endpoint="speech/stream", status="failed", status_code=400,
            provider=model.provider, model=model.gateway_id, voice=voice_id,
            error_code="invalid_voice_scope", total_latency_ms=int((time.perf_counter() - started) * 1000),
            input_chars=len(body.input), response_format=response_format,
        )
        return error(f"音色 {voice_id} 与模型 {model_id} 不兼容", code="invalid_voice_scope")
    try:
        adapter = demo_provider if model.mode == "demo" else provider_for(model.provider)
    except ProviderError as exc:
        record_gateway_request(
            request_id=request_id, endpoint="speech/stream", status="failed", status_code=exc.status,
            provider=model.provider, model=model.gateway_id, voice=voice_id, error_code=exc.code,
            total_latency_ms=int((time.perf_counter() - started) * 1000), input_chars=len(body.input),
            response_format=response_format,
        )
        return JSONResponse(status_code=exc.status, content={"error": {"message": str(exc), "type": "provider_error", "code": exc.code}})
    job_id = "job_" + uuid.uuid4().hex[:12]
    return StreamingResponse(
        _stream_speech_events(body, model, resolved_voice, adapter, job_id, response_format),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Voice-Studio-Job": job_id,
            "X-Voice-Studio-Stream": "sse",
            "X-Voice-Studio-Chunk-Encoding": "base64",
        },
    )


def _job_response(row: sqlite3.Row) -> dict[str, Any]:
    item = dict(row)
    item["input_text"] = item.get("input_text") or ""
    item["created_date"] = datetime.fromisoformat(item["created_at"]).astimezone().date().isoformat()
    item["audio_available"] = False
    audio_path = item.get("audio_path")
    if audio_path:
        try:
            path = (ROOT / audio_path).resolve()
            path.relative_to(AUDIO.resolve())
            item["audio_available"] = path.is_file()
        except (OSError, ValueError):
            pass
    item["audio_url"] = f"/api/jobs/{item['id']}/audio" if item["audio_available"] else None
    item["text_url"] = f"/api/jobs/{item['id']}/text" if item["input_text"] else None
    return item


def _job_audio_path(row: sqlite3.Row) -> Path:
    audio_path = row["audio_path"]
    if not audio_path:
        raise HTTPException(404, "该任务没有保存音频文件")
    path = (ROOT / audio_path).resolve()
    try:
        path.relative_to(AUDIO.resolve())
    except ValueError as exc:
        raise HTTPException(404, "任务音频路径无效") from exc
    if not path.is_file():
        raise HTTPException(404, "该任务的音频文件已不存在")
    return path


def _job_rows_for_batch(body: JobBatchBody) -> list[sqlite3.Row]:
    job_ids = list(dict.fromkeys(item.strip() for item in body.job_ids if item.strip()))
    if not job_ids and not body.date:
        raise HTTPException(400, "请至少选择一个任务或指定日期")
    with db() as connection:
        if job_ids:
            placeholders = ",".join("?" for _ in job_ids)
            rows = connection.execute(
                f"SELECT * FROM jobs WHERE id IN ({placeholders}) ORDER BY created_at DESC",
                job_ids,
            ).fetchall()
        else:
            rows = connection.execute(
                "SELECT * FROM jobs WHERE date(created_at, 'localtime')=? ORDER BY created_at DESC",
                (body.date,),
            ).fetchall()
    if not rows:
        raise HTTPException(404, "没有找到可处理的任务")
    return rows


def _safe_existing_audio_path(row: sqlite3.Row) -> Path | None:
    audio_path = row["audio_path"]
    if not audio_path:
        return None
    try:
        path = (ROOT / audio_path).resolve()
        path.relative_to(AUDIO.resolve())
    except (OSError, ValueError):
        return None
    return path if path.is_file() else None


def _delete_job_rows(rows: list[sqlite3.Row]) -> tuple[int, int]:
    audio_paths = {path for row in rows if (path := _safe_existing_audio_path(row)) is not None}
    with db() as connection:
        connection.executemany("DELETE FROM jobs WHERE id=?", [(row["id"],) for row in rows])
    deleted_bytes = 0
    for path in audio_paths:
        try:
            deleted_bytes += path.stat().st_size
            path.unlink(missing_ok=True)
        except OSError:
            pass
    return len(rows), deleted_bytes


@app.get("/api/jobs")
def list_jobs(date: str | None = None, limit: int = 100):
    if date:
        try:
            datetime.strptime(date, "%Y-%m-%d")
        except ValueError as exc:
            raise HTTPException(400, "date 必须使用 YYYY-MM-DD 格式") from exc
    limit = max(1, min(limit, 500))
    with db() as connection:
        if date:
            rows = connection.execute(
                "SELECT * FROM jobs WHERE date(created_at, 'localtime')=? ORDER BY created_at DESC LIMIT ?",
                (date, limit),
            ).fetchall()
        else:
            rows = connection.execute("SELECT * FROM jobs ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
    return [_job_response(row) for row in rows]


@app.get("/api/jobs/{job_id}/audio")
def download_job_audio(job_id: str):
    with db() as connection:
        row = connection.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
    if not row:
        raise HTTPException(404, "任务不存在")
    path = _job_audio_path(row)
    media_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    return FileResponse(path, media_type=media_type, filename=f"voice-studio-{job_id}{path.suffix}")


@app.get("/api/jobs/{job_id}/text")
def download_job_text(job_id: str):
    with db() as connection:
        row = connection.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
    if not row:
        raise HTTPException(404, "任务不存在")
    text = row["input_text"] or ""
    if not text:
        raise HTTPException(404, "该任务是历史旧记录，未保存原始文字")
    return Response(
        content=text,
        media_type="text/plain",
        headers={"Content-Disposition": f'attachment; filename="voice-studio-{job_id}.txt"'},
    )


@app.post("/api/jobs/export")
def export_jobs(body: JobBatchBody):
    rows = _job_rows_for_batch(body)
    total_audio_bytes = sum(path.stat().st_size for row in rows if (path := _safe_existing_audio_path(row)) is not None)
    if total_audio_bytes > 512 * 1024 * 1024:
        raise HTTPException(413, "所选音频超过 512 MB，请分批导出")
    archive_dir = DATA / "archives"
    archive_dir.mkdir(parents=True, exist_ok=True)
    archive_fd, archive_name = tempfile.mkstemp(prefix="jobs-", suffix=".zip", dir=archive_dir)
    os.close(archive_fd)
    archive_path = Path(archive_name)
    manifest: list[dict[str, Any]] = []
    try:
        with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
            for row in rows:
                job_id = row["id"]
                text = row["input_text"] or ""
                audio_path = _safe_existing_audio_path(row)
                item = {
                    "id": job_id,
                    "model": row["model"],
                    "voice": row["voice"],
                    "status": row["status"],
                    "created_at": row["created_at"],
                    "text_file": f"text/{job_id}.txt" if text else None,
                    "audio_file": f"audio/{job_id}{audio_path.suffix}" if audio_path else None,
                }
                manifest.append(item)
                if text:
                    archive.writestr(f"text/{job_id}.txt", text)
                if audio_path:
                    archive.write(audio_path, f"audio/{job_id}{audio_path.suffix}")
            archive.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
    except Exception:
        archive_path.unlink(missing_ok=True)
        raise
    return FileResponse(
        archive_path,
        media_type="application/zip",
        filename="voice-studio-jobs.zip",
        background=BackgroundTask(archive_path.unlink, missing_ok=True),
    )


@app.post("/api/jobs/delete")
def delete_jobs(body: JobBatchBody):
    rows = _job_rows_for_batch(body)
    deleted_count, deleted_bytes = _delete_job_rows(rows)
    return {"deleted": deleted_count, "freed_bytes": deleted_bytes, "message": f"已删除 {deleted_count} 条任务记录"}


@app.delete("/api/jobs/{job_id}")
def delete_job(job_id: str):
    rows = _job_rows_for_batch(JobBatchBody(job_ids=[job_id]))
    deleted_count, deleted_bytes = _delete_job_rows(rows)
    return {"deleted": deleted_count, "freed_bytes": deleted_bytes, "message": "任务记录与对应音频已删除"}


@app.get("/api/jobs/storage")
def job_storage():
    with db() as connection:
        usage = storage_snapshot(connection, ROOT, AUDIO)["usage"]
    return {
        "job_count": usage["job_count"],
        "audio_count": usage["audio_count"],
        "audio_bytes": usage["audio_bytes"],
        "audio_megabytes": round(usage["audio_bytes"] / 1024 / 1024, 2),
        "missing_audio_count": usage["missing_audio_count"],
    }


@app.get("/api/storage")
def get_storage_status():
    with db() as connection:
        return storage_snapshot(connection, ROOT, AUDIO)


@app.put("/api/storage/policy")
def update_storage_policy(body: StoragePolicyBody):
    with db() as connection:
        write_policy(connection, body.model_dump())
        return storage_snapshot(connection, ROOT, AUDIO)


@app.post("/api/storage/cleanup/preview")
def preview_storage_cleanup():
    with db() as connection:
        plan = build_cleanup_plan(connection, ROOT, AUDIO, read_policy(connection))
        return cleanup_preview(plan)


@app.post("/api/storage/cleanup")
def clean_storage_now():
    with db() as connection:
        result = execute_cleanup(
            connection,
            ROOT,
            AUDIO,
            trigger="manual",
            run_id="cleanup_" + uuid.uuid4().hex[:12],
        )
        return {"result": result, "storage": storage_snapshot(connection, ROOT, AUDIO)}


@app.post("/api/storage/open-directory")
def open_storage_directory():
    AUDIO.mkdir(parents=True, exist_ok=True)
    path = AUDIO.resolve()
    try:
        system = platform.system()
        if system == "Windows":
            os.startfile(str(path))  # type: ignore[attr-defined]
        elif system == "Darwin":
            subprocess.Popen(["open", str(path)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        elif system == "Linux":
            # A server or SSH session may have no desktop session. Return the
            # path instead of failing when no graphical session is available.
            if not (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")):
                return {"opened": False, "path": str(path), "message": "当前 Linux 会话没有图形桌面，请手动打开该路径。"}
            subprocess.Popen(["xdg-open", str(path)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        else:
            return {"opened": False, "path": str(path), "message": "当前系统没有可用的目录打开器，请手动打开该路径。"}
    except OSError as exc:
        return {"opened": False, "path": str(path), "message": f"无法自动打开目录，请手动打开：{exc}"}
    return {"opened": True, "path": str(path), "message": "已请求系统文件管理器打开目录。"}


@app.get("/api/gateway/stats")
def gateway_stats(window: str = "7d", provider: str = ""):
    windows = {"24h": timedelta(hours=24), "7d": timedelta(days=7), "30d": timedelta(days=30), "all": None}
    if window not in windows:
        raise HTTPException(status_code=400, detail={"message": "window 仅支持 24h、7d、30d、all", "code": "invalid_window"})
    cutoff = None if windows[window] is None else (datetime.now(timezone.utc) - windows[window]).isoformat()
    clauses = []
    params: list[str] = []
    if cutoff:
        clauses.append("created_at >= ?")
        params.append(cutoff)
    if provider:
        clauses.append("provider = ?")
        params.append(provider)
    where = " WHERE " + " AND ".join(clauses) if clauses else ""
    with db() as connection:
        rows = connection.execute(f"SELECT * FROM gateway_requests{where} ORDER BY created_at DESC", params).fetchall()

    def bucket(items: list[sqlite3.Row], key: str) -> list[dict[str, Any]]:
        grouped: dict[str, list[sqlite3.Row]] = {}
        for row in items:
            grouped.setdefault(str(row[key] or "unknown"), []).append(row)
        result = []
        for name, group in sorted(grouped.items(), key=lambda item: (-len(item[1]), item[0])):
            completed = sum(row["status"] == "completed" for row in group)
            result.append({
                "name": name,
                "requests": len(group),
                "completed": completed,
                "failed": sum(row["status"] == "failed" for row in group),
                "cancelled": sum(row["status"] == "cancelled" for row in group),
                "success_rate": round(completed / len(group) * 100, 1) if group else 0,
                "first_chunk_latency": latency_summary(group, "first_chunk_latency_ms"),
                "total_latency": latency_summary(group, "total_latency_ms"),
            })
        return result

    total = len(rows)
    completed = sum(row["status"] == "completed" for row in rows)
    errors: dict[str, dict[str, Any]] = {}
    for row in rows:
        if row["status"] != "failed":
            continue
        code = str(row["error_code"] or "unknown_error")
        item = errors.setdefault(code, {"code": code, "count": 0, "last_seen_at": row["created_at"]})
        item["count"] += 1
        item["last_seen_at"] = max(item["last_seen_at"], row["created_at"])
    return {
        "window": window,
        "provider": provider or None,
        "sample_count": total,
        "total_requests": total,
        "completed_requests": completed,
        "failed_requests": sum(row["status"] == "failed" for row in rows),
        "cancelled_requests": sum(row["status"] == "cancelled" for row in rows),
        "success_rate": round(completed / total * 100, 1) if total else 0,
        "first_chunk_latency": latency_summary(rows, "first_chunk_latency_ms"),
        "total_latency": latency_summary(rows, "total_latency_ms"),
        "by_provider": bucket(rows, "provider"),
        "by_model": bucket(rows, "model"),
        "errors": sorted(errors.values(), key=lambda item: (-item["count"], item["code"])),
    }


@app.get("/api/gateway")
def gateway_config():
    key = gateway_key()
    return {
        "enabled": True,
        "base_url": f"{LOCAL_BASE_URL}/v1",
        "key": key,
        "key_hint": key[:7] + "..." + key[-4:],
        "key_source": gateway_key_source(),
        "managed": not bool(os.getenv("VOICE_STUDIO_GATEWAY_KEY", "").strip()),
        "mode": "hybrid",
        "note": "通义千问、火山引擎、MiniMax 与 MiMo 已接入真实接口。",
    }


@app.post("/api/gateway/rotate")
def rotate_gateway_key():
    if os.getenv("VOICE_STUDIO_GATEWAY_KEY", "").strip():
        raise HTTPException(status_code=409, detail="当前由环境变量 VOICE_STUDIO_GATEWAY_KEY 管理网关 Key，不能在界面轮换")
    value = "vs_" + secrets.token_urlsafe(24)
    DATA.mkdir(parents=True, exist_ok=True)
    temp_path = GATEWAY_CONFIG_PATH.with_suffix(".tmp")
    temp_path.write_text(json.dumps({"key": value}, ensure_ascii=False, indent=2), encoding="utf-8")
    temp_path.replace(GATEWAY_CONFIG_PATH)
    return {"key": value, "key_hint": value[:7] + "..." + value[-4:], "key_source": "本地 gateway.json", "managed": True}


if FRONTEND_DIST.exists():
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets"), name="assets")

    @app.get("/{full_path:path}")
    async def spa(full_path: str):
        candidate = (FRONTEND_DIST / full_path).resolve()
        try:
            candidate.relative_to(FRONTEND_DIST.resolve())
        except ValueError as exc:
            raise HTTPException(404, "文件不存在") from exc
        if candidate.exists() and candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(FRONTEND_DIST / "index.html")
