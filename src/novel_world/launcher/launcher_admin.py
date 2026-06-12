from __future__ import annotations

import base64
import json
import mimetypes
from pathlib import Path
from typing import Any

from novel_world.bootstrap.config import default_config
from novel_world.launcher.bootstrap import get_root

ALLOWED_BG_EXT = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
DEFAULT_APPEARANCE: dict[str, Any] = {"overlay": 0.55, "blur": 8, "fit": "cover"}


def _launcher_data_dir() -> Path:
    cfg = default_config(get_root())
    return cfg.data_dir / "launcher"


def _background_dir() -> Path:
    return _launcher_data_dir() / "background"


def _appearance_path() -> Path:
    return _launcher_data_dir() / "appearance.json"


def _decode_b64(data_b64: str) -> bytes:
    text = (data_b64 or "").strip()
    if "," in text:
        text = text.split(",", 1)[1]
    return base64.b64decode(text)


def _load_appearance_config() -> dict[str, Any]:
    path = _appearance_path()
    if not path.is_file():
        return dict(DEFAULT_APPEARANCE)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return dict(DEFAULT_APPEARANCE)
    if not isinstance(data, dict):
        return dict(DEFAULT_APPEARANCE)
    merged = dict(DEFAULT_APPEARANCE)
    merged.update(data)
    return merged


def _save_appearance_config(config: dict[str, Any]) -> None:
    _launcher_data_dir().mkdir(parents=True, exist_ok=True)
    merged = dict(DEFAULT_APPEARANCE)
    merged.update(config)
    _appearance_path().write_text(
        json.dumps(merged, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _find_background_file() -> Path | None:
    bg_dir = _background_dir()
    if not bg_dir.is_dir():
        return None
    for candidate in sorted(bg_dir.glob("bg.*")):
        if candidate.is_file() and candidate.suffix.lower() in ALLOWED_BG_EXT:
            return candidate
    return None


def _encode_background_data_url(path: Path) -> str:
    mime, _ = mimetypes.guess_type(path.name)
    if not mime:
        mime = "image/png"
    payload = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{payload}"


def get_launcher_appearance() -> dict[str, Any]:
    config = _load_appearance_config()
    bg = _find_background_file()
    result: dict[str, Any] = {
        "ok": True,
        "has_background": bg is not None,
        "overlay": float(config.get("overlay", DEFAULT_APPEARANCE["overlay"])),
        "blur": int(config.get("blur", DEFAULT_APPEARANCE["blur"])),
        "fit": str(config.get("fit", DEFAULT_APPEARANCE["fit"])),
    }
    if bg is not None:
        try:
            result["background_data_url"] = _encode_background_data_url(bg)
        except OSError as exc:
            result["has_background"] = False
            result["message"] = str(exc)
    return result


def upload_launcher_background(filename: str, data_b64: str) -> dict[str, Any]:
    try:
        data = _decode_b64(data_b64)
    except Exception as exc:
        return {"ok": False, "message": f"图片数据无效：{exc}"}
    if not data:
        return {"ok": False, "message": "图片为空"}
    ext = Path(filename or "bg.png").suffix.lower()
    if ext not in ALLOWED_BG_EXT:
        ext = ".png"
    bg_dir = _background_dir()
    bg_dir.mkdir(parents=True, exist_ok=True)
    for old in bg_dir.glob("bg.*"):
        old.unlink(missing_ok=True)
    dest = bg_dir / f"bg{ext}"
    dest.write_bytes(data)
    return {"ok": True, "message": "背景已更新"}


def clear_launcher_background() -> dict[str, Any]:
    bg_dir = _background_dir()
    if bg_dir.is_dir():
        for old in bg_dir.glob("bg.*"):
            old.unlink(missing_ok=True)
    return {"ok": True, "message": "背景已清除"}


def save_launcher_appearance(
    overlay: float = 0.55,
    blur: int = 8,
    fit: str = "cover",
) -> dict[str, Any]:
    overlay_val = max(0.0, min(0.8, float(overlay)))
    blur_val = max(0, min(24, int(blur)))
    fit_val = fit if fit in ("cover", "contain") else "cover"
    config = _load_appearance_config()
    config.update({"overlay": overlay_val, "blur": blur_val, "fit": fit_val})
    _save_appearance_config(config)
    return {"ok": True, "message": "外观设置已保存"}
