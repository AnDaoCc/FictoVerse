from __future__ import annotations

from typing import Protocol


class TTSProvider(Protocol):
    """TTS 后端统一接口。"""

    def synthesize(self, text: str, *, voice: str = "", rate: float = 1.0) -> bytes: ...

    def list_voices(self, *, locale_prefix: str = "") -> list[dict[str, str]]: ...

    def media_type(self) -> str: ...
