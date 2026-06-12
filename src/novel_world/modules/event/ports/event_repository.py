from __future__ import annotations

from typing import Any, Protocol

from novel_world.core.domain.ids import CharacterId, EventId, WorldId
from novel_world.modules.event.domain.entities import Event


class EventRepository(Protocol):
    def append(self, event: Event) -> None: ...

    def get(self, event_id: EventId) -> Event | None: ...

    def list_by_world(self, world_id: WorldId) -> list[Event]: ...

    def next_seq(self, world_id: WorldId) -> int: ...

    def delete_all(self, world_id: WorldId) -> None: ...

    def replace_all(self, world_id: WorldId, events: list[Event]) -> None: ...
