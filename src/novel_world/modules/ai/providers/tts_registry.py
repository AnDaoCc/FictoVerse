from __future__ import annotations

from typing import Any

from novel_world.modules.ai.providers.custom_http_tts_provider import CustomHttpTTSProvider
from novel_world.modules.ai.providers.edge_tts_provider import EdgeTTSProvider
from novel_world.modules.ai.providers.openai_compatible_tts_provider import OpenAICompatibleTTSProvider
from novel_world.modules.ai.services.tts_voice_resolver import DEFAULT_EDGE_VOICE


def normalize_tts_backend(backend: str) -> str:
    name = str(backend or "edge").lower().strip()
    if name == "openai":
        return "openai_compatible"
    return name


def build_tts_provider(
    prefs: dict[str, Any],
    *,
    require_credentials: bool = True,
) -> EdgeTTSProvider | OpenAICompatibleTTSProvider | CustomHttpTTSProvider | None:
    backend = normalize_tts_backend(str(prefs.get("tts_backend") or "edge"))
    if backend == "openai_compatible":
        key = str(prefs.get("tts_openai_api_key") or "").strip()
        if not key and require_credentials:
            return None
        return OpenAICompatibleTTSProvider(
            api_key=key or "placeholder",
            base_url=str(prefs.get("tts_openai_base_url") or "https://api.openai.com/v1"),
            model=str(prefs.get("tts_openai_model") or "tts-1"),
            voice=str(prefs.get("tts_openai_voice") or "alloy"),
            auth_style=str(prefs.get("tts_openai_auth_style") or "bearer"),
            voices_json=str(prefs.get("tts_openai_voices_json") or ""),
        )
    if backend == "custom_http":
        cfg = prefs.get("tts_custom")
        if not isinstance(cfg, dict):
            cfg = {}
        if require_credentials and not str(cfg.get("url") or "").strip():
            return None
        return CustomHttpTTSProvider(cfg)
    if backend == "edge":
        return EdgeTTSProvider(voice=str(prefs.get("tts_voice") or DEFAULT_EDGE_VOICE))
    return None
