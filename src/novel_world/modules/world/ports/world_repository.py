from __future__ import annotations

from typing import Protocol

from novel_world.core.domain.ids import WorldId
from novel_world.modules.world.domain.entities import World


class WorldRepository(Protocol):
    def get(self, world_id: WorldId) -> World | None: ...

    def save(self, world: World) -> None: ...

    def delete(self, world_id: WorldId) -> None: ...
