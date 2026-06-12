from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from novel_world.bootstrap.app_context import create_app_context
from novel_world.bootstrap.app_factory import create_app


@pytest.fixture
def app_runtime(tmp_path: Path):
    ctx = create_app_context(tmp_path)
    runtime = ctx.open()
    yield runtime
    runtime.close()


def test_provider_registry_create_and_build(app_runtime) -> None:
    provider = app_runtime.providers.create(
        "Test OpenAI Compatible",
        "openai_compatible",
        {
            "api_key": "test-key",
            "base_url": "http://localhost:9999/v1",
            "model": "test-model",
        },
    )
    client = app_runtime.providers.build_client(provider.id)
    assert client is not None


@patch("novel_world.modules.ai.providers.openai_provider.httpx.Client")
def test_chat_send_message_mock(mock_client_cls, app_runtime, tmp_path) -> None:
    def iter_lines():
        yield 'data: {"choices":[{"delta":{"content":"你好，我是 AI。"}}]}'
        yield "data: [DONE]"

    mock_stream_resp = MagicMock()
    mock_stream_resp.raise_for_status = MagicMock()
    mock_stream_resp.iter_lines = iter_lines

    mock_stream_ctx = MagicMock()
    mock_stream_ctx.__enter__ = MagicMock(return_value=mock_stream_resp)
    mock_stream_ctx.__exit__ = MagicMock(return_value=False)

    mock_client = MagicMock()
    mock_client.__enter__ = MagicMock(return_value=mock_client)
    mock_client.__exit__ = MagicMock(return_value=False)
    mock_client.stream.return_value = mock_stream_ctx
    mock_client_cls.return_value = mock_client

    provider = app_runtime.providers.create(
        "Mock Provider",
        "openai_compatible",
        {
            "api_key": "k",
            "base_url": "http://localhost:9999/v1",
            "model": "mock-model",
        },
    )
    session = app_runtime.chat.create_session(provider.id, "mock-model")
    reply = app_runtime.chat.send_message(session.id, "你好")
    app_runtime.commit()

    assert reply.content == "你好，我是 AI。"
    messages = app_runtime.chat.get_messages(session.id)
    assert len(messages) == 2
    assert messages[0].role == "user"
    assert messages[1].role == "assistant"


def test_delete_chat_session(app_runtime) -> None:
    provider = app_runtime.providers.create(
        "Mock",
        "openai_compatible",
        {"api_key": "k", "base_url": "http://x/v1", "model": "m"},
    )
    session = app_runtime.chat.create_session(provider.id, "m")
    app_runtime.commit()
    assert len(app_runtime.chat.list_sessions(world_id=None)) == 1

    app_runtime.chat.delete_session(session.id)
    app_runtime.commit()
    assert app_runtime.chat.list_sessions(world_id=None) == []


def test_delete_world_removes_db_file(app_runtime, tmp_path) -> None:
    from novel_world.application.use_cases.create_world import CreateWorldUseCase
    from novel_world.core.domain.ids import WorldId

    world = CreateWorldUseCase(base_dir=tmp_path).execute("待删除世界")
    factory = create_app(tmp_path)
    assert WorldId(str(world.id)) in factory.list_world_ids()

    assert factory.delete_world(WorldId(str(world.id))) is True
    assert WorldId(str(world.id)) not in factory.list_world_ids()


def test_world_system_prompt_includes_world_name(app_runtime, tmp_path) -> None:
    from novel_world.application.use_cases.create_world import CreateWorldUseCase

    world = CreateWorldUseCase(base_dir=tmp_path).execute(
        "测试世界",
        description="一个测试世界",
        rules={"magic": True},
    )
    provider = app_runtime.providers.create(
        "Mock",
        "openai_compatible",
        {"api_key": "k", "base_url": "http://x/v1", "model": "m"},
    )
    session = app_runtime.chat.create_session(provider.id, "m", world_id=str(world.id))
    prompt = app_runtime.chat._build_system_prompt(str(world.id))
    assert "测试世界" in prompt
    assert "magic" in prompt


