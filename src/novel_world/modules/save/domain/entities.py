from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from novel_world.core.domain.ids import SaveId, WorldId


@dataclass
class SaveSlot:
    id: SaveId
    world_id: WorldId
    slot_index: int
    label: str
    snapshot_path: str
    snapshot_version: int
    checksum: str
    world_time_at_save: str | None = None
    created_at: datetime | None = None
