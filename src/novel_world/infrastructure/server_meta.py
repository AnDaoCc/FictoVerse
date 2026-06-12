from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from novel_world.core.domain.timestamps import to_iso


def server_meta_path(data_dir: Path) -> Path:
    return data_dir / "server.json"


def write_server_meta(data_dir: Path, *, host: str, port: int) -> None:
    data_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "host": host,
        "port": port,
        "pid": os.getpid(),
        "started_at": to_iso(datetime.now(timezone.utc)),
    }
    server_meta_path(data_dir).write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def read_server_meta(data_dir: Path) -> dict[str, Any] | None:
    path = server_meta_path(data_dir)
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def remove_server_meta(data_dir: Path) -> None:
    path = server_meta_path(data_dir)
    if path.exists():
        path.unlink()
