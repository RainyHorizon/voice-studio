from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True)
class ProviderModel:
    """Describe one provider model exposed by the local gateway.

    ``gateway_id`` is the stable ``provider/model`` identifier used by the
    OpenAI-compatible API. ``operations`` declares optional clone/design
    capabilities in addition to synthesis.
    """
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
    design_prompt_max: int | None = None
    design_preview_min: int | None = None
    design_preview_max: int | None = None

    @property
    def gateway_id(self) -> str:
        return f"{self.provider}/{self.model_id}"


@dataclass(frozen=True)
class SynthesisRequest:
    """Normalized synthesis request passed from the gateway to an adapter."""
    model: str
    voice: str
    text: str
    speed: float = 1.0
    format: str = "mp3"
    instructions: str | None = None


class SpeechProvider(Protocol):
    """Minimal adapter contract implemented by each speech provider."""
    key: str

    def models(self) -> list[ProviderModel]: ...

    async def synthesize(self, request: SynthesisRequest, output: Path) -> dict: ...


class ProviderError(Exception):
    """Provider failure normalized to a user-facing message and HTTP status."""

    def __init__(self, message: str, code: str = "provider_error", status: int = 502):
        super().__init__(message)
        self.code = code
        self.status = status
