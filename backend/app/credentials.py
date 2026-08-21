import json

import keyring
from keyring.errors import KeyringError


SERVICE_NAME = "VoiceStudio.ProviderAccount"


class CredentialStoreError(RuntimeError):
    pass


def save_api_key(account_id: str, api_key: str) -> None:
    save_provider_credentials(account_id, api_key=api_key)


def save_provider_credentials(account_id: str, **credentials: str) -> None:
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
    except KeyringError as exc:
        raise CredentialStoreError("无法写入 Windows Credential Manager") from exc


def load_api_key(account_id: str) -> str | None:
    return load_provider_credentials(account_id).get("api_key")


def load_provider_credentials(account_id: str) -> dict[str, str]:
    try:
        value = keyring.get_password(SERVICE_NAME, account_id)
    except KeyringError as exc:
        raise CredentialStoreError("无法读取 Windows Credential Manager") from exc
    if not value:
        return {}
    try:
        parsed = json.loads(value)
        return parsed if isinstance(parsed, dict) else {}
    except (json.JSONDecodeError, TypeError) as exc:
        raise CredentialStoreError("Windows Credential Manager 中的凭据格式无效") from exc


def delete_api_key(account_id: str) -> None:
    try:
        if keyring.get_password(SERVICE_NAME, account_id) is not None:
            keyring.delete_password(SERVICE_NAME, account_id)
    except KeyringError as exc:
        raise CredentialStoreError("无法删除 Windows Credential Manager 凭据") from exc


def credential_store_status() -> dict[str, str | bool]:
    try:
        keyring.get_password(SERVICE_NAME, "__healthcheck__")
        backend = type(keyring.get_keyring()).__name__
        return {"available": True, "backend": backend, "message": "Windows Credential Manager 可用"}
    except KeyringError as exc:
        return {"available": False, "backend": "", "message": f"无法访问 Windows Credential Manager：{exc}"}
