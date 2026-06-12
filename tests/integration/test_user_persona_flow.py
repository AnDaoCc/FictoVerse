from __future__ import annotations

import json
from pathlib import Path

import pytest

from novel_world.application.use_cases.create_world import CreateWorldUseCase
from novel_world.bootstrap.app_context import create_app_context
from novel_world.bootstrap.app_factory import create_app
from novel_world.core.domain.ids import WorldId
from novel_world.modules.ai.services.user_persona import merge_session_persona


@pytest.fixture
def app_runtime(tmp_path: Path):
    ctx = create_app_context(tmp_path)
    runtime = ctx.open()
    yield runtime
    runtime.close()


def _make_world(tmp_path: Path, name: str = "测试世界") -> str:
    world = CreateWorldUseCase(base_dir=tmp_path).execute(name)
    return str(world.id)


def _two_chars(tmp_path: Path) -> tuple[str, str, str]:
    w1 = _make_world(tmp_path, "群世界")
    factory = create_app(tmp_path)
    rt = factory.open_world(WorldId(w1))
    try:
        c1 = rt.character.create(WorldId(w1), "角色甲", role="主角")
        c2 = rt.character.create(WorldId(w1), "角色乙", role="配角")
        rt.session.commit()
        return w1, str(c1.id), str(c2.id)
    finally:
        rt.close()


def test_chat_session_inherits_world_persona(app_runtime, tmp_path: Path) -> None:
    world_id = _make_world(tmp_path)
    factory = create_app(tmp_path)
    rt = factory.open_world(WorldId(world_id))
    try:
        world = rt.world.get(WorldId(world_id))
        settings = dict(world.settings) if isinstance(world.settings, dict) else {}
        settings["user_persona"] = {"name": "世界旅人", "description": "路过的观察者"}
        rt.world.update(WorldId(world_id), settings=settings)
        rt.session.commit()
    finally:
        rt.close()

    provider = app_runtime.providers.create(
        "Mock", "openai_compatible", {"api_key": "k", "base_url": "http://x/v1", "model": "m"}
    )
    session = app_runtime.chat.create_session(provider.id, "m", world_id=world_id)
    persona = merge_session_persona(session.config)
    assert persona["name"] == "世界旅人"
    app_runtime.commit()


class _CaptureStub:
    def __init__(self, speaker_id: str) -> None:
        self.last_prompt = ""
        self._speaker_id = speaker_id

    def complete(self, messages, *, model, generation=None):
        self.last_prompt = messages[-1].content if messages else ""
        return json.dumps({"speaker_id": self._speaker_id, "content": "hi"})


def test_group_prompt_includes_user_persona(app_runtime, tmp_path: Path) -> None:
    w1, c1, c2 = _two_chars(tmp_path)
    provider = app_runtime.providers.create(
        "Mock", "openai_compatible", {"api_key": "k", "base_url": "http://x/v1", "model": "m"}
    )
    session = app_runtime.group_chat.create_group(
        provider.id,
        "m",
        title="人设测试群",
        members=[
            {"world_id": w1, "character_id": c1},
            {"world_id": w1, "character_id": c2},
        ],
    )
    app_runtime.group_chat.update_persona(
        session.id, name="调查员林", description="局外人"
    )
    stub = _CaptureStub(c1)
    app_runtime.group_chat._providers.build_client = lambda pid: stub

    list(
        app_runtime.group_chat.reply_round(
            session.id, content="大家好", mode="send", max_round=1
        )
    )
    assert "调查员林" in stub.last_prompt or "局外人" in stub.last_prompt
    app_runtime.commit()
