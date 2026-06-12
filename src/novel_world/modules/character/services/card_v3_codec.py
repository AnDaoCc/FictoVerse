"""SillyTavern V3 角色卡编解码辅助。"""
from __future__ import annotations

from typing import Any

from novel_world.modules.character.domain.character_card import (
    CARD_SPEC,
    CARD_SPEC_V3,
    CharacterCard,
)


def is_v3_raw(raw: dict[str, Any]) -> bool:
    return str(raw.get("spec", "")).strip() == CARD_SPEC_V3


def normalize_card_warnings(raw: dict[str, Any], warnings: list[str]) -> list[str]:
    spec = str(raw.get("spec", "")).strip()
    if spec == CARD_SPEC_V3:
        warnings = [w for w in warnings if "未知的 spec" not in w]
        if not any("V3" in w for w in warnings):
            warnings.insert(0, "已识别为酒馆 V3 角色卡。")
    elif spec and spec != CARD_SPEC:
        warnings.append(f"未知的 spec「{spec}」，已尝试按 V2/V3 字段解析。")
    return warnings


def card_to_json_bytes(card: CharacterCard, *, prefer_v3: bool = True, indent: int = 2) -> bytes:
    import json

    payload = card.to_export_dict(prefer_v3=prefer_v3)
    return json.dumps(payload, ensure_ascii=False, indent=indent).encode("utf-8")
