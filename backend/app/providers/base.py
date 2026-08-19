from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True)
class ProviderModel:
    provider: str
    model_id: str
    display_name: str
    kind: str
    quality: str
    latency: str
    languages: list[str]
    supports_clone: bool
    mode: str = "demo"
    operations: list[str] = field(default_factory=lambda: ["synthesis"])

    @property
    def gateway_id(self) -> str:
        return f"{self.provider}/{self.model_id}"


@dataclass(frozen=True)
class SynthesisRequest:
    model: str
    voice: str
    text: str
    speed: float = 1.0
    format: str = "mp3"
    instructions: str | None = None


class SpeechProvider(Protocol):
    key: str

    def models(self) -> list[ProviderModel]: ...

    async def synthesize(self, request: SynthesisRequest, output: Path) -> dict: ...


class ProviderError(Exception):
    def __init__(self, message: str, code: str = "provider_error", status: int = 502):
        super().__init__(message)
        self.code = code
        self.status = status
