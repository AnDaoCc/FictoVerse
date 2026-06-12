from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from novel_world.application.use_cases.create_world import CreateWorldUseCase
from novel_world.bootstrap.app_context import create_app_context
from novel_world.bootstrap.app_factory import create_app
from novel_world.core.domain.ids import WorldId
from novel_world.infrastructure.repositories.sqlite_repositories import SqliteCharacterRepository
from novel_world.modules.ai.services.roleplay_service import RoleplayService
from novel_world.modules.character.domain.character_card import CharacterCard
from novel_world.modules.character.services.card_codec import card_to_json_bytes
from novel_world.modules.character.services.character_card_service import CharacterCardService


@pytest.fixture
def app_runtime(tmp_path: Path):
    ctx = create_app_context(tmp_path)
    runtime = ctx.open()
    yield runtime
    runtime.close()


def _make_character(tmp_path, world_id, name="角色A", **profile_extra):
    factory = create_app(tmp_path)
    rt = factory.open_world(WorldId(str(world_id)))
    try:
        profile = {
            "personality": "冷静",
            "first_mes": "你好，旅人。",
            "mes_example": "<START>\n{{user}}: 你好\n{{char}}: 嗯。",
            **profile_extra,
        }
        c = rt.character.create(WorldId(str(world_id)), name, role="主角", profile=profile)
        rt.session.commit()
        return c
    finally:
        rt.close()


def _make_other_character(tmp_path, world_id, name="角色B"):
    return _make_character(tmp_path, world_id, name=name)


class _StubClient:
    def __init__(self) -> None:
        self.last_messages = None

    def complete(self, messages, *, model, generation=None):
        return "摘要"

    def stream_complete(self, messages, *, model, generation=None):
        self.last_messages = messages
        from novel_world.modules.ai.ports.llm_provider import StreamChunk

        yield StreamChunk(kind="content", text="角色回复")
        yield StreamChunk(kind="done")


def test_roleplay_session_first_mes(app_runtime, tmp_path) -> None:
    world = CreateWorldUseCase(base_dir=tmp_path).execute("RP世界")
    c = _make_character(tmp_path, world.id)
    provider = app_runtime.providers.create(
        "Mock", "openai_compatible", {"api_key": "k", "base_url": "http://x/v1", "model": "m"}
    )
    session = app_runtime.roleplay.create_session(
        provider.id,
        "m",
        world_id=str(world.id),
        character_id=str(c.id),
        user_persona={"name": "旅人", "description": "外来者"},
    )
    app_runtime.commit()
    messages = app_runtime.roleplay.get_messages(session.id)
    assert len(messages) == 1
    assert messages[0].role == "assistant"
    assert messages[0].content == "你好，旅人。"
    assert messages[0].speaker["name"] == "角色A"


def test_roleplay_prompt_single_character(app_runtime, tmp_path) -> None:
    world = CreateWorldUseCase(base_dir=tmp_path).execute("多角世界", description="测试")
    c1 = _make_character(tmp_path, world.id, name="主角A")
    _make_other_character(tmp_path, world.id, name="配角B")
    provider = app_runtime.providers.create(
        "Mock", "openai_compatible", {"api_key": "k", "base_url": "http://x/v1", "model": "m"}
    )
    session = app_runtime.roleplay.create_session(
        provider.id,
        "m",
        world_id=str(world.id),
        character_id=str(c1.id),
        user_persona={"name": "旅人", "description": "测试身份"},
    )
    stub = _StubClient()
    app_runtime.roleplay._providers.build_client = lambda pid: stub
    list(app_runtime.roleplay.stream_message(session.id, "你好"))
    app_runtime.commit()

    system_msgs = [m for m in stub.last_messages if m.role == "system"]
    assert system_msgs
    system_text = system_msgs[0].content
    assert "主角A" in system_text
    assert "配角B" not in system_text
    assert "旅人" in system_text
    assert "测试身份" in system_text or "对话对象" in system_text


def test_import_card_updates_character(tmp_path) -> None:
    world = CreateWorldUseCase(base_dir=tmp_path).execute("卡世界")
    factory = create_app(tmp_path)
    rt = factory.open_world(WorldId(str(world.id)))
    try:
        c = rt.character.create(WorldId(str(world.id)), "占位", role="npc")
        rt.session.commit()
        card_svc = CharacterCardService(
            factory.config,
            SqliteCharacterRepository(rt.session.connection),
        )
        card = CharacterCard(name="导入角色", description="描述", first_mes="嗨")
        updated, _warnings = card_svc.import_card(
            WorldId(str(world.id)), c.id, card_to_json_bytes(card), "card.json"
        )
        rt.session.commit()
        assert updated.name == "导入角色"
        assert updated.profile["first_mes"] == "嗨"
        assert updated.metadata["card"]["spec"] == "chara_card_v2"
    finally:
        rt.close()


def test_roleplay_routes_registered() -> None:
    from novel_world.web.app import app

    paths = [getattr(r, "path", "") for r in app.routes]
    assert "/worlds/{world_id}/roleplay/{character_id}/chat" in paths
    assert "/api/roleplay/sessions/{session_id}/stream" in paths
    assert "/api/sessions/{session_id}/prompt-preview" in paths


def test_roleplay_prompt_includes_memory(app_runtime, tmp_path) -> None:
    from novel_world.application.use_cases.create_world import CreateWorldUseCase

    world = CreateWorldUseCase(base_dir=tmp_path).execute("记忆世界")
    c = _make_character(tmp_path, world.id, name="记忆角色")
    provider = app_runtime.providers.create(
        "Mock", "openai_compatible", {"api_key": "k", "base_url": "http://x/v1", "model": "m"}
    )
    session = app_runtime.roleplay.create_session(
        provider.id,
        "m",
        world_id=str(world.id),
        character_id=str(c.id),
    )
    app_runtime.memory.pin(session.id, "用户有一只黑猫", pinned=True)
    app_runtime.commit()

    preview = app_runtime.roleplay.preview_prompt(session.id, "你好")
    assert "黑猫" in preview["system"] or preview["memory_injected"]
