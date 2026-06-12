from __future__ import annotations



from pathlib import Path



import pytest



from novel_world.application.use_cases.create_world import CreateWorldUseCase

from novel_world.bootstrap.app_context import create_app_context

from novel_world.bootstrap.app_factory import create_app

from novel_world.core.domain.ids import WorldId

from novel_world.modules.extensions.hook_bus import clear_hooks, register_hook, run_hooks

from novel_world.modules.world.services.world_pack_service import WorldPackService





@pytest.fixture

def app_runtime(tmp_path: Path):

    ext_dir = tmp_path / "data" / "extensions"

    ext_dir.mkdir(parents=True)

    (ext_dir / "sample.py").write_text(

        'def register(hooks):\n    hooks.register_hook("display.transform", lambda t, **k: t.upper())\n',

        encoding="utf-8",

    )

    ctx = create_app_context(tmp_path)

    runtime = ctx.open()

    yield runtime

    runtime.close()

    clear_hooks()





def test_hook_bus_runs_by_priority() -> None:

    clear_hooks()

    register_hook("test.hook", lambda v, **_: v + "b", priority=200)

    register_hook("test.hook", lambda v, **_: v + "a", priority=100)

    assert run_hooks("test.hook", "") == "ab"

    clear_hooks()





def test_group_add_remove_members(app_runtime, tmp_path) -> None:

    world = CreateWorldUseCase(base_dir=tmp_path).execute("测试世界")

    factory = create_app(tmp_path)

    rt = factory.open_world(WorldId(str(world.id)))

    try:

        c1 = rt.character.create(WorldId(str(world.id)), "角色A", role="主角")

        c2 = rt.character.create(WorldId(str(world.id)), "角色B", role="配角")

        c3 = rt.character.create(WorldId(str(world.id)), "角色C", role="配角")

        rt.session.commit()

    finally:

        rt.close()



    provider = app_runtime.providers.create(

        "Mock", "openai_compatible", {"api_key": "k", "base_url": "http://x/v1", "model": "m"}

    )

    session = app_runtime.group_chat.create_group(
        provider.id,
        "m",
        title="测试群",
        members=[

            {"world_id": str(world.id), "character_id": str(c1.id)},

            {"world_id": str(world.id), "character_id": str(c2.id)},

        ],

    )

    app_runtime.group_chat.add_members(

        session.id, [{"world_id": str(world.id), "character_id": str(c3.id)}]

    )

    members = app_runtime.group_chat.get_members(session.id)

    assert len(members) == 3



    app_runtime.group_chat.remove_member(session.id, str(world.id), str(c3.id))

    members = app_runtime.group_chat.get_members(session.id)

    assert len(members) == 2

    app_runtime.commit()





def test_mod_folder_loads(tmp_path: Path) -> None:
    mods_dir = tmp_path / "data" / "mods" / "folder_mod"
    mods_dir.mkdir(parents=True)
    (mods_dir / "mod.json").write_text(
        '{"id":"folder_mod","name":"Folder","type":"python_hooks","entry":"main.py"}',
        encoding="utf-8",
    )
    (mods_dir / "main.py").write_text(
        'def register(hooks):\n    hooks.register_hook("display.transform", lambda t, **k: t + "!")\n',
        encoding="utf-8",
    )
    ctx = create_app_context(tmp_path)
    runtime = ctx.open()
    try:
        assert any(e["id"] == "folder_mod" and e["status"] == "ok" for e in runtime.extensions)
        assert run_hooks("display.transform", "x") == "x!"
    finally:
        runtime.close()
        clear_hooks()


def test_world_pack_roundtrip(tmp_path: Path) -> None:

    world = CreateWorldUseCase(base_dir=tmp_path).execute("导出世界")

    factory = create_app(tmp_path)

    svc = WorldPackService(factory.config, factory)

    pack = svc.export_world(str(world.id), include_uploads=False)

    imported = svc.import_world(pack, new_world_id=f"{world.id}_copy")

    assert imported["world_id"] == f"{world.id}_copy"

    assert (factory.config.world_db_path(f"{world.id}_copy")).is_file()

