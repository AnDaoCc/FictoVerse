from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class GenerationConfig:
    temperature: float = 0.8
    top_p: float = 1.0
    max_tokens: int = 512
    repetition_penalty: float = 1.0
    stop: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> GenerationConfig:
        if not isinstance(data, dict):
            return cls()
        stop = data.get("stop") or []
        return cls(
            temperature=float(data.get("temperature", 0.8)),
            top_p=float(data.get("top_p", 1.0)),
            max_tokens=int(data.get("max_tokens", 512)),
            repetition_penalty=float(data.get("repetition_penalty", 1.0)),
            stop=[str(s) for s in stop] if isinstance(stop, list) else [],
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "temperature": self.temperature,
            "top_p": self.top_p,
            "max_tokens": self.max_tokens,
            "repetition_penalty": self.repetition_penalty,
            "stop": list(self.stop),
        }
