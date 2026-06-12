from __future__ import annotations

import json
from pathlib import Path

import pytest

from novel_world.application.use_cases.create_world import CreateWorldUseCase
from novel_world.bootstrap.app_context import create_app_context
from novel_world.bootstrap.app_factory import create_app
from novel_world.core.domain.ids import WorldId
from novel_world.infrastructure.user_preferences import get_user_prefs, save_user_prefs
from novel_world.modules.ai.services.session_lore_service import SessionLoreService
from novel_world.modules.ai.services.st_preset_codec import apply_preset_to_prefs, parse_st_preset
from novel_world.modules.ai.services.st_regex_codec import parse_st_regex_scripts
from novel_world.modules.character.domain.character_card import CARD_SPEC_V3, CharacterCard
from novel_world.modules.character.services.card_v3_codec import card_to_json_bytes


@pytest.fixture
def app_runtime(tmp_path: Path):
    ctx = create_app_context(tmp_path)
    runtime = ctx.open()
    yield runtime
    runtime.close()


def test_v3_card_import_flow(tmp_path: Path) -> None:
    world = CreateWorldUseCase(base_dir=tmp_path).execute("B档世界")
    factory = create_app(tmp_path)
    wrt = factory.open_world(WorldId(str(world.id)))
    try:
        card = CharacterCard(name="V3测试", first_mes="你好", card_spec=CARD_SPEC_V3)
        raw = card_to_json_bytes(card)
        from novel_world.modules.character.services.character_card_service import CharacterCardService
        from novel_world.infrastructure.repositories.sqlite_repositories import SqliteCharacterRepository

        svc = CharacterCardService(factory.config, SqliteCharacterRepository(wrt.session.connection))
        c = wrt.character.create(WorldId(str(world.id)), "占位", role="npc")
        wrt.session.commit()
        updated, _ = svc.import_card(WorldId(str(world.id)), c.id, raw, "card.json")
        assert updated.metadata["card"]["spec"] == CARD_SPEC_V3
    finally:
        wrt.close()


def test_session_lore_and_preset_profile(app_runtime, tmp_path: Path) -> None:
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
        provider.id, "m", world_id=str(world.id), character_id=str(c.id)
    )
    session, _ = SessionLoreService.import_st(
        session,
        json.dumps({"entries": {"0": {"keys": ["dragon"], "content": "Dragon"}}}).encode(),
    )
    app_runtime.roleplay.update_session_config(session.id, {"session_lore": session.config["session_lore"]})
    preset = parse_st_preset(
        {
            "temperature": 0.5,
            "prompts": [{"identifier": "main", "content": "ordered"}],
            "prompt_order": ["main"],
        }
    )
    app_runtime.roleplay.update_session_config(
        session.id,
        {
            "generation": preset["generation"],
            "prompt_layers": preset["prompt_layers"],
            "prompt_profile": preset["prompt_profile"],
        },
    )
    app_runtime.commit()
    updated = app_runtime.roleplay.get_session(session.id)
    assert len(updated.config.get("session_lore") or []) == 1
    assert updated.config.get("prompt_profile", {}).get("order") == ["main"]


def test_global_regex_in_prefs(app_runtime) -> None:
    scripts = parse_st_regex_scripts([{"scriptName": "t", "findRegex": "a", "replaceString": "b", "placement": [1]}])
    prefs = get_user_prefs(app_runtime.session.connection)
    save_user_prefs(
        app_runtime.session.connection,
        {**prefs, "global_regex_scripts": [s.to_dict() for s in scripts]},
    )
    app_runtime.commit()
    merged = get_user_prefs(app_runtime.session.connection)
    assert len(merged.get("global_regex_scripts") or []) == 1
