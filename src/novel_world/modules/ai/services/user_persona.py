from __future__ import annotations

from typing import Any

DEFAULT_PERSONA: dict[str, str] = {"name": "", "description": ""}
DISPLAY_FALLBACK = "你"

_GOD_MODE_PROMPTS = {
    "roleplay": "用户以上帝视角参与对话，无固定角色身份；不要强行给用户编造具体人设。",
    "group": "用户以上帝视角参与群聊，无固定角色身份；不要强行给用户编造具体人设。",
    "world": "用户以上帝视角参与，无固定角色身份；不要强行给用户编造具体人设。",
}


def normalize_persona(raw: dict[str, str] | None) -> dict[str, str]:
    if not raw or not isinstance(raw, dict):
        return dict(DEFAULT_PERSONA)
    return {
        "name": str(raw.get("name", "")).strip(),
        "description": str(raw.get("description", "")).strip(),
    }


def is_god_mode(persona: dict[str, str] | None) -> bool:
    p = normalize_persona(persona)
    return not p["name"] and not p["description"]


def display_name(persona: dict[str, str] | None, *, fallback: str = DISPLAY_FALLBACK) -> str:
    p = normalize_persona(persona)
    if is_god_mode(p):
        return fallback
    return p["name"] or fallback


def persona_from_world_settings(settings: dict[str, Any] | None) -> dict[str, str]:
    if not settings or not isinstance(settings, dict):
        return dict(DEFAULT_PERSONA)
    raw = settings.get("user_persona")
    if not isinstance(raw, dict):
        return dict(DEFAULT_PERSONA)
    return normalize_persona(raw)


def merge_session_persona(
    session_config: dict[str, Any] | None,
    world_settings: dict[str, Any] | None = None,
) -> dict[str, str]:
    cfg = session_config or {}
    if "user_persona" in cfg and isinstance(cfg.get("user_persona"), dict):
        return normalize_persona(cfg["user_persona"])
    return persona_from_world_settings(world_settings)


def format_persona_for_prompt(
    persona: dict[str, str] | None,
    *,
    mode: str = "roleplay",
) -> str:
    p = normalize_persona(persona)
    if is_god_mode(p):
        return _GOD_MODE_PROMPTS.get(mode, _GOD_MODE_PROMPTS["roleplay"])
    block = f"名称：{p['name']}"
    if p["description"]:
        block += f"\n描述：{p['description']}"
    return block


def format_user_transcript_line(
    persona: dict[str, str] | None,
    content: str,
    *,
    fallback: str = DISPLAY_FALLBACK,
) -> str:
    label = display_name(persona, fallback=fallback)
    if is_god_mode(persona):
        return f"我（用户，上帝视角）：{content.strip()}"
    return f"{label}（用户扮演）：{content.strip()}"


def store_persona(name: str, description: str) -> dict[str, str]:
    return normalize_persona({"name": name, "description": description})
