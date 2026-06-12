from __future__ import annotations

import json

import pytest

from novel_world.modules.character.domain.character_card import CharacterCard
from novel_world.modules.character.domain.entities import Character
from novel_world.modules.character.services.card_codec import (
    card_from_json_bytes,
    card_from_json_bytes_with_warnings,
    card_from_png_bytes,
    card_to_json_bytes,
    card_to_png_bytes,
)
from novel_world.modules.character.services.card_mapper import (
    apply_card_to_character,
    card_from_character,
)


def test_v2_json_round_trip() -> None:
    card = CharacterCard(
        name="凌筱崎",
        description="天才剑修",
        personality="冷静",
        scenario="宗门大比前夜",
        first_mes="你来了。",
        mes_example="<START>\n{{user}}: 你好\n{{char}}: 嗯。",
        post_history_instructions="保持古风",
        tags=["玄幻"],
    )
    raw = card_to_json_bytes(card)
    restored = card_from_json_bytes(raw)
    assert restored.name == "凌筱崎"
    assert restored.first_mes == "你来了。"
    assert restored.tags == ["玄幻"]


def test_v2_dict_wrapper() -> None:
    payload = {
        "spec": "chara_card_v2",
        "spec_version": "2.0",
        "data": {"name": "测试", "description": "desc", "first_mes": "hi"},
    }
    card = CharacterCard.from_v2_dict(payload)
    assert card.name == "测试"
    out = card.to_v2_dict()
    assert out["spec"] == "chara_card_v2"
    assert out["data"]["name"] == "测试"


def test_png_chara_round_trip() -> None:
    card = CharacterCard(name="PNG角色", first_mes="开场")
    png = card_to_png_bytes(card)
    restored, _ = card_from_png_bytes(png)
    assert restored.name == "PNG角色"
    assert restored.first_mes == "开场"


def test_flat_json_without_spec_warns() -> None:
    payload = {"name": "扁平卡", "description": "无 spec", "first_mes": "你好"}
    card, warnings = card_from_json_bytes_with_warnings(json.dumps(payload).encode("utf-8"))
    assert card.name == "扁平卡"
    assert any("spec" in w for w in warnings)


def test_mapper_apply_and_export() -> None:
    character = Character(
        id="c1",
        world_id="w1",
        name="旧名",
        profile={"summary": "旧简介"},
        metadata={},
    )
    card = CharacterCard(
        name="新名",
        description="新描述",
        personality="活泼",
        first_mes="你好呀",
    )
    apply_card_to_character(character, card)
    assert character.name == "新名"
    assert character.profile["description"] == "新描述"
    assert character.profile["first_mes"] == "你好呀"
    assert character.metadata["card"]["spec"] == "chara_card_v2"

    exported = card_from_character(character)
    assert exported.name == "新名"
    assert exported.first_mes == "你好呀"