def test_character_profile_in_system_prompt(app_runtime, tmp_path) -> None:
    from novel_world.application.use_cases.create_world import CreateWorldUseCase
    from novel_world.core.domain.ids import WorldId

    world = CreateWorldUseCase(base_dir=tmp_path).execute("测试世界")
    factory = create_app(tmp_path)
    rt = factory.open_world(WorldId(str(world.id)))
    try:
        rt.character.create(
            WorldId(str(world.id)),
            "凌筱崎",
            role="主角",
            profile={"summary": "天才少女", "personality": "冷静"},
        )
        rt.session.commit()
    finally:
        rt.close()

    prompt = app_runtime.chat._build_system_prompt(str(world.id))
    assert "凌筱崎" in prompt
    assert "天才少女" in prompt
    assert "冷静" in prompt


def test_relationships_in_system_prompt(app_runtime, tmp_path) -> None:
    from novel_world.application.use_cases.create_world import CreateWorldUseCase
    from novel_world.core.domain.ids import WorldId

    world = CreateWorldUseCase(base_dir=tmp_path).execute("关系世界")
    factory = create_app(tmp_path)
    rt = factory.open_world(WorldId(str(world.id)))
    try:
        rt.character.create(WorldId(str(world.id)), "师傅", role="配角")
        rt.character.create(
            WorldId(str(world.id)),
            "徒弟",
            role="主角",
            metadata={"relationships": [{"target": "师傅", "type": "师徒", "note": "授业恩师"}]},
        )
        rt.session.commit()
    finally:
        rt.close()

    prompt = app_runtime.chat._build_system_prompt(str(world.id))
    assert "师徒" in prompt
    assert "授业恩师" in prompt


def test_empty_rules_settings_omitted_from_prompt(app_runtime, tmp_path) -> None:
    from novel_world.application.use_cases.create_world import CreateWorldUseCase

    world = CreateWorldUseCase(base_dir=tmp_path).execute("空设定世界", rules={}, settings={})
    prompt = app_runtime.chat._build_system_prompt(str(world.id))
    assert "规则：" not in prompt
    assert "设定：" not in prompt


class _StubClient:
    def __init__(self) -> None:
        self.last_messages = None
        self.summarize_count = 0

    def complete(self, messages, *, model, generation=None):
        self.summarize_count += 1
        return "前情摘要内容"

    def stream_complete(self, messages, *, model, generation=None):
        self.last_messages = messages
        from novel_world.modules.ai.ports.llm_provider import StreamChunk

        yield StreamChunk(kind="content", text="续写正文")
        yield StreamChunk(kind="done")


def test_continue_mode_injects_instruction(app_runtime) -> None:
    from novel_world.modules.ai.services.chat_service import CONTINUE_WRITING_INSTRUCTION

    provider = app_runtime.providers.create(
        "Mock", "openai_compatible", {"api_key": "k", "base_url": "http://x/v1", "model": "m"}
    )
    session = app_runtime.chat.create_session(provider.id, "m")
    stub = _StubClient()
    app_runtime.chat._providers.build_client = lambda pid: stub

    list(app_runtime.chat.stream_message(session.id, "", mode="continue"))
    app_runtime.commit()

    messages = app_runtime.chat.get_messages(session.id)
    assert CONTINUE_WRITING_INSTRUCTION in messages[0].content
    assert messages[-1].content == "续写正文"


def test_rolling_summary_compresses_history(app_runtime) -> None:
    provider = app_runtime.providers.create(
        "Mock", "openai_compatible", {"api_key": "k", "base_url": "http://x/v1", "model": "m"}
    )
    session = app_runtime.chat.create_session(provider.id, "m")
    stub = _StubClient()
    app_runtime.chat._providers.build_client = lambda pid: stub

    for i in range(20):
        list(app_runtime.chat.stream_message(session.id, f"第{i}条"))
    app_runtime.commit()

    refreshed = app_runtime.chat.get_session(session.id)
    assert refreshed.summary_content == "前情摘要内容"
    assert refreshed.summary_until > 0
    assert stub.summarize_count >= 1
    non_system = [m for m in stub.last_messages if m.role != "system"]
    assert len(non_system) <= 16
    assert any(m.role == "system" and "前情提要" in m.content for m in stub.last_messages)
