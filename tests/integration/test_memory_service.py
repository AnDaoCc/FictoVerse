from __future__ import annotations

from pathlib import Path

import pytest

from novel_world.bootstrap.app_context import create_app_context


@pytest.fixture
def app_runtime(tmp_path: Path):
    ctx = create_app_context(tmp_path)
    runtime = ctx.open()
    yield runtime
    runtime.close()


def test_pin_and_list_memory(app_runtime) -> None:
    provider = app_runtime.providers.create(
        "Mock", "openai_compatible", {"api_key": "k", "base_url": "http://x/v1", "model": "m"}
    )
    session = app_runtime.chat.create_session(provider.id, "m")
    mem = app_runtime.memory.pin(session.id, "用户喜欢猫", keywords=["猫"], pinned=True)
    app_runtime.commit()

    items = app_runtime.memory.list(session.id)
    assert len(items) == 1
    assert items[0].id == mem.id
    assert items[0].pinned


def test_select_for_prompt_keyword_and_pinned(app_runtime) -> None:
    provider = app_runtime.providers.create(
        "Mock", "openai_compatible", {"api_key": "k", "base_url": "http://x/v1", "model": "m"}
    )
    session = app_runtime.chat.create_session(provider.id, "m")
    app_runtime.memory.pin(session.id, "Pinned fact", pinned=True)
    app_runtime.memory.pin(session.id, "Dragon weakness", keywords=["dragon"], pinned=False)
    app_runtime.commit()

    block, lines = app_runtime.memory.select_for_prompt(session.id, "a dragon appears")
    assert "Pinned fact" in block
    assert "Dragon weakness" in block
    assert len(lines) >= 2


def test_set_pinned_toggle(app_runtime) -> None:
    provider = app_runtime.providers.create(
        "Mock", "openai_compatible", {"api_key": "k", "base_url": "http://x/v1", "model": "m"}
    )
    session = app_runtime.chat.create_session(provider.id, "m")
    mem = app_runtime.memory.pin(session.id, "toggle me", pinned=True)
    app_runtime.commit()

    updated = app_runtime.memory.set_pinned(mem.id, pinned=False)
    assert updated.pinned is False
    items = app_runtime.memory.list(session.id, pinned_only=True)
    assert not items

    app_runtime.memory.set_pinned(mem.id, pinned=True)
    items = app_runtime.memory.list(session.id, pinned_only=True)
    assert len(items) == 1
