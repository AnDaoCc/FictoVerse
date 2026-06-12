from __future__ import annotations

from novel_world.modules.ai.services.lore_engine import LoreEngine
from novel_world.modules.world.domain.lore_entry import LoreEntry


def test_lore_constant_always_included() -> None:
    engine = LoreEngine()
    entries = [
        LoreEntry(id="c1", content="Always here", constant=True, keys=[]),
        LoreEntry(id="s1", content="Secret lore", keys=["dragon"], selective=True),
    ]
    result = engine.scan(entries, "hello world", token_budget=2000)
    assert "c1" in result.matched_ids
    assert "s1" not in result.matched_ids
    assert "Always here" in "\n".join(result.before_main)


def test_lore_keyword_match_and_budget() -> None:
    engine = LoreEngine()
    entries = [
        LoreEntry(id="low", content="x" * 400, keys=["dragon"], priority=0),
        LoreEntry(id="high", content="Dragon lore", keys=["dragon"], priority=10),
    ]
    result = engine.scan(entries, "I saw a dragon", token_budget=50)
    assert "high" in result.matched_ids


def test_lore_recursive_second_round() -> None:
    engine = LoreEngine()
    entries = [
        LoreEntry(
            id="a",
            content="mentions phoenix",
            keys=["dragon"],
            recursive=True,
        ),
        LoreEntry(id="b", content="Phoenix detail", keys=["phoenix"]),
    ]
    result = engine.scan(entries, "dragon appeared", token_budget=2000)
    assert "a" in result.matched_ids
    assert "b" in result.matched_ids


def test_character_book_parsing() -> None:
    book = {
        "entries": [
            {"keys": ["key1"], "content": "Entry one", "constant": False},
        ]
    }
    parsed = LoreEngine.entries_from_character_book(book, "char-1")
    assert len(parsed) == 1
    assert parsed[0].keys == ["key1"]
    assert parsed[0].source == "character_book"
