from __future__ import annotations

from novel_world.modules.ai.services.world_speaker import (
    infer_speaker_from_content,
    parse_world_reply,
)


class _Char:
    def __init__(self, cid: str, name: str, role: str = "hero_male") -> None:
        self.id = cid
        self.name = name
        self.role = role
        self.metadata = {}


class _FakeWorldApp:
    def open_world(self, _wid):
        return self

    def close(self) -> None:
        return None

    def list_by_world(self, _wid, active_only=True):
        return [_Char("c1", "凌筱喻", "hero_male")]


class _FakeRT:
    character = _FakeWorldApp()


def test_infer_speaker_from_plain_text() -> None:
    app = _FakeWorldApp()
    app.character = type("C", (), {"list_by_world": _FakeWorldApp().list_by_world})()
    chars = [_Char("c1", "凌筱喻", "hero_male")]
    sp = infer_speaker_from_content(
        app, "w1", "（愣了一下）对，我是凌筱喻。", characters=chars
    )
    assert sp is not None
    assert sp["name"] == "凌筱喻"


def test_parse_world_reply_plain_fallback() -> None:
    app = _FakeWorldApp()
    chars = [_Char("c1", "凌筱喻", "hero_male")]
    sp, content = parse_world_reply(
        app,
        "w1",
        "你好，我是凌筱喻。",
        characters=chars,
    )
    assert sp is not None
    assert sp["name"] == "凌筱喻"
    assert "凌筱喻" in content


def test_parse_world_reply_json() -> None:
    app = _FakeWorldApp()
    chars = [_Char("c1", "凌筱喻", "hero_male")]
    raw = '{"speaker_id":"c1","content":"你好。"}'
    sp, content = parse_world_reply(app, "w1", raw, characters=chars)
    assert sp is not None
    assert sp["name"] == "凌筱喻"
    assert content == "你好。"
