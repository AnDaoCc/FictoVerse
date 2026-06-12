from __future__ import annotations

from typing import Any

from novel_world.core.domain.ids import CharacterId, WorldId, new_character_id
from novel_world.core.domain.timestamps import utc_now
from novel_world.core.exceptions import NotFoundError, ValidationError
from novel_world.modules.character.domain.entities import Character
from novel_world.modules.character.ports.character_repository import CharacterRepository


class CharacterService:
    def __init__(self, repository: CharacterRepository) -> None:
        self._repository = repository

    def create(
        self,
        world_id: WorldId,
        name: str,
        *,
        role: str = "npc",
        profile: dict[str, Any] | None = None,
        attributes: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Character:
        if not name.strip():
            raise ValidationError("角色名称不能为空。")
        now = utc_now()
        character = Character(
            id=new_character_id(),
            world_id=world_id,
            name=name.strip(),
            role=role,
            profile=profile or {},
            attributes=attributes or {},
            metadata=metadata or {},
            created_at=now,
            updated_at=now,
        )
        self._repository.save(character)
        return character

    def get(self, character_id: CharacterId) -> Character:
        character = self._repository.get(character_id)
        if character is None:
            raise NotFoundError(f"角色不存在: {character_id}")
        return character

    def list_by_world(self, world_id: WorldId, *, active_only: bool = True) -> list[Character]:
        return self._repository.list_by_world(world_id, active_only=active_only)

    def update(
        self,
        character_id: CharacterId,
        *,
        name: str | None = None,
        role: str | None = None,
        profile: dict[str, Any] | None = None,
        attributes: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
        is_active: bool | None = None,
    ) -> Character:
        character = self.get(character_id)
        if name is not None:
            if not name.strip():
                raise ValidationError("角色名称不能为空。")
            character.name = name.strip()
        if role is not None:
            character.role = role
        if profile is not None:
            character.profile = profile
        if attributes is not None:
            character.attributes = attributes
        if metadata is not None:
            character.metadata = metadata
        if is_active is not None:
            character.is_active = is_active
        character.updated_at = utc_now()
        self._repository.save(character)
        return character

    def delete(self, character_id: CharacterId) -> None:
        self.get(character_id)
        self._repository.delete(character_id)
