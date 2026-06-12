from __future__ import annotations

import json

from novel_world.modules.character.domain.character_card import CARD_SPEC_V3, CharacterCard
from novel_world.modules.character.services.card_codec import card_from_json_bytes_with_warnings
from novel_world.modules.character.services.card_v3_codec import card_to_json_bytes


def test_v3_round_trip() -> None:
    card = CharacterCard(
        name="V3角色",
        description="desc",
        first_mes="hi",
        group_only_greetings=["group hi"],
        card_spec=CARD_SPEC_V3,
        card_spec_version="3.0",
    )
    raw = card_to_json_bytes(card)
    payload = json.loads(raw.decode("utf-8"))
    assert payload["spec"] == CARD_SPEC_V3
    restored, warnings = card_from_json_bytes_with_warnings(raw)
    assert restored.name == "V3角色"
    assert restored.group_only_greetings == ["group hi"]
    assert any("V3" in w for w in warnings)
