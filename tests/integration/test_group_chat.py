from __future__ import annotations

import json
from pathlib import Path

import pytest

from novel_world.application.use_cases.create_world import CreateWorldUseCase
from novel_world.bootstrap.app_context import create_app_context
from novel_world.bootstrap.app_factory import create_app
from novel_world.core.domain.ids import WorldId


@pytest.fixture
def app_runtime(tmp_path: Path):
    ctx = create_app_context(tmp_path)
    runtime = ctx.open()
    yield runtime
    runtime.close()


def _make_world_with_character(tmp_path: Path, world_name: str, char_name: str) -> tuple[str, str]:
    world = CreateWorldUseCase(base_dir=tmp_path).execute(world_name)
    factory = create_app(tmp_path)
    rt = factory.open_world(WorldId(str(world.id)))
    try:
        character = rt.character.create(WorldId(str(world.id)), char_name, role="主角")
        rt.session.commit()
    finally:
        rt.close()
    return str(world.id), str(character.id)


class _CyclingStub:
    """按顺序返回不同发言者的 JSON，模拟群聊选角。"""

    def __init__(self, speaker_ids: list[str]) -> None:
        self._ids = speaker_ids
        self._i = 0
        self.calls = 0

    def complete(self, messages, *, model, generation=None):
        self.calls += 1
        speaker = self._ids[self._i % len(self._ids)]
        self._i += 1
        return json.dumps({"speaker_id": speaker, "content": f"{speaker} 的发言"})


def _setup_group(app_runtime, tmp_path):
    w1, c1 = _make_world_with_character(tmp_path, "世界甲", "甲角色")
    w2, c2 = _make_world_with_character(tmp_path, "世界乙", "乙角色")
    provider = app_runtime.providers.create(
        "Mock", "openai_compatible", {"api_key": "k", "base_url": "http://x/v1", "model": "m"}
    )
    session = app_runtime.group_chat.create_group(
        provider.id,
        "m",
        title="跨界群",
        members=[
            {"world_id": w1, "character_id": c1},
            {"world_id": w2, "character_id": c2},
        ],
    )
    app_runtime.commit()
    return session, [c1, c2]


def test_create_group_persists_members(app_runtime, tmp_path) -> None:
    session, ids = _setup_group(app_runtime, tmp_path)
    assert session.session_type == "group"
    members = app_runtime.group_chat.get_members(session.id)
    assert len(members) == 2
    assert {m.character_id for m in members} == set(ids)
    assert {m.world_name for m in members} == {"世界甲", "世界乙"}


def test_create_group_same_world_two_members(app_runtime, tmp_path) -> None:
    w1, c1 = _make_world_with_character(tmp_path, "同世界", "角色甲")
    factory = create_app(tmp_path)
    rt = factory.open_world(WorldId(w1))
    try:
        c2 = rt.character.create(WorldId(w1), "角色乙", role="配角")
        rt.session.commit()
    finally:
        rt.close()
    provider = app_runtime.providers.create(
        "Mock", "openai_compatible", {"api_key": "k", "base_url": "http://x/v1", "model": "m"}
    )
    session = app_runtime.group_chat.create_group(
        provider.id,
        "m",
        title="同世界群",
        members=[
            {"world_id": w1, "character_id": c1},
            {"world_id": w1, "character_id": str(c2.id)},
        ],
    )
    app_runtime.commit()
    assert len(app_runtime.group_chat.get_members(session.id)) == 2


def test_create_group_requires_two_members(app_runtime, tmp_path) -> None:
    from novel_world.core.exceptions import ValidationError

    w1, c1 = _make_world_with_character(tmp_path, "孤独世界", "独行者")
    provider = app_runtime.providers.create(
        "Mock", "openai_compatible", {"api_key": "k", "base_url": "http://x/v1", "model": "m"}
    )
    with pytest.raises(ValidationError):
        app_runtime.group_chat.create_group(
            provider.id, "m", title="单人", members=[{"world_id": w1, "character_id": c1}]
        )


def test_reply_round_manual_generates_capped_replies(app_runtime, tmp_path) -> None:
    session, ids = _setup_group(app_runtime, tmp_path)
    stub = _CyclingStub(ids)
    app_runtime.group_chat._providers.build_client = lambda pid: stub

    events = list(
        app_runtime.group_chat.reply_round(
            session.id, content="大家好", mode="send", max_round=2
        )
    )
    app_runtime.commit()

    char_events = [e for e in events if e["event"] == "character_message"]
    assert len(char_events) == 2
    assert any(e["event"] == "user_message" for e in events)
    assert events[-1]["event"] == "done"

    messages = app_runtime.group_chat.get_messages(session.id)
    # 1 条用户消息 + 2 条角色消息
    assert len(messages) == 3
    assert messages[0].role == "user"
    assert messages[1].speaker is not None
    assert messages[1].speaker["name"] in {"甲角色", "乙角色"}


