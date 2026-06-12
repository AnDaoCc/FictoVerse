from __future__ import annotations

from typing import Any

from novel_world.core.domain.ids import CharacterId, EventId, WorldId, new_event_id
from novel_world.core.domain.timestamps import utc_now
from novel_world.core.exceptions import NotFoundError, ValidationError
from novel_world.modules.event.domain.entities import Event
from novel_world.modules.event.ports.event_repository import EventRepository


class EventService:
    def __init__(self, repository: EventRepository) -> None:
        self._repository = repository

    def record(
        self,
        world_id: WorldId,
        event_type: str,
        payload: dict[str, Any] | None = None,
        *,
        world_time: str | None = None,
        actor_id: CharacterId | None = None,
        causation_id: EventId | None = None,
    ) -> Event:
        if not event_type.strip():
            raise ValidationError("事件类型不能为空。")
        now = utc_now()
        event = Event(
            id=new_event_id(),
            world_id=world_id,
            seq=self._repository.next_seq(world_id),
            event_type=event_type.strip(),
            world_time=world_time,
            real_time=now,
            actor_id=actor_id,
            payload=payload or {},
            causation_id=causation_id,
            created_at=now,
        )
        self._repository.append(event)
        return event

    def get(self, event_id: EventId) -> Event:
        event = self._repository.get(event_id)
        if event is None:
            raise NotFoundError(f"事件不存在: {event_id}")
        return event

    def list_by_world(self, world_id: WorldId) -> list[Event]:
        return self._repository.list_by_world(world_id)
