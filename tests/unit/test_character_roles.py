from __future__ import annotations

from novel_world.modules.character.character_roles import (
    ROLE_OPTIONS,
    normalize_role,
    role_label,
)


def test_normalize_legacy_values() -> None:
    assert normalize_role("主角") == "hero_male"
    assert normalize_role("配角") == "npc_important"
    assert normalize_role("player") == "hero_male"
    assert normalize_role("npc") == "npc_passerby"
    assert normalize_role("hero_female") == "hero_female"


def test_role_label() -> None:
    assert role_label("hero_male") == "男主角"
    assert role_label("主角") == "男主角"
    assert role_label("npc") == "路人NPC"
    assert role_label("") == "路人NPC"


def test_role_options_count() -> None:
    assert len(ROLE_OPTIONS) == 7
