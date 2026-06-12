from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from novel_world.bootstrap.app_context import create_app_context
from novel_world.infrastructure.repositories.sqlite_chat_repository import new_stored_message
from novel_world.modules.ai.ports.llm_provider import StreamChunk


@pytest.fixture
def app_runtime(tmp_path: Path):
    ctx = create_app_context(tmp_path)
    runtime = ctx.open()
    yield runtime
    runtime.close()


class _StubClient:
    def stream_complete(self, messages, *, model, generation=None):
        yield StreamChunk(kind="content", text="新回复")
        yield StreamChunk(kind="done")

    def complete(self, messages, *, model, generation=None):
        return "摘要"


def test_message_edit_and_delete(app_runtime) -> None:
    provider = app_runtime.providers.create(
        "Mock", "openai_compatible", {"api_key": "k", "base_url": "http://x/v1", "model": "m"}
    )
    session = app_runtime.chat.create_session(provider.id, "m")
    app_runtime.chat._chat_repo.append_message(
        new_stored_message(session.id, "user", "hello")
    )
    assistant = new_stored_message(session.id, "assistant", "old reply")
    app_runtime.chat._chat_repo.append_message(assistant)
    app_runtime.commit()

    updated = app_runtime.message_ops.edit(session.id, assistant.id, "edited reply")
    app_runtime.commit()
    assert updated.content == "edited reply"

    app_runtime.message_ops.delete(session.id, assistant.id)
    app_runtime.commit()
    msgs = app_runtime.chat.get_messages(session.id)
    assert len(msgs) == 1


def test_message_swipe_variants(app_runtime) -> None:
    provider = app_runtime.providers.create(
        "Mock", "openai_compatible", {"api_key": "k", "base_url": "http://x/v1", "model": "m"}
    )
    session = app_runtime.chat.create_session(provider.id, "m")
    msg = new_stored_message(session.id, "assistant", "current")
    msg.variants = [
        {"content": "variant A", "thinking_content": ""},
        {"content": "variant B", "thinking_content": ""},
    ]
    msg.active_variant = 0
    msg.content = "variant A"
    app_runtime.chat._chat_repo.append_message(msg)
    app_runtime.commit()

    swapped = app_runtime.message_ops.swipe(session.id, msg.id, direction="next")
    app_runtime.commit()
    assert swapped.content == "variant B"


def test_regenerate_stream(app_runtime) -> None:
    provider = app_runtime.providers.create(
        "Mock", "openai_compatible", {"api_key": "k", "base_url": "http://x/v1", "model": "m"}
    )
    session = app_runtime.chat.create_session(provider.id, "m")
    app_runtime.chat._chat_repo.append_message(new_stored_message(session.id, "user", "hi"))
    assistant = new_stored_message(session.id, "assistant", "bye")
    app_runtime.chat._chat_repo.append_message(assistant)
    app_runtime.commit()

    app_runtime.chat._providers.build_client = lambda pid: _StubClient()
    chunks = list(app_runtime.message_ops.regenerate(session.id, assistant.id))
    app_runtime.commit()
    assert any(c.kind == "content" for c in chunks)
