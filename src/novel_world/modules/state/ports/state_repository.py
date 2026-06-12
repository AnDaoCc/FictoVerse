from __future__ import annotations

from typing import Any, Protocol

from novel_world.core.domain.ids import CharacterId, WorldId
from novel_world.modules.state.domain.entities import StateEntry, StateScope


class StateRepository(Protocol):
    def get_entry(
        self,
        world_id: WorldId,
        scope: StateScope,
        key: str,
        scope_id: CharacterId | None = None,
    ) -> StateEntry | None: ...

    def list_by_world(self, world_id: WorldId) -> list[StateEntry]: ...

    def upsert(self, entry: StateEntry) -> None: ...

    def delete_entry(
        self,
        world_id: WorldId,
        scope: StateScope,
        key: str,
        scope_id: CharacterId | None = None,
    ) -> None: ...

    def delete_all(self, world_id: WorldId) -> None: ...

    def replace_all(self, world_id: WorldId, entries: list[StateEntry]) -> None: ...
