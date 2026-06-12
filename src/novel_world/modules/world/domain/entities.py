from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from novel_world.core.domain.ids import WorldId
from novel_world.core.domain.schema_version import SCHEMA_VERSION


@dataclass
class World:
    id: WorldId
    name: str
    description: str = ""
    genre: str = ""
    rules: dict[str, Any] = field(default_factory=dict)
    settings: dict[str, Any] = field(default_factory=dict)
    schema_version: int = SCHEMA_VERSION
    created_at: datetime | None = None
    updated_at: datetime | None = None
