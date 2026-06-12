"""角色类型枚举：启动器、Web 世界详情、聊天侧栏统一使用。"""

from __future__ import annotations

ROLE_OPTIONS: tuple[tuple[str, str], ...] = (
    ("hero_male", "男主角"),
    ("hero_female", "女主角"),
    ("party_male", "主角团内的男"),
    ("party_female", "主角团中的女"),
    ("npc_important", "重要NPC"),
    ("npc_story", "剧情NPC"),
    ("npc_passerby", "路人NPC"),
)

_ROLE_LABELS: dict[str, str] = dict(ROLE_OPTIONS)

_LEGACY_MAP: dict[str, str] = {
    "主角": "hero_male",
    "女主角": "hero_female",
    "男主角": "hero_male",
    "配角": "npc_important",
    "player": "hero_male",
    "npc": "npc_passerby",
    "protagonist": "hero_male",
    "supporting": "npc_important",
}

_DEFAULT_ROLE = "npc_passerby"


def normalize_role(raw: str | None) -> str:
    text = (raw or "").strip()
    if not text:
        return _DEFAULT_ROLE
    if text in _ROLE_LABELS:
        return text
    if text in _LEGACY_MAP:
        return _LEGACY_MAP[text]
    lowered = text.lower()
    if lowered in _LEGACY_MAP:
        return _LEGACY_MAP[lowered]
    return text if text in _ROLE_LABELS else _DEFAULT_ROLE


def role_label(value: str | None) -> str:
    key = normalize_role(value)
    return _ROLE_LABELS.get(key, value or _ROLE_LABELS[_DEFAULT_ROLE])


def role_options_for_template() -> list[dict[str, str]]:
    return [{"value": v, "label": label} for v, label in ROLE_OPTIONS]
