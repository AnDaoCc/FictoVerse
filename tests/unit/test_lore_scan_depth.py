from novel_world.modules.ai.services.lore_engine import LoreEngine
from novel_world.modules.ai.services.prompt_context import build_scan_text_for_entry
from novel_world.modules.world.domain.lore_entry import LoreEntry


class _Msg:
    def __init__(self, content: str):
        self.content = content


def test_scan_depth_limits_history() -> None:
    messages = [_Msg(f"m{i}") for i in range(20)]
    entry = LoreEntry(id="1", content="x", scan_depth=3)
    text = build_scan_text_for_entry(messages, "", entry, default_limit=12)
    assert "m19" in text
    assert "m0" not in text


def test_keyword_match_with_secondary_and_logic() -> None:
    engine = LoreEngine()
    entry = LoreEntry(
        id="a",
        keys=["magic"],
        keys_secondary=["fire"],
        selective_logic=3,
        content="combo",
        selective=True,
    )
    assert engine._matches_keywords(entry, "magic and fire spell", False)
    assert not engine._matches_keywords(entry, "only magic", False)
