from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal

from novel_world.core.domain.ids import CharacterId, StateEntryId, WorldId

StateScope = Literal["world", "character", "global"]


@dataclass
class StateEntry:
    id: StateEntryId
    world_id: WorldId
    scope: StateScope
    scope_id: CharacterId | None
    key: str
    value: Any
    value_type: str
    updated_at: datetime | None = None
