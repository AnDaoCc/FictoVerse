from __future__ import annotations

import json
from pathlib import Path

from novel_world.infrastructure.server_meta import (
    read_server_meta,
    remove_server_meta,
    write_server_meta,
)


def test_server_meta_roundtrip(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    write_server_meta(data_dir, host="127.0.0.1", port=8080)
    meta = read_server_meta(data_dir)
    assert meta is not None
    assert meta["host"] == "127.0.0.1"
    assert meta["port"] == 8080
    assert "pid" in meta
    remove_server_meta(data_dir)
    assert read_server_meta(data_dir) is None
