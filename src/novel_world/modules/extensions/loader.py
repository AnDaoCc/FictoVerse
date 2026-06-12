from __future__ import annotations

from pathlib import Path
from typing import Any

from novel_world.modules.extensions.mod_registry import load_extensions as _load_extensions

__all__ = ["load_extensions"]


def load_extensions(
    extensions_dir: Path,
    *,
    disabled: list[str] | None = None,
    mods_dir: Path | None = None,
    world_packs_dir: Path | None = None,
) -> list[dict[str, Any]]:
    return _load_extensions(
        extensions_dir,
        disabled=disabled,
        mods_dir=mods_dir,
        world_packs_dir=world_packs_dir,
    )
