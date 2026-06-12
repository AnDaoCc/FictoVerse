from __future__ import annotations

import importlib.util
import json
import re
import shutil
import sys
import zipfile
from io import BytesIO
from pathlib import Path
from typing import Any

from novel_world import __version__ as APP_VERSION
from novel_world.modules.extensions import hook_bus
from novel_world.modules.extensions.hook_catalog import MOD_API_VERSION, MOD_TYPES

def _parse_version(text: str) -> tuple[int, ...]:
    parts = re.findall(r"\d+", (text or "0").strip())
    return tuple(int(p) for p in parts) if parts else (0,)


def version_gte(current: str, minimum: str) -> bool:
    cur = _parse_version(current)
    min_v = _parse_version(minimum)
    length = max(len(cur), len(min_v))
    cur_padded = cur + (0,) * (length - len(cur))
    min_padded = min_v + (0,) * (length - len(min_v))
    return cur_padded >= min_padded


def validate_manifest(manifest: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if not isinstance(manifest, dict):
        return ["manifest 必须为 JSON 对象"]
    mod_id = str(manifest.get("id") or "").strip()
    if not mod_id:
        errors.append("缺少 id")
    elif not re.fullmatch(r"[a-zA-Z0-9_-]+", mod_id):
        errors.append("id 仅允许字母、数字、下划线与连字符")
    name = str(manifest.get("name") or "").strip()
    if not name:
        errors.append("缺少 name")
    mod_type = str(manifest.get("type") or "python_hooks").strip()
    if mod_type not in MOD_TYPES:
        errors.append(f"type 无效，允许：{', '.join(MOD_TYPES)}")
    try:
        api_ver = int(manifest.get("mod_api_version", 1))
    except (TypeError, ValueError):
        errors.append("mod_api_version 必须为整数")
        api_ver = 1
    else:
        if api_ver < 1:
            errors.append("mod_api_version 必须 >= 1")
    if mod_type in ("python_hooks", "composite") and not str(manifest.get("entry") or "main.py").strip():
        errors.append("python_hooks/composite 需要 entry 字段")
    return errors


def check_compatibility(manifest: dict[str, Any]) -> tuple[bool, str | None]:
    errors = validate_manifest(manifest)
    if errors:
        return False, "; ".join(errors)
    try:
        api_ver = int(manifest.get("mod_api_version", 1))
    except (TypeError, ValueError):
        return False, "mod_api_version 无效"
    if api_ver > MOD_API_VERSION:
        return False, f"需要 MOD API {api_ver}，当前仅支持 {MOD_API_VERSION}"
    min_app = str(manifest.get("min_app_version") or "0").strip()
    if min_app and not version_gte(APP_VERSION, min_app):
        return False, f"需要应用版本 >= {min_app}，当前 {APP_VERSION}"
    return True, None


def _manifest_from_legacy_py(path: Path) -> dict[str, Any]:
    stem = path.stem
    return {
        "id": stem,
        "name": stem,
        "version": "0.0.0",
        "mod_api_version": 1,
        "min_app_version": "0",
        "type": "python_hooks",
        "description": "遗留扩展脚本（data/extensions）",
        "author": "",
        "entry": path.name,
        "legacy": True,
    }


def _read_manifest_file(path: Path) -> dict[str, Any] | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def _mod_record_base(manifest: dict[str, Any], *, root: Path, source: str) -> dict[str, Any]:
    mod_id = str(manifest.get("id") or "").strip()
    return {
        "id": mod_id,
        "name": str(manifest.get("name") or mod_id),
        "type": str(manifest.get("type") or "python_hooks"),
        "version": str(manifest.get("version") or ""),
        "description": str(manifest.get("description") or ""),
        "author": str(manifest.get("author") or ""),
        "path": str(root),
        "source": source,
        "builtin": bool(manifest.get("builtin")),
        "legacy": bool(manifest.get("legacy")),
        "manifest": manifest,
        "assets": manifest.get("assets") if isinstance(manifest.get("assets"), dict) else {},
        "pack_file": str(manifest.get("pack_file") or ""),
        "status": "ok",
        "error": None,
        "hooks_registered": [],
        "enabled": True,
    }


def discover_mods(
    extensions_dir: Path,
    mods_dir: Path,
    *,
    world_packs_dir: Path | None = None,
) -> list[dict[str, Any]]:
    """扫描 MOD 目录与遗留 extensions，不执行加载。"""
    found: dict[str, dict[str, Any]] = {}

    if mods_dir.is_dir():
        for child in sorted(mods_dir.iterdir()):
            if not child.is_dir() or child.name.startswith("_"):
                continue
            manifest_path = child / "mod.json"
            if not manifest_path.is_file():
                continue
            manifest = _read_manifest_file(manifest_path)
            if manifest is None:
                rec = _mod_record_base({"id": child.name, "name": child.name, "type": "python_hooks"}, root=child, source="mods")
                rec["status"] = "error"
                rec["error"] = "mod.json 无法解析"
                found[child.name] = rec
                continue
            mod_id = str(manifest.get("id") or child.name).strip()
            manifest = {**manifest, "id": mod_id}
            rec = _mod_record_base(manifest, root=child, source="mods")
            val_errors = validate_manifest(manifest)
            if val_errors:
                rec["status"] = "error"
                rec["error"] = "; ".join(val_errors)
            else:
                ok, err = check_compatibility(manifest)
                if not ok:
                    rec["status"] = "incompatible"
                    rec["error"] = err
            found[mod_id] = rec

    if extensions_dir.is_dir():
        for path in sorted(extensions_dir.glob("*.py")):
            if path.name.startswith("_"):
                continue
            manifest = _manifest_from_legacy_py(path)
            mod_id = manifest["id"]
            if mod_id in found:
                continue
            rec = _mod_record_base(manifest, root=path.parent, source="legacy")
            rec["legacy_path"] = str(path)
            found[mod_id] = rec

    if world_packs_dir and world_packs_dir.is_dir():
        for pack in sorted(world_packs_dir.glob("*.nworld.zip")):
            mod_id = f"pack_{pack.stem}"
            if mod_id in found:
                continue
            manifest = {
                "id": mod_id,
                "name": pack.stem,
                "version": "",
                "mod_api_version": 1,
                "min_app_version": "0",
                "type": "world_content",
                "description": "已安装的世界内容包",
                "pack_file": pack.name,
                "readonly": True,
            }
            rec = _mod_record_base(manifest, root=pack.parent, source="packs")
            found[mod_id] = rec

    return list(found.values())


class _HookRegistrar:
    """传给 MOD register() 的上下文，统一注册 Hook 与斜杠命令。"""

    def __init__(self, mod_id: str, hooks_before: set[str]) -> None:
        self._mod_id = mod_id
        self._hooks_before = hooks_before
        self._registered: list[str] = []

    def register_hook(self, name: str, fn: Any, *, priority: int = 100) -> None:
        hook_bus.register_hook(name, fn, priority=priority)
        self._registered.append(name)

    def register_command(self, name: str, handler: Any) -> None:
        from novel_world.modules.ai.services.command_parser import register_command

        register_command(name, handler)

    @property
    def hooks_registered(self) -> list[str]:
        after = set(hook_bus.list_hooks().keys())
        new_hooks = sorted(after - self._hooks_before)
        return new_hooks or list(dict.fromkeys(self._registered))


def _load_python_entry(entry_path: Path, mod_id: str) -> tuple[list[str], str | None]:
    if not entry_path.is_file():
        return [], f"入口文件不存在：{entry_path.name}"
    hooks_before = set(hook_bus.list_hooks().keys())
    mod_name = f"nw_mod_{mod_id}"
    try:
        spec = importlib.util.spec_from_file_location(mod_name, entry_path)
        if spec is None or spec.loader is None:
            return [], "无法创建模块 spec"
        module = importlib.util.module_from_spec(spec)
        sys.modules[mod_name] = module
        spec.loader.exec_module(module)
        register = getattr(module, "register", None)
        if not callable(register):
            return [], "缺少 register(hooks) 函数"
        registrar = _HookRegistrar(mod_id, hooks_before)
        register(registrar)
        return registrar.hooks_registered, None
    except Exception as exc:
        return [], str(exc)


def _apply_disabled(records: list[dict[str, Any]], disabled: set[str]) -> None:
    for rec in records:
        mod_id = rec["id"]
        if mod_id in disabled:
            if rec["status"] == "ok":
                rec["status"] = "disabled"
            rec["enabled"] = False
        elif rec["status"] == "ok":
            rec["enabled"] = True
        else:
            rec["enabled"] = False


def load_mods(
    extensions_dir: Path,
    mods_dir: Path,
    *,
    disabled: list[str] | None = None,
    world_packs_dir: Path | None = None,
) -> list[dict[str, Any]]:
    """发现、校验并加载可运行的 MOD（Python Hook 部分）。"""
    disabled_set = set(disabled or [])
    records = discover_mods(extensions_dir, mods_dir, world_packs_dir=world_packs_dir)

    for rec in records:
        if rec["status"] not in ("ok", "disabled"):
            continue
        if rec["id"] in disabled_set:
            rec["status"] = "disabled"
            rec["enabled"] = False
            continue

        mod_type = rec["type"]
        if mod_type not in ("python_hooks", "composite"):
            continue

        manifest = rec.get("manifest") or {}
        entry_name = str(manifest.get("entry") or "main.py").strip()
        if rec.get("legacy"):
            legacy_path = Path(str(rec.get("legacy_path") or ""))
            if legacy_path.is_file():
                hooks, err = _load_python_entry(legacy_path, rec["id"])
            else:
                hooks, err = [], "遗留扩展文件不存在"
        else:
            root = Path(rec["path"])
            hooks, err = _load_python_entry(root / entry_name, rec["id"])

        if err:
            rec["status"] = "error"
            rec["error"] = err
            rec["enabled"] = False
        else:
            rec["hooks_registered"] = hooks
            rec["status"] = "ok"
            rec["enabled"] = True

    _apply_disabled(records, disabled_set)
    return records


def load_extensions(
    extensions_dir: Path,
    *,
    disabled: list[str] | None = None,
    mods_dir: Path | None = None,
    world_packs_dir: Path | None = None,
) -> list[dict[str, Any]]:
    """向后兼容入口。"""
    mods = mods_dir or extensions_dir.parent / "mods"
    return load_mods(
        extensions_dir,
        mods,
        disabled=disabled,
        world_packs_dir=world_packs_dir,
    )


def get_enabled_frontend_assets(
    records: list[dict[str, Any]],
    *,
    disabled: list[str] | None = None,
) -> list[dict[str, Any]]:
    disabled_set = set(disabled or [])
    assets: list[dict[str, Any]] = []
    for rec in records:
        if rec["id"] in disabled_set or rec.get("status") in ("error", "incompatible", "disabled"):
            continue
        if rec["type"] not in ("frontend", "composite"):
            continue
        manifest_assets = rec.get("assets") or {}
        js_files = manifest_assets.get("js") if isinstance(manifest_assets.get("js"), list) else []
        css_files = manifest_assets.get("css") if isinstance(manifest_assets.get("css"), list) else []
        if not js_files and not css_files:
            root = Path(rec["path"])
            if (root / "mod.js").is_file():
                js_files = ["mod.js"]
            if (root / "mod.css").is_file():
                css_files = ["mod.css"]
        if js_files or css_files:
            assets.append(
                {
                    "id": rec["id"],
                    "js": [str(f) for f in js_files],
                    "css": [str(f) for f in css_files],
                }
            )
    return assets


def resolve_mod_asset_path(mods_dir: Path, mod_id: str, asset_path: str) -> Path | None:
    if not re.fullmatch(r"[a-zA-Z0-9_-]+", mod_id):
        return None
    clean = asset_path.replace("\\", "/").lstrip("/")
    if ".." in clean.split("/"):
        return None
    root = (mods_dir / mod_id).resolve()
    target = (root / clean).resolve()
    if not str(target).startswith(str(root)):
        return None
    if not target.is_file():
        return None
    return target


def install_mod_zip(mods_dir: Path, data: bytes, *, filename: str = "") -> dict[str, Any]:
    mods_dir.mkdir(parents=True, exist_ok=True)
    try:
        with zipfile.ZipFile(BytesIO(data)) as zf:
            if "mod.json" not in zf.namelist():
                return {"ok": False, "message": "ZIP 根目录缺少 mod.json"}
            manifest = json.loads(zf.read("mod.json").decode("utf-8"))
    except (zipfile.BadZipFile, json.JSONDecodeError, UnicodeDecodeError) as exc:
        return {"ok": False, "message": f"无法读取 MOD 包：{exc}"}

    errors = validate_manifest(manifest)
    if errors:
        return {"ok": False, "message": "; ".join(errors)}
    ok, err = check_compatibility(manifest)
    if not ok:
        return {"ok": False, "message": err or "不兼容"}

    mod_id = str(manifest["id"]).strip()
    target = mods_dir / mod_id
    if target.exists():
        return {"ok": False, "message": f"MOD {mod_id} 已存在"}

    target.mkdir(parents=True, exist_ok=False)
    try:
        with zipfile.ZipFile(BytesIO(data)) as zf:
            for name in zf.namelist():
                if name.endswith("/"):
                    continue
                dest = target / name
                if ".." in Path(name).parts:
                    raise ValueError("非法路径")
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(zf.read(name))
    except Exception as exc:
        shutil.rmtree(target, ignore_errors=True)
        return {"ok": False, "message": f"安装失败：{exc}"}

    return {"ok": True, "message": f"已安装 MOD：{manifest.get('name') or mod_id}", "id": mod_id}


def uninstall_mod(mods_dir: Path, mod_id: str) -> dict[str, Any]:
    if not re.fullmatch(r"[a-zA-Z0-9_-]+", mod_id):
        return {"ok": False, "message": "无效的 MOD id"}
    target = mods_dir / mod_id
    manifest_path = target / "mod.json"
    if manifest_path.is_file():
        manifest = _read_manifest_file(manifest_path) or {}
        if manifest.get("builtin"):
            return {"ok": False, "message": "内置 MOD 不可卸载"}
    if not target.is_dir():
        return {"ok": False, "message": "MOD 不存在"}
    shutil.rmtree(target)
    return {"ok": True, "message": f"已卸载 MOD：{mod_id}"}
