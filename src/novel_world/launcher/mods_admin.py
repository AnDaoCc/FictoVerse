"""启动器 MOD 管理：直连本地数据库，与 Web 设置页能力对齐。"""

from __future__ import annotations

import base64
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from novel_world.bootstrap.app_context import create_app_context
from novel_world.infrastructure.user_preferences import get_user_prefs, save_user_prefs
from novel_world.launcher.bootstrap import get_root
from novel_world.modules.extensions.hook_catalog import hook_catalog_for_ui
from novel_world.modules.extensions.mod_registry import (
    discover_mods,
    install_mod_zip,
    load_mods,
    uninstall_mod,
)


def _ok(data: Any = None, message: str = "") -> dict[str, Any]:
    out: dict[str, Any] = {"ok": True}
    if message:
        out["message"] = message
    if data is not None:
        out["data"] = data
    return out


def _err(message: str) -> dict[str, Any]:
    return {"ok": False, "message": message}


def _app_ctx():
    return create_app_context(get_root())


def _public_mod(rec: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": rec.get("id"),
        "name": rec.get("name"),
        "type": rec.get("type"),
        "version": rec.get("version"),
        "description": rec.get("description"),
        "author": rec.get("author"),
        "status": rec.get("status"),
        "error": rec.get("error"),
        "enabled": rec.get("enabled", False),
        "hooks_registered": rec.get("hooks_registered") or [],
        "path": rec.get("path"),
        "builtin": bool(rec.get("builtin")),
        "legacy": bool(rec.get("legacy")),
        "source": rec.get("source"),
    }


def list_mods(*, reload: bool = False) -> dict[str, Any]:
    ctx = _app_ctx()
    runtime = ctx.open()
    try:
        prefs = get_user_prefs(runtime.session.connection)
        disabled = list(prefs.get("disabled_extensions") or [])
        config = runtime.config
        if reload:
            records = load_mods(
                config.extensions_dir,
                config.mods_dir,
                disabled=disabled,
                world_packs_dir=config.world_packs_dir,
            )
        else:
            records = discover_mods(
                config.extensions_dir,
                config.mods_dir,
                world_packs_dir=config.world_packs_dir,
            )
            disabled_set = set(disabled)
            for rec in records:
                if rec["id"] in disabled_set:
                    if rec["status"] == "ok":
                        rec["status"] = "disabled"
                    rec["enabled"] = False
                else:
                    rec["enabled"] = rec["status"] == "ok"
        return _ok(
            {
                "mods": [_public_mod(r) for r in records],
                "mods_dir": str(config.mods_dir),
                "extensions_dir": str(config.extensions_dir),
                "hook_catalog": hook_catalog_for_ui(),
            }
        )
    finally:
        runtime.close()


def set_mod_enabled(mod_id: str, enabled: bool) -> dict[str, Any]:
    mod_id = (mod_id or "").strip()
    if not mod_id:
        return _err("缺少 MOD id")
    ctx = _app_ctx()
    runtime = ctx.open()
    try:
        config = runtime.config
        records = discover_mods(
            config.extensions_dir,
            config.mods_dir,
            world_packs_dir=config.world_packs_dir,
        )
        known = {r["id"] for r in records}
        if mod_id not in known:
            return _err("MOD 不存在")
        prefs = get_user_prefs(runtime.session.connection)
        disabled = list(prefs.get("disabled_extensions") or [])
        disabled_set = set(disabled)
        if enabled:
            disabled_set.discard(mod_id)
        else:
            disabled_set.add(mod_id)
        save_user_prefs(
            runtime.session.connection,
            {**prefs, "disabled_extensions": sorted(disabled_set)},
        )
        runtime.commit()
        return _ok(message="已保存 MOD 开关")
    finally:
        runtime.close()


def open_mods_directory() -> dict[str, Any]:
    ctx = _app_ctx()
    runtime = ctx.open()
    try:
        path = runtime.config.mods_dir
        path.mkdir(parents=True, exist_ok=True)
        ok, msg = _open_folder(path)
        if ok:
            return _ok(message=msg)
        return _err(msg)
    finally:
        runtime.close()


def install_mod_zip_file(filename: str, data_b64: str) -> dict[str, Any]:
    try:
        data = base64.b64decode(data_b64 or "")
    except Exception as exc:
        return _err(f"数据解码失败：{exc}")
    if not data:
        return _err("空文件")
    ctx = _app_ctx()
    runtime = ctx.open()
    try:
        result = install_mod_zip(runtime.config.mods_dir, data, filename=filename or "")
        if not result.get("ok"):
            return _err(str(result.get("message") or "安装失败"))
        return _ok({"id": result.get("id")}, message=str(result.get("message") or "已安装"))
    finally:
        runtime.close()


def uninstall_mod_by_id(mod_id: str) -> dict[str, Any]:
    ctx = _app_ctx()
    runtime = ctx.open()
    try:
        result = uninstall_mod(runtime.config.mods_dir, (mod_id or "").strip())
        if not result.get("ok"):
            return _err(str(result.get("message") or "卸载失败"))
        return _ok(message=str(result.get("message") or "已卸载"))
    finally:
        runtime.close()


def _open_folder(path: Path) -> tuple[bool, str]:
    try:
        if sys.platform == "win32":
            os.startfile(str(path))  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.run(["open", str(path)], check=False)
        else:
            subprocess.run(["xdg-open", str(path)], check=False)
        return True, f"已打开：{path}"
    except Exception as exc:
        return False, f"无法打开目录：{exc}"
