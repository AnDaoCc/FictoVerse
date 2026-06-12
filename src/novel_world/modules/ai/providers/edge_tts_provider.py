from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path
from typing import Any

from novel_world.modules.ai.services.tts_voice_resolver import DEFAULT_EDGE_VOICE, strip_text_for_tts

_VOICE_CACHE: list[dict[str, str]] | None = None


def _run_async(coro) -> Any:
    try:
        return asyncio.run(coro)
    except RuntimeError:
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(coro)
        finally:
            loop.close()


class EdgeTTSProvider:
    """Edge TTS 后端（通过 edge-tts 可选依赖合成）。"""

    def __init__(self, *, voice: str = DEFAULT_EDGE_VOICE) -> None:
        self._voice = voice

    def media_type(self) -> str:
        return "audio/mpeg"

    def list_voices(self, *, locale_prefix: str = "") -> list[dict[str, str]]:
        global _VOICE_CACHE
        if _VOICE_CACHE is None:
            try:
                import edge_tts  # type: ignore

                async def _fetch() -> list[dict[str, Any]]:
                    raw = await edge_tts.list_voices()
                    return list(raw)

                voices = _run_async(_fetch())
                _VOICE_CACHE = [
                    {
                        "id": str(v.get("ShortName", "")),
                        "name": str(v.get("FriendlyName", v.get("ShortName", ""))),
                        "locale": str(v.get("Locale", "")),
                        "gender": str(v.get("Gender", "")),
                    }
                    for v in voices
                    if v.get("ShortName")
                ]
            except Exception:
                _VOICE_CACHE = [
                    {
                        "id": DEFAULT_EDGE_VOICE,
                        "name": DEFAULT_EDGE_VOICE,
                        "locale": "zh-CN",
                        "gender": "Female",
                    },
                    {
                        "id": "zh-CN-YunxiNeural",
                        "name": "zh-CN-YunxiNeural",
                        "locale": "zh-CN",
                        "gender": "Male",
                    },
                ]
        if locale_prefix:
            prefix = locale_prefix.lower()
            return [v for v in _VOICE_CACHE if v.get("locale", "").lower().startswith(prefix)]
        return list(_VOICE_CACHE)

    async def _synthesize_async(self, text: str, *, voice: str, rate: float) -> bytes:
        try:
            import edge_tts  # type: ignore
        except ImportError:
            return b""
        communicate = edge_tts.Communicate(text, voice=voice, rate=f"{int((rate - 1) * 100):+d}%")
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
            path = Path(tmp.name)
        await communicate.save(str(path))
        data = path.read_bytes()
        path.unlink(missing_ok=True)
        return data

    def synthesize(self, text: str, *, voice: str = "", rate: float = 1.0) -> bytes:
        cleaned = strip_text_for_tts(text)
        if not cleaned:
            return b""
        v = voice or self._voice
        return _run_async(self._synthesize_async(cleaned, voice=v, rate=rate))
