from __future__ import annotations

import json
from pathlib import Path
import pytest

from novel_world.infrastructure.user_preferences import get_user_prefs
from novel_world.launcher import mods_admin


@pytest.fixture
def mod_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    root = tmp_path / "proj"
    root.mkdir()
    (root / "pyproject.toml").write_text("[project]\nname='test'\n", encoding="utf-8")
    data = root / "data"
    mods = data / "mods"
    ext = data / "extensions"
    mods.mkdir(parents=True)
    ext.mkdir(parents=True)
    mod_root = mods / "toggle_me"
    mod_root.mkdir()
    (mod_root / "mod.json").write_text(
        json.dumps(
            {
                "id": "toggle_me",
                "name": "Toggle",
                "type": "python_hooks",
                "entry": "main.py",
            }
        ),
        encoding="utf-8",
    )
    (mod_root / "main.py").write_text("def register(hooks):\n    pass\n", encoding="utf-8")

    monkeypatch.setattr(mods_admin, "get_root", lambda: root)
    yield root


def test_list_mods_returns_discovered(mod_env: Path) -> None:
    res = mods_admin.list_mods()
    assert res["ok"]
    ids = [m["id"] for m in res["data"]["mods"]]
    assert "toggle_me" in ids


def test_set_mod_enabled_persists(mod_env: Path) -> None:
    off = mods_admin.set_mod_enabled("toggle_me", False)
    assert off["ok"]
    ctx = mods_admin._app_ctx()
    runtime = ctx.open()
    try:
        prefs = get_user_prefs(runtime.session.connection)
        assert "toggle_me" in prefs.get("disabled_extensions", [])
    finally:
        runtime.close()

    on = mods_admin.set_mod_enabled("toggle_me", True)
    assert on["ok"]
    runtime = ctx.open()
    try:
        prefs = get_user_prefs(runtime.session.connection)
        assert "toggle_me" not in prefs.get("disabled_extensions", [])
    finally:
        runtime.close()
