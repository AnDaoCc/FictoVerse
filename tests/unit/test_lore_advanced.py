from __future__ import annotations

from novel_world.modules.ai.services.lore_engine import LoreEngine
from novel_world.modules.ai.services.lore_session_state import LoreSessionState
from novel_world.modules.world.domain.lore_entry import LoreEntry


def test_probability_can_skip_entry(monkeypatch) -> None:
    monkeypatch.setattr("novel_world.modules.ai.services.lore_session_state.random.random", lambda: 0.99)
    engine = LoreEngine()
    entries = [
        LoreEntry(id="p1", keys=["dragon"], content="Dragon lore", probability=0.1, selective=True),
    ]
    result = engine.scan(entries, "a dragon appeared", token_budget=2000)
    assert "p1" not in result.matched_ids


def test_sticky_keeps_entry_without_keyword() -> None:
    engine = LoreEngine()
    state = LoreSessionState(sticky={"s1": 2})
    entries = [
        LoreEntry(id="s1", keys=["magic"], content="Sticky magic", sticky=3, selective=True),
    ]
    result = engine.scan(entries, "hello", session_state=state, token_budget=2000)
    assert "s1" in result.matched_ids


def test_character_filter_include() -> None:
    engine = LoreEngine()
    entries = [
        LoreEntry(
            id="f1",
            keys=["test"],
            content="For Alice",
            character_filter=["Alice"],
            filter_type="include",
        ),
        LoreEntry(id="f2", keys=["test"], content="For all", selective=True),
    ]
    result = engine.scan(
        entries,
        "test",
        active_character_name="Alice",
        token_budget=2000,
    )
    assert "f1" in result.matched_ids
    assert "f2" in result.matched_ids


def test_group_weight_picks_one() -> None:
    engine = LoreEngine()
    entries = [
        LoreEntry(id="g1", keys=["x"], content="low", lore_group="g", group_weight=1, selective=True),
        LoreEntry(id="g2", keys=["x"], content="high", lore_group="g", group_weight=10, selective=True),
    ]
    result = engine.scan(entries, "x", token_budget=2000)
    assert len(result.matched_ids) == 1
    assert "g2" in result.matched_ids
