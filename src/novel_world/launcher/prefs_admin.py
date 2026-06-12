"""启动器用户偏好管理（与 Web 设置页对齐）。"""

from __future__ import annotations

import base64
from typing import Any

from novel_world.bootstrap.app_context import create_app_context
from novel_world.infrastructure.user_preferences import get_user_prefs, save_user_prefs
from novel_world.launcher.bootstrap import get_root
from novel_world.modules.ai.services.st_preset_codec import apply_preset_to_prefs, parse_st_preset
from novel_world.modules.ai.services.st_regex_codec import parse_st_regex_scripts
from novel_world.modules.stscript.engine import parse_st_scripts_json


def _ok(message: str = "", **extra: Any) -> dict[str, Any]:
    out: dict[str, Any] = {"ok": True}
    if message:
        out["message"] = message
    out.update(extra)
    return out


def _err(message: str) -> dict[str, Any]:
    return {"ok": False, "message": message}


def import_st_preset(filename: str, data_b64: str) -> dict[str, Any]:
    try:
        data = base64.b64decode(data_b64)
    except Exception as exc:
        return _err(f"预设文件解码失败：{exc}")
    try:
        preset = parse_st_preset(data)
    except Exception as exc:
        return _err(str(exc))

    ctx = create_app_context(get_root())
    runtime = ctx.open()
    try:
        existing = get_user_prefs(runtime.session.connection)
        save_user_prefs(
            runtime.session.connection,
            apply_preset_to_prefs(existing, preset),
        )
        runtime.commit()
    finally:
        runtime.close()

    name = preset.get("name") or filename or "preset"
    return _ok(message=f"已导入预设「{name}」为全局默认。", name=name)


def import_st_regex(filename: str, data_b64: str) -> dict[str, Any]:
    try:
        data = base64.b64decode(data_b64)
    except Exception as exc:
        return _err(f"Regex 文件解码失败：{exc}")
    try:
        scripts = parse_st_regex_scripts(data)
    except Exception as exc:
        return _err(str(exc))

    ctx = create_app_context(get_root())
    runtime = ctx.open()
    try:
        existing = get_user_prefs(runtime.session.connection)
        merged = dict(existing)
        merged["global_regex_scripts"] = [s.to_dict() for s in scripts]
        save_user_prefs(runtime.session.connection, merged)
        runtime.commit()
    finally:
        runtime.close()

    return _ok(message=f"已导入 {len(scripts)} 条全局 Regex 脚本。", count=len(scripts))


def import_st_stscript(filename: str, data_b64: str) -> dict[str, Any]:
    try:
        data = base64.b64decode(data_b64)
    except Exception as exc:
        return _err(f"STscript 文件解码失败：{exc}")
    try:
        scripts = parse_st_scripts_json(data)
    except Exception as exc:
        return _err(str(exc))

    ctx = create_app_context(get_root())
    runtime = ctx.open()
    try:
        existing = get_user_prefs(runtime.session.connection)
        merged = dict(existing)
        merged["global_stscripts"] = [
            {"name": s.name, "content": s.content, "triggers": s.triggers, "enabled": s.enabled}
            for s in scripts
        ]
        save_user_prefs(runtime.session.connection, merged)
        runtime.commit()
    finally:
        runtime.close()

    return _ok(message=f"已导入 {len(scripts)} 条 STscript。", count=len(scripts))
