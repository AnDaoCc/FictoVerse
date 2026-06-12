from __future__ import annotations

import json

from novel_world.modules.world.domain.lore_entry import LoreEntry
from novel_world.modules.world.services.st_lore_codec import (
    export_st_world_info,
    parse_st_world_info,
)


def test_parse_st_entries_object() -> None:
    raw = {
        "entries": {
            "0": {
                "uid": 10,
                "keys": ["dragon"],
                "content": "Dragon lore",
                "position": 1,
                "disable": False,
            },
            "1": {
                "key": "magic",
                "keysecondary": ["spell"],
                "content": "Magic rules",
                "constant": True,
                "position": 4,
                "depth": 2,
            },
        }
    }
    entries = parse_st_world_info(raw)
    assert len(entries) == 2
    by_ref = {e.source_ref: e for e in entries}
    assert by_ref["10"].keys == ["dragon"]
    assert by_ref["10"].position == "after_char"
    magic = next(e for e in entries if "magic" in e.keys)
    assert magic.constant is True
    assert magic.position == "at_depth"
    assert magic.depth == 2
    assert "spell" in magic.keys_secondary


def test_parse_st_entries_array() -> None:
    raw = {"entries": [{"keys": ["a"], "content": "Entry A", "enabled": False}]}
    entries = parse_st_world_info(raw)
    assert len(entries) == 1
    assert entries[0].enabled is False


def test_parse_top_level_array() -> None:
    raw = [{"keys": ["x"], "content": "Top array entry"}]
    entries = parse_st_world_info(raw)
    assert len(entries) == 1
    assert entries[0].content == "Top array entry"


def test_parse_advanced_fields() -> None:
    raw = {
        "entries": {
            "0": {
                "keys": ["x"],
                "content": "Advanced",
                "probability": 0.5,
                "group": "g1",
                "groupWeight": 10,
                "cooldown": 3,
                "sticky": 2,
                "characterFilter": ["Alice"],
            }
        }
    }
    entries = parse_st_world_info(raw)
    assert len(entries) == 1
    e = entries[0]
    assert e.probability == 0.5
    assert e.lore_group == "g1"
    assert e.group_weight == 10
    assert e.cooldown == 3
    assert e.sticky == 2
    assert e.character_filter == ["Alice"]


def test_export_round_trip_fields() -> None:
    entry = LoreEntry(
        id="e1",
        keys=["fire", "flame"],
        content="Fire lore",
        constant=False,
        selective=True,
        recursive=True,
        priority=5,
        insertion_order=3,
        position="after_char",
        depth=6,
        enabled=True,
        comment="note",
        source="st_import",
        source_ref="42",
    )
    exported = export_st_world_info([entry])
    assert "entries" in exported
    assert "0" in exported["entries"]
    item = exported["entries"]["0"]
    assert item["content"] == "Fire lore"
    assert item["key"] == "fire"
    assert item["keysecondary"] == ["flame"]
    assert item["position"] == 1
    assert item["extensions"]["recursive"] is True
    assert item["disable"] is False

    restored = parse_st_world_info(exported, source="manual")
    assert len(restored) == 1
    assert restored[0].keys == ["fire", "flame"]
    assert restored[0].recursive is True
    assert restored[0].position == "after_char"


def test_export_json_serializable() -> None:
    entry = LoreEntry(id="e2", keys=["k"], content="c", source_ref="1")
    payload = export_st_world_info([entry])
    json.dumps(payload, ensure_ascii=False)
