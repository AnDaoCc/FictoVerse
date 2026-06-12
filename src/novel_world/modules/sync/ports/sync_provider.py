from __future__ import annotations

from typing import Protocol


class SyncProvider(Protocol):
    def push_world(self, world_id: str, pack_bytes: bytes) -> str: ...

    def pull_world(self, remote_id: str) -> bytes: ...

    def list_remote_worlds(self) -> list[dict]: ...
