from __future__ import annotations

import json
from pathlib import Path

import pytest

from novel_world.application.use_cases.create_world import CreateWorldUseCase
from novel_world.bootstrap.app_context import create_app_context
from novel_world.bootstrap.app_factory import create_app
from novel_world.core.domain.ids import WorldId
from novel_world.infrastructure.user_preferences import get_user_prefs, save_user_prefs
from novel_world.modules.stscript.engine import parse_st_scripts_json


@pytest.fixture
def app_runtime(tmp_path: Path):
    ctx = create_app_context(tmp_path)
    runtime = ctx.open()
    yield runtime
    runtime.close()


def test_stscript_in_prefs(app_runtime) -> None:
    scripts = parse_st_scripts_json([{"name": "t", "content": "/echo x", "triggers": ["send"]}])
    prefs = get_user_prefs(app_runtime.session.connection)
    save_user_prefs(
        app_runtime.session.connection,
        {
            **prefs,
            "global_stscripts": [
                {"name": s.name, "content": s.content, "triggers": s.triggers, "enabled": True}
                for s in scripts
            ],
        },
    )
    app_runtime.commit()
    merged = get_user_prefs(app_runtime.session.connection)
    assert len(merged.get("global_stscripts") or []) == 1


def test_data_bank_world_flow(tmp_path: Path) -> None:
    world = CreateWorldUseCase(base_dir=tmp_path).execute("C档世界")
    factory = create_app(tmp_path)
    rt = factory.open_world(WorldId(str(world.id)))
    try:
        from novel_world.modules.world.services.data_bank_service import DataBankService

        svc = DataBankService(rt.session.connection)
        svc.index_text(world_id=str(world.id), title="设定", content="北方有龙。")
        rt.session.commit()
        hits = svc.search(str(world.id), "北方有龙", min_score=0.0)
        assert hits
    finally:
        rt.close()
