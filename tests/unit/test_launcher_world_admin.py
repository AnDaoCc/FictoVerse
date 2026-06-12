from __future__ import annotations

from pathlib import Path

from novel_world.launcher import world_admin


def _setup_root(tmp_path: Path, monkeypatch) -> Path:
    root = tmp_path / "proj"
    root.mkdir()
    (root / "pyproject.toml").write_text("[project]\nname='test'\n", encoding="utf-8")
    (root / "data").mkdir()
    monkeypatch.setattr(world_admin, "get_root", lambda: root)
    return root


def test_world_admin_crud(tmp_path: Path, monkeypatch) -> None:
    _setup_root(tmp_path, monkeypatch)

    created = world_admin.create_world("测试世界", description="简介", genre="奇幻")
    assert created["ok"] is True
    world_id = created["data"]["id"]

    listed = world_admin.list_worlds()
    assert listed["ok"] is True
    assert any(w["id"] == world_id for w in listed["data"])

    detail = world_admin.get_world(world_id)
    assert detail["ok"] is True
    assert detail["data"]["name"] == "测试世界"
    assert detail["data"]["description"] == "简介"

    updated = world_admin.update_world(
        world_id,
        "新名称",
        description="新简介",
        genre="科幻",
        rules_json='{"a":1}',
        settings_json='{"b":2}',
    )
    assert updated["ok"] is True

    persona = world_admin.update_world_user_persona(
        world_id, persona_name="旅人", persona_description="来自远方"
    )
    assert persona["ok"] is True

    again = world_admin.get_world(world_id)
    assert again["data"]["name"] == "新名称"
    assert again["data"]["user_persona"]["name"] == "旅人"

    char = world_admin.create_character(
        world_id,
        {"name": "艾拉", "role": "npc", "summary": "向导", "personality": "冷静"},
    )
    assert char["ok"] is True
    char_id = char["data"]["id"]

    detail2 = world_admin.get_world(world_id)
    assert len(detail2["data"]["characters"]) == 1

    saved = world_admin.update_character(
        world_id,
        char_id,
        {"name": "艾拉·修订", "role": "npc", "summary": "老向导"},
    )
    assert saved["ok"] is True
    assert saved["data"]["name"] == "艾拉·修订"

    lore = world_admin.create_lore_entry(
        world_id,
        {"keys": "城门,入口", "content": "古老的石门", "scope": "world"},
    )
    assert lore["ok"] is True

    state = world_admin.set_state(world_id, "weather", '"晴"', scope="world")
    assert state["ok"] is True

    deleted_char = world_admin.delete_character(world_id, char_id)
    assert deleted_char["ok"] is True

    deleted = world_admin.delete_world(world_id)
    assert deleted["ok"] is True

    listed2 = world_admin.list_worlds()
    assert not any(w["id"] == world_id for w in listed2["data"])
