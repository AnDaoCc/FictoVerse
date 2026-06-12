from __future__ import annotations

import json
import zipfile
from io import BytesIO
from pathlib import Path

import pytest

from novel_world.modules.extensions.hook_bus import clear_hooks, run_hooks
from novel_world.modules.ai.services.command_parser import parse_command
from novel_world.modules.extensions.mod_registry import (
    check_compatibility,
    discover_mods,
    get_enabled_frontend_assets,
    install_mod_zip,
    load_mods,
    resolve_mod_asset_path,
    uninstall_mod,
    validate_manifest,
)


@pytest.fixture(autouse=True)
def _clear_hooks():
    clear_hooks()
    yield
    clear_hooks()


def test_validate_manifest_requires_id_and_name() -> None:
    errors = validate_manifest({"type": "python_hooks"})
    assert "缺少 id" in errors
    assert "缺少 name" in errors


def test_check_compatibility_rejects_high_api_version() -> None:
    ok, err = check_compatibility(
        {
            "id": "x",
            "name": "X",
            "type": "python_hooks",
            "mod_api_version": 99,
            "min_app_version": "0",
        }
    )
    assert not ok
    assert err and "MOD API" in err


def test_discover_mods_folder_and_legacy(tmp_path: Path) -> None:
    mods_dir = tmp_path / "data" / "mods"
    ext_dir = tmp_path / "data" / "extensions"
    mods_dir.mkdir(parents=True)
    ext_dir.mkdir(parents=True)

    mod_root = mods_dir / "sample_mod"
    mod_root.mkdir()
    (mod_root / "mod.json").write_text(
        json.dumps(
            {
                "id": "sample_mod",
                "name": "Sample",
                "type": "python_hooks",
                "entry": "main.py",
            }
        ),
        encoding="utf-8",
    )
    (mod_root / "main.py").write_text(
        'def register(hooks):\n    hooks.register_hook("display.transform", lambda t, **k: t)\n',
        encoding="utf-8",
    )
    (ext_dir / "legacy_ext.py").write_text(
        'def register(hooks):\n    pass\n',
        encoding="utf-8",
    )

    records = discover_mods(ext_dir, mods_dir)
    ids = {r["id"] for r in records}
    assert "sample_mod" in ids
    assert "legacy_ext" in ids


def test_load_mods_runs_hook(tmp_path: Path) -> None:
    mods_dir = tmp_path / "data" / "mods"
    ext_dir = tmp_path / "data" / "extensions"
    mods_dir.mkdir(parents=True)
    ext_dir.mkdir(parents=True)

    mod_root = mods_dir / "upper"
    mod_root.mkdir()
    (mod_root / "mod.json").write_text(
        json.dumps(
            {
                "id": "upper",
                "name": "Upper",
                "type": "python_hooks",
                "entry": "main.py",
            }
        ),
        encoding="utf-8",
    )
    (mod_root / "main.py").write_text(
        'def register(hooks):\n    hooks.register_hook("display.transform", lambda t, **k: (t or "").upper())\n',
        encoding="utf-8",
    )

    records = load_mods(ext_dir, mods_dir)
    assert any(r["id"] == "upper" and r["status"] == "ok" for r in records)
    assert run_hooks("display.transform", "hi") == "HI"


def test_register_command_via_mod(tmp_path: Path) -> None:
    mods_dir = tmp_path / "data" / "mods"
    ext_dir = tmp_path / "data" / "extensions"
    mods_dir.mkdir(parents=True)
    ext_dir.mkdir(parents=True)
    mod_root = mods_dir / "cmd_mod"
    mod_root.mkdir()
    (mod_root / "mod.json").write_text(
        json.dumps(
            {
                "id": "cmd_mod",
                "name": "Cmd",
                "type": "python_hooks",
                "entry": "main.py",
            }
        ),
        encoding="utf-8",
    )
    (mod_root / "main.py").write_text(
        "def register(hooks):\n"
        "    def handler(arg, ctx):\n"
        "        return True, f'CMD:{arg}'\n"
        "    hooks.register_command('hello', handler)\n",
        encoding="utf-8",
    )
    load_mods(ext_dir, mods_dir)
    handled, remainder = parse_command("/hello world", {})
    assert handled
    assert remainder == "CMD:world"


def test_frontend_assets_and_resolve_path(tmp_path: Path) -> None:
    mods_dir = tmp_path / "data" / "mods"
    ext_dir = tmp_path / "data" / "extensions"
    mod_root = mods_dir / "ui_mod"
    mod_root.mkdir(parents=True)
    (mod_root / "mod.json").write_text(
        json.dumps(
            {
                "id": "ui_mod",
                "name": "UI",
                "type": "frontend",
                "assets": {"js": ["mod.js"], "css": ["mod.css"]},
            }
        ),
        encoding="utf-8",
    )
    (mod_root / "mod.js").write_text("// js", encoding="utf-8")
    records = discover_mods(ext_dir, mods_dir)
    assets = get_enabled_frontend_assets(records)
    assert assets and assets[0]["id"] == "ui_mod"
    resolved = resolve_mod_asset_path(mods_dir, "ui_mod", "mod.js")
    assert resolved and resolved.is_file()
    assert resolve_mod_asset_path(mods_dir, "ui_mod", "../secret") is None


def test_install_and_uninstall_mod_zip(tmp_path: Path) -> None:
    mods_dir = tmp_path / "data" / "mods"
    mods_dir.mkdir(parents=True)
    buf = BytesIO()
    manifest = {
        "id": "zip_mod",
        "name": "Zip Mod",
        "type": "frontend",
        "assets": {"js": ["mod.js"]},
    }
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("mod.json", json.dumps(manifest))
        zf.writestr("mod.js", "// demo")
    result = install_mod_zip(mods_dir, buf.getvalue())
    assert result.get("ok")
    assert (mods_dir / "zip_mod" / "mod.json").is_file()
    removed = uninstall_mod(mods_dir, "zip_mod")
    assert removed.get("ok")
    assert not (mods_dir / "zip_mod").exists()
