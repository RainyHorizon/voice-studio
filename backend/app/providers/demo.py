import math
import struct
import wave
from pathlib import Path

from .base import ProviderModel, SpeechProvider, SynthesisRequest


MODELS = [
    ProviderModel("demo", "local-demo", "本地演示音频", "tts", "诊断", "即时", ["zh-CN", "en-US"], False, operations=["synthesis"]),
]


class DemoProvider(SpeechProvider):
    key = "demo"

    def models(self) -> list[ProviderModel]:
        return MODELS

    async def synthesize(self, request: SynthesisRequest, output: Path) -> dict:
        """Generate a short, valid WAV for offline UI/API verification.

        Real provider adapters can replace this method without changing the gateway contract.
        """
        sample_rate = 24000
        duration = max(1.2, min(12.0, 0.045 * len(request.text) + 0.8))
        frames = int(sample_rate * duration)
        base = 205 + (sum(ord(c) for c in request.voice) % 100)
        output.parent.mkdir(parents=True, exist_ok=True)
        with wave.open(str(output), "wb") as stream:
            stream.setnchannels(1)
            stream.setsampwidth(2)
            stream.setframerate(sample_rate)
            for index in range(frames):
                t = index / sample_rate
                envelope = min(1.0, t * 8) * min(1.0, (duration - t) * 8)
                value = int(12000 * envelope * math.sin(2 * math.pi * base * t + 0.18 * math.sin(t * 8)))
                stream.writeframes(struct.pack("<h", value))
        return {"provider_request_id": f"demo_{output.stem}", "duration_ms": int(duration * 1000), "demo": True}
