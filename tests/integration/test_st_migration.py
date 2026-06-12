from __future__ import annotations

import json
from pathlib import Path

import pytest

from novel_world.application.use_cases.create_world import CreateWorldUseCase
from novel_world.bootstrap.app_context import create_app_context
from novel_world.bootstrap.app_factory import create_app
from novel_world.core.domain.ids import WorldId
from novel_world.infrastructure.repositories.sqlite_lore_repository import SqliteLoreRepository
from novel_world.infrastructure.user_preferences import get_user_prefs
from novel_world.modules.ai.services.lore_engine import LoreEngine
from novel_world.modules.ai.services.st_preset_codec import apply_preset_to_prefs, parse_st_preset
from novel_world.modules.world.services.lore_service import LoreService


@pytest.fixture
def app_runtime(tmp_path: Path):
    ctx = create_app_context(tmp_path)
    runtime = ctx.open()
    yield runtime
    runtime.close()


def test_import_world_info_then_scan(tmp_path: Path) -> None:
    world = CreateWorldUseCase(base_dir=tmp_path).execute("ST世界")
    factory = create_app(tmp_path)
    wrt = factory.open_world(WorldId(str(world.id)))
    try:
        wi = {
            "entries": {
                "0": {"keys": ["dragon"], "content": "Dragon appears in the sky", "priority": 10},
            }
        }
        lore_svc = LoreService(SqliteLoreRepository(wrt.session.connection))
        count = lore_svc.import_st_world_info(
            json.dumps(wi).encode("utf-8"),
            scope="world",
            mode="merge",
        )
        wrt.session.commit()
        assert count == 1

        entries = lore_svc.list_entries(include_disabled=True)
        result = LoreEngine().scan(entries, "I saw a dragon today", token_budget=2000)
        assert result.matched_ids
        assert "Dragon" in "\n".join(result.before_main)
    finally:
        wrt.close()


def test_preset_to_session_config(app_runtime, tmp_path: Path) -> None:
    world = CreateWorldUseCase(base_dir=tmp_path).execute("Preset世界")
    factory = create_app(tmp_path)
    wrt = factory.open_world(WorldId(str(world.id)))
    try:
        c = wrt.character.create(WorldId(str(world.id)), "角色", profile={"first_mes": "hi"})
        wrt.session.commit()
    finally:
        wrt.close()

    provider = app_runtime.providers.create(
        "Mock", "openai_compatible", {"api_key": "k", "base_url": "http://x/v1", "model": "m"}
    )
    session = app_runtime.roleplay.create_session(
        provider.id,
        "m",
        world_id=str(world.id),
        character_id=str(c.id),
    )
    preset = parse_st_preset(
        {
            "temperature": 0.42,
            "prompts": [{"identifier": "main", "content": "Imported main"}],
        }
    )
    app_runtime.roleplay.update_session_config(
        session.id,
        {
            "generation": preset["generation"],
            "prompt_layers": preset["prompt_layers"],
        },
    )
    app_runtime.commit()

    updated = app_runtime.roleplay.get_session(session.id)
    assert updated.config["generation"]["temperature"] == 0.42
    assert updated.config["prompt_layers"]["main"] == "Imported main"


def test_alternate_greeting_switch(app_runtime, tmp_path: Path) -> None:
    world = CreateWorldUseCase(base_dir=tmp_path).execute("Greeting世界")
    factory = create_app(tmp_path)
    wrt = factory.open_world(WorldId(str(world.id)))
    try:
        c = wrt.character.create(
            WorldId(str(world.id)),
            "角色",
            profile={
                "first_mes": "开场一",
                "alternate_greetings": ["开场二", "开场三"],
            },
        )
        wrt.session.commit()
    finally:
        wrt.close()

    provider = app_runtime.providers.create(
        "Mock", "openai_compatible", {"api_key": "k", "base_url": "http://x/v1", "model": "m"}
    )
    session = app_runtime.roleplay.create_session(
        provider.id,
        "m",
        world_id=str(world.id),
        character_id=str(c.id),
    )
    messages = app_runtime.roleplay.get_messages(session.id)
    assert messages[0].content == "开场一"

    app_runtime.roleplay.set_greeting_index(session.id, 2)
    app_runtime.commit()
    messages = app_runtime.roleplay.get_messages(session.id)
    assert messages[0].content == "开场三"
    cfg = app_runtime.roleplay.get_session(session.id).config
    assert cfg["greeting_index"] == 2


def test_apply_preset_to_user_prefs(app_runtime) -> None:
    preset = parse_st_preset({"temperature": 0.33, "prompts": []})
    existing = get_user_prefs(app_runtime.session.connection)
    merged = apply_preset_to_prefs(existing, preset)
    assert merged["default_generation"]["temperature"] == 0.33
