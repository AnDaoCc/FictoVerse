from __future__ import annotations

from pathlib import Path

import pytest

from novel_world.application.use_cases.create_world import CreateWorldUseCase
from novel_world.application.use_cases.world_ops import CreateSaveUseCase, LoadSaveUseCase
from novel_world.bootstrap.app_factory import create_app


@pytest.fixture
def project_root(tmp_path: Path) -> Path:
    return tmp_path


def test_create_world_and_persist(project_root: Path) -> None:
    world = CreateWorldUseCase(base_dir=project_root).execute(
        "测试世界",
        description="一个用于测试的世界",
        genre="玄幻",
        rules={"magic": "允许"},
    )
    app = create_app(project_root)
    runtime = app.open_world(world.id)
    try:
        loaded = runtime.world.get(world.id)
        assert loaded.name == "测试世界"
        assert loaded.rules["magic"] == "允许"
        assert runtime.state.get_value(world.id, "time.current") == "故事尚未开始"
        events = runtime.event.list_by_world(world.id)
        assert len(events) == 1
        assert events[0].event_type == "system.world_created"
    finally:
        runtime.close()


def test_save_and_load_roundtrip(project_root: Path) -> None:
    world = CreateWorldUseCase(base_dir=project_root).execute("存档测试")
    app = create_app(project_root)

    runtime = app.open_world(world.id)
    try:
        hero = runtime.character.create(world.id, "主角", role="protagonist")
        runtime.state.set_value(world.id, "time.current", "第三天", scope="world")
        runtime.state.set_value(
            world.id,
            "location.current",
            "客栈",
            scope="character",
            scope_id=hero.id,
        )
        runtime.event.record(
            world.id,
            "character.arrived",
            payload={"place": "客栈"},
            actor_id=hero.id,
        )
        runtime.commit()
    finally:
        runtime.close()

    slot = CreateSaveUseCase(base_dir=project_root).execute(world.id, slot_index=0, label="测试存档")

    runtime = app.open_world(world.id)
    try:
        runtime.state.set_value(world.id, "time.current", "被改掉的时间", scope="world")
        runtime.commit()
    finally:
        runtime.close()

    LoadSaveUseCase(base_dir=project_root).execute(world.id, slot.id)

    runtime = app.open_world(world.id)
    try:
        assert runtime.state.get_value(world.id, "time.current") == "第三天"
        characters = runtime.character.list_by_world(world.id)
        assert len(characters) == 1
        assert characters[0].name == "主角"
        events = runtime.event.list_by_world(world.id)
        assert len(events) == 2
        assert events[-1].event_type == "character.arrived"
    finally:
        runtime.close()
