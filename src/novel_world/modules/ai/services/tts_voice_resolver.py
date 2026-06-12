"""TTS 音色解析：角色 metadata、酒馆 extensions、全局默认。"""

from __future__ import annotations

import re
from typing import Any

DEFAULT_EDGE_VOICE = "zh-CN-XiaoxiaoNeural"

_EXTENSION_VOICE_KEYS = (
    "tts_voice",
    "voice",
    "edge_tts_voice",
    "edgeTTSVoice",
    "talktome_voice",
)


def _strip_text(value: Any) -> str:
    return str(value or "").strip()


def extract_tts_voice_from_extensions(extensions: dict[str, Any] | None) -> str:
    if not isinstance(extensions, dict):
        return ""
    for key in _EXTENSION_VOICE_KEYS:
        voice = _strip_text(extensions.get(key))
        if voice:
            return voice
    return ""


def extract_tts_voice_from_character(character: Any) -> str:
    if character is None:
        return ""
    metadata = getattr(character, "metadata", None) or {}
    if isinstance(metadata, dict):
        voice = _strip_text(metadata.get("tts_voice"))
        if voice:
            return voice
        card = metadata.get("card")
        if isinstance(card, dict):
            data = card.get("data") if isinstance(card.get("data"), dict) else card
            if isinstance(data, dict):
                ext = data.get("extensions")
                if isinstance(ext, dict):
                    voice = extract_tts_voice_from_extensions(ext)
                    if voice:
                        return voice
    return ""


def resolve_voice_for_character(character: Any, *, global_default: str = "") -> str:
    voice = extract_tts_voice_from_character(character)
    if voice:
        return voice
    fallback = _strip_text(global_default)
    return fallback or DEFAULT_EDGE_VOICE


def resolve_voice_for_speaker(
    speaker: dict[str, str] | None,
    *,
    global_default: str = "",
    characters_by_id: dict[str, Any] | None = None,
) -> str:
    if not speaker:
        fallback = _strip_text(global_default)
        return fallback or DEFAULT_EDGE_VOICE
    voice = _strip_text(speaker.get("tts_voice"))
    if voice:
        return voice
    char_id = _strip_text(speaker.get("character_id"))
    if char_id and characters_by_id:
        character = characters_by_id.get(char_id)
        if character is not None:
            return resolve_voice_for_character(character, global_default=global_default)
    fallback = _strip_text(global_default)
    return fallback or DEFAULT_EDGE_VOICE


def strip_text_for_tts(text: str) -> str:
    """移除 Markdown/HTML，供 TTS 朗读。"""
    raw = (text or "").strip()
    if not raw:
        return ""
    raw = re.sub(r"```[\s\S]*?```", " ", raw)
    raw = re.sub(r"`([^`]+)`", r"\1", raw)
    raw = re.sub(r"!\[[^\]]*\]\([^)]+\)", " ", raw)
    raw = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", raw)
    raw = re.sub(r"<[^>]+>", " ", raw)
    raw = re.sub(r"[#*_~>|]", " ", raw)
    raw = re.sub(r"\s+", " ", raw).strip()
    return raw


def build_speaker_payload(
    character: Any,
    world_id: str,
    *,
    avatar_url: str = "",
    extra: dict[str, str] | None = None,
    global_default: str = "",
) -> dict[str, str]:
    payload: dict[str, str] = {
        "character_id": str(getattr(character, "id", "")),
        "world_id": world_id,
        "name": str(getattr(character, "name", "") or ""),
        "avatar_url": avatar_url,
        "tts_voice": resolve_voice_for_character(character, global_default=global_default),
    }
    if extra:
        payload.update({k: v for k, v in extra.items() if v})
    return payload
