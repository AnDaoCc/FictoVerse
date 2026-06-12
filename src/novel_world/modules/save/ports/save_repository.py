from __future__ import annotations

from typing import Any, Protocol

from novel_world.core.domain.ids import SaveId, WorldId
from novel_world.modules.save.domain.entities import SaveSlot


class SaveRepository(Protocol):
    def get(self, save_id: SaveId) -> SaveSlot | None: ...

    def get_by_slot(self, world_id: WorldId, slot_index: int) -> SaveSlot | None: ...

    def list_by_world(self, world_id: WorldId) -> list[SaveSlot]: ...

    def save(self, slot: SaveSlot) -> None: ...

    def delete(self, save_id: SaveId) -> None: ...
