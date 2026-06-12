from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from novel_world.core.domain.ids import CharacterId, WorldId


@dataclass
class Character:
    id: CharacterId
    world_id: WorldId
    name: str
    role: str = "npc"
    profile: dict[str, Any] = field(default_factory=dict)
    attributes: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    is_active: bool = True
    created_at: datetime | None = None
    updated_at: datetime | None = None
