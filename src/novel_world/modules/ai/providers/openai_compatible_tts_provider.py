from __future__ import annotations

import json
from typing import Any

import httpx

from novel_world.modules.ai.services.tts_voice_resolver import strip_text_for_tts

OPENAI_VOICES = [
    {"id": "alloy", "name": "Alloy", "locale": "en", "gender": ""},
    {"id": "echo", "name": "Echo", "locale": "en", "gender": ""},
    {"id": "fable", "name": "Fable", "locale": "en", "gender": ""},
    {"id": "onyx", "name": "Onyx", "locale": "en", "gender": ""},
    {"id": "nova", "name": "Nova", "locale": "en", "gender": ""},
    {"id": "shimmer", "name": "Shimmer", "locale": "en", "gender": ""},
]


def parse_voices_json(raw: str) -> list[dict[str, str]]:
    text = (raw or "").strip()
    if not text:
        return []
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return []
    items = data if isinstance(data, list) else data.get("voices") if isinstance(data, dict) else []
    if not isinstance(items, list):
        return []
    out: list[dict[str, str]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        vid = str(item.get("id") or item.get("voice") or "").strip()
        if not vid:
            continue
        out.append(
            {
                "id": vid,
                "name": str(item.get("name") or vid),
                "locale": str(item.get("locale") or ""),
                "gender": str(item.get("gender") or ""),
            }
        )
    return out


class OpenAICompatibleTTSProvider:
    """OpenAI 兼容 TTS：POST {base_url}/audio/speech"""

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str = "https://api.openai.com/v1",
        model: str = "tts-1",
        voice: str = "alloy",
        auth_style: str = "bearer",
        voices_json: str = "",
    ) -> None:
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._voice = voice
        self._auth_style = auth_style.lower()
        self._voices_json = voices_json

    def media_type(self) -> str:
        return "audio/mpeg"

    def _auth_headers(self) -> dict[str, str]:
        if self._auth_style == "api-key":
            return {"api-key": self._api_key}
        return {"Authorization": f"Bearer {self._api_key}"}

    def list_voices(self, *, locale_prefix: str = "") -> list[dict[str, str]]:
        custom = parse_voices_json(self._voices_json)
        voices = custom or list(OPENAI_VOICES)
        if locale_prefix:
            prefix = locale_prefix.lower()
            filtered = [v for v in voices if v.get("locale", "").lower().startswith(prefix)]
            return filtered or voices
        return voices

    def synthesize(self, text: str, *, voice: str = "", rate: float = 1.0) -> bytes:
        cleaned = strip_text_for_tts(text)
        if not cleaned:
            return b""
        with httpx.Client(timeout=120.0) as client:
            resp = client.post(
                f"{self._base_url}/audio/speech",
                headers=self._auth_headers(),
                json={
                    "model": self._model,
                    "input": cleaned,
                    "voice": voice or self._voice,
                    "speed": max(0.25, min(4.0, rate)),
                },
            )
            resp.raise_for_status()
            return resp.content


# 向后兼容旧名称
OpenAITTSProvider = OpenAICompatibleTTSProvider
