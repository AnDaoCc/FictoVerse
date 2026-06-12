from __future__ import annotations

from datetime import datetime
from typing import Any

from novel_world.core.domain.ids import WorldId, new_world_id
from novel_world.core.domain.timestamps import utc_now
from novel_world.core.exceptions import NotFoundError, ValidationError
from novel_world.modules.world.domain.entities import World
from novel_world.modules.world.ports.world_repository import WorldRepository


class WorldService:
    def __init__(self, repository: WorldRepository) -> None:
        self._repository = repository

    def create(
        self,
        name: str,
        *,
        world_id: WorldId | None = None,
        description: str = "",
        genre: str = "",
        rules: dict[str, Any] | None = None,
        settings: dict[str, Any] | None = None,
    ) -> World:
        if not name.strip():
            raise ValidationError("世界名称不能为空。")
        now = utc_now()
        world = World(
            id=world_id or new_world_id(),
            name=name.strip(),
            description=description,
            genre=genre,
            rules=rules or {},
            settings=settings or {},
            created_at=now,
            updated_at=now,
        )
        self._repository.save(world)
        return world

    def get(self, world_id: WorldId) -> World:
        world = self._repository.get(world_id)
        if world is None:
            raise NotFoundError(f"世界不存在: {world_id}")
        return world

    def update(
        self,
        world_id: WorldId,
        *,
        name: str | None = None,
        description: str | None = None,
        genre: str | None = None,
        rules: dict[str, Any] | None = None,
        settings: dict[str, Any] | None = None,
    ) -> World:
        world = self.get(world_id)
        if name is not None:
            if not name.strip():
                raise ValidationError("世界名称不能为空。")
            world.name = name.strip()
        if description is not None:
            world.description = description
        if genre is not None:
            world.genre = genre
        if rules is not None:
            world.rules = rules
        if settings is not None:
            world.settings = settings
        world.updated_at = utc_now()
        self._repository.save(world)
        return world

    def delete(self, world_id: WorldId) -> None:
        self.get(world_id)
        self._repository.delete(world_id)
