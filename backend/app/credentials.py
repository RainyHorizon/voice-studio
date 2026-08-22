import json
import os
import platform

import keyring


SERVICE_NAME = "VoiceStudio.ProviderAccount"
ENV_MODE = "env"
ENV_PROVIDER_KEYS = {
    "dashscope": "VOICE_STUDIO_DASHSCOPE_API_KEY",
    "volcengine": "VOICE_STUDIO_VOLCENGINE_API_KEY",
    "minimax": "VOICE_STUDIO_MINIMAX_API_KEY",
    "mimo": "VOICE_STUDIO_MIMO_API_KEY",
}


def environment_credentials_enabled() -> bool:
    return os.getenv("VOICE_STUDIO_CREDENTIALS_MODE", "").strip().lower() == ENV_MODE


def environment_provider_credentials(provider: str) -> dict[str, str]:
    if not environment_credentials_enabled():
        return {}
    values: dict[str, str] = {}
    api_key_name = ENV_PROVIDER_KEYS.get(provider)
    if api_key_name and os.getenv(api_key_name, "").strip():
        values["api_key"] = os.environ[api_key_name].strip()
    if provider == "volcengine":
        for field, env_name in {
            "openapi_access_key": "VOICE_STUDIO_VOLCENGINE_OPENAPI_ACCESS_KEY",
            "openapi_secret_key": "VOICE_STUDIO_VOLCENGINE_OPENAPI_SECRET_KEY",
        }.items():
            if os.getenv(env_name, "").strip():
                values[field] = os.environ[env_name].strip()
    return values


def environment_account_provider(account_id: str) -> str | None:
    if not account_id.startswith("env_"):
        return None
    provider = account_id[4:]
    return provider if provider in ENV_PROVIDER_KEYS else None


def credential_store_name() -> str:
    """Return a user-facing name without assuming a particular operating system."""
    system = platform.system()
    if system == "Windows":
        return "Windows Credential Manager"
    if system == "Darwin":
        return "macOS 钥匙串"
    if system == "Linux":
        return "Linux 系统密钥环"
    return "系统密钥环"


class CredentialStoreError(RuntimeError):
    pass


def save_api_key(account_id: str, api_key: str) -> None:
    save_provider_credentials(account_id, api_key=api_key)


def save_provider_credentials(account_id: str, **credentials: str) -> None:
    if environment_account_provider(account_id):
        raise CredentialStoreError("Docker 环境变量凭据由部署配置管理，不能在页面中修改")
    try:
        current = {}
        existing = keyring.get_password(SERVICE_NAME, account_id)
        if existing:
            try:
                current = json.loads(existing) or {}
            except (json.JSONDecodeError, TypeError):
                current = {}
        current.update({key: value for key, value in credentials.items() if value})
        keyring.set_password(SERVICE_NAME, account_id, json.dumps(current))
    except Exception as exc:
        raise CredentialStoreError(f"无法写入{credential_store_name()}") from exc


def load_api_key(account_id: str) -> str | None:
    return load_provider_credentials(account_id).get("api_key")


def load_provider_credentials(account_id: str) -> dict[str, str]:
    provider = environment_account_provider(account_id)
    if provider:
        return environment_provider_credentials(provider)
    try:
        value = keyring.get_password(SERVICE_NAME, account_id)
    except Exception as exc:
        raise CredentialStoreError(f"无法读取{credential_store_name()}") from exc
    if not value:
        return {}
    try:
        parsed = json.loads(value)
        return parsed if isinstance(parsed, dict) else {}
    except (json.JSONDecodeError, TypeError) as exc:
        raise CredentialStoreError(f"{credential_store_name()}中的凭据格式无效") from exc


def delete_api_key(account_id: str) -> None:
    if environment_account_provider(account_id):
        return
    try:
        if keyring.get_password(SERVICE_NAME, account_id) is not None:
            keyring.delete_password(SERVICE_NAME, account_id)
    except Exception as exc:
        raise CredentialStoreError(f"无法删除{credential_store_name()}凭据") from exc


def credential_store_status() -> dict[str, str | bool]:
    if environment_credentials_enabled():
        configured = sum(bool(environment_provider_credentials(provider).get("api_key")) for provider in ENV_PROVIDER_KEYS)
        return {
            "available": True,
            "backend": "EnvironmentCredentials",
            "message": f"Docker 环境变量凭据模式可用，已配置 {configured} 家厂商",
        }
    try:
        keyring.get_password(SERVICE_NAME, "__healthcheck__")
        backend = type(keyring.get_keyring()).__name__
        return {"available": True, "backend": backend, "message": f"{credential_store_name()}可用"}
    except Exception as exc:
        # Some keyring backends raise NoKeyringError/RuntimeError instead of KeyringError.
        return {"available": False, "backend": "", "message": f"无法访问{credential_store_name()}：{exc}"}