def test_auto_reply_respects_stop(app_runtime, tmp_path) -> None:
    session, ids = _setup_group(app_runtime, tmp_path)
    stub = _CyclingStub(ids)
    app_runtime.group_chat._providers.build_client = lambda pid: stub

    gen = app_runtime.group_chat.reply_round(session.id, mode="auto", max_round=10)
    produced = 0
    for evt in gen:
        if evt["event"] == "character_message":
            produced += 1
            if produced == 1:
                app_runtime.group_chat.request_stop(session.id)
    app_runtime.commit()

    # 第一条之后请求停止，循环在下一轮开始处中断
    assert produced == 1


def test_auto_reply_respects_max_round(app_runtime, tmp_path) -> None:
    session, ids = _setup_group(app_runtime, tmp_path)
    stub = _CyclingStub(ids)
    app_runtime.group_chat._providers.build_client = lambda pid: stub

    events = list(app_runtime.group_chat.reply_round(session.id, mode="auto", max_round=3))
    char_events = [e for e in events if e["event"] == "character_message"]
    assert len(char_events) == 3


def test_send_mode_uses_max_round_not_legacy_default(app_runtime, tmp_path) -> None:
    session, ids = _setup_group(app_runtime, tmp_path)
    stub = _CyclingStub(ids)
    app_runtime.group_chat._providers.build_client = lambda pid: stub

    events = list(
        app_runtime.group_chat.reply_round(
            session.id, content="你好", mode="send", max_round=5
        )
    )
    char_events = [e for e in events if e["event"] == "character_message"]
    assert len(char_events) == 5


def test_max_per_character_caps_same_speaker(app_runtime, tmp_path) -> None:
    session, ids = _setup_group(app_runtime, tmp_path)
    stub = _CyclingStub(ids)
    app_runtime.group_chat._providers.build_client = lambda pid: stub

    events = list(
        app_runtime.group_chat.reply_round(
            session.id,
            mode="auto",
            max_round=10,
            max_per_character=1,
        )
    )
    char_events = [e for e in events if e["event"] == "character_message"]
    assert len(char_events) == 2
    speakers = {e["data"]["speaker"]["character_id"] for e in char_events}
    assert speakers == set(ids)


class _EmptyThenOkStub:
    def __init__(self, speaker_id: str) -> None:
        self._speaker_id = speaker_id
        self.calls = 0

    def complete(self, messages, *, model, generation=None):
        self.calls += 1
        if self.calls == 2:
            return ""
        return json.dumps(
            {"speaker_id": self._speaker_id, "content": f"reply-{self.calls}"}
        )


def test_empty_reply_does_not_stop_entire_round(app_runtime, tmp_path) -> None:
    session, ids = _setup_group(app_runtime, tmp_path)
    stub = _EmptyThenOkStub(ids[0])
    app_runtime.group_chat._providers.build_client = lambda pid: stub

    events = list(
        app_runtime.group_chat.reply_round(
            session.id, mode="reply", max_round=3
        )
    )
    char_events = [e for e in events if e["event"] == "character_message"]
    assert len(char_events) == 3
    assert stub.calls >= 4


def test_mute_member_excludes_from_active(app_runtime, tmp_path) -> None:
    session, ids = _setup_group(app_runtime, tmp_path)
    app_runtime.group_chat.set_member_muted(session.id, ids[0], muted=True)
    updated = app_runtime.group_chat.get_session(session.id)
    assert ids[0] in (updated.config or {}).get("muted", [])
    app_runtime.commit()


def test_force_character_id_reply(app_runtime, tmp_path) -> None:
    session, ids = _setup_group(app_runtime, tmp_path)

    class _ForcedStub:
        def complete(self, messages, *, model, generation=None):
            text = messages[-1].content if messages else ""
            assert ids[0] in text
            return json.dumps({"speaker_id": ids[0], "content": "forced reply"})

    app_runtime.group_chat._providers.build_client = lambda pid: _ForcedStub()
    events = list(
        app_runtime.group_chat.reply_round(
            session.id,
            content="",
            mode="reply",
            max_round=1,
            force_character_id=ids[0],
        )
    )
    char_events = [e for e in events if e["event"] == "character_message"]
    assert len(char_events) == 1
    assert char_events[0]["data"]["speaker"]["character_id"] == ids[0]
    app_runtime.commit()
