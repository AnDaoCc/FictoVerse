from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from novel_world.core.domain.ids import CharacterId, EventId, WorldId


@dataclass
class Event:
    id: EventId
    world_id: WorldId
    seq: int
    event_type: str
    real_time: datetime
    payload: dict[str, Any] = field(default_factory=dict)
    world_time: str | None = None
    actor_id: CharacterId | None = None
    causation_id: EventId | None = None
    created_at: datetime | None = None
