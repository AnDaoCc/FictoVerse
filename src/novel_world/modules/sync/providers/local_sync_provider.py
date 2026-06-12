from __future__ import annotations

from pathlib import Path


class LocalSyncProvider:
    """占位实现：仅本地 packs 目录，不连接远程服务器。"""

    def __init__(self, packs_dir: Path) -> None:
        self._packs_dir = packs_dir
        self._packs_dir.mkdir(parents=True, exist_ok=True)

    def push_world(self, world_id: str, pack_bytes: bytes) -> str:
        dest = self._packs_dir / f"{world_id}.nworld.zip"
        dest.write_bytes(pack_bytes)
        return str(dest)

    def pull_world(self, remote_id: str) -> bytes:
        path = Path(remote_id)
        if not path.is_file():
            path = self._packs_dir / remote_id
        if not path.is_file():
            raise FileNotFoundError(remote_id)
        return path.read_bytes()

    def list_remote_worlds(self) -> list[dict]:
        return [
            {"id": p.name, "path": str(p), "size": p.stat().st_size}
            for p in sorted(self._packs_dir.glob("*.nworld.zip"))
        ]
