from __future__ import annotations

import json
from typing import Any

from novel_world.modules.character.domain.character_card import CARD_SPEC, CharacterCard


def is_chub_card(data: dict[str, Any]) -> bool:
    return bool(data.get("chub") or data.get("is_chub") or data.get("source") == "chub")


def parse_chub_card(data: dict[str, Any]) -> CharacterCard:
    """Chub.ai 导出 JSON → 内部 CharacterCard。"""
    inner = data.get("data") if isinstance(data.get("data"), dict) else data
    name = str(inner.get("name") or data.get("name") or "未命名")
    card = CharacterCard(
        name=name,
        description=str(inner.get("description") or inner.get("personality") or ""),
        personality=str(inner.get("personality") or ""),
        scenario=str(inner.get("scenario") or ""),
        first_mes=str(inner.get("first_mes") or inner.get("greeting") or ""),
        mes_example=str(inner.get("mes_example") or ""),
        creator=str(inner.get("creator") or data.get("creator") or ""),
        tags=[str(t) for t in (inner.get("tags") or data.get("tags") or []) if str(t).strip()],
        card_spec=CARD_SPEC,
        card_spec_version="2.0",
    )
    card.metadata = {"import_raw": data, "import_format": "chub"}
    book = inner.get("character_book") or inner.get("char_book")
    if isinstance(book, dict):
        card.character_book = book
    return card


def parse_chub_bytes(raw: bytes) -> CharacterCard:
    data = json.loads(raw.decode("utf-8"))
    if not isinstance(data, dict):
        raise ValueError("Chub JSON 根节点必须是对象。")
    return parse_chub_card(data)
