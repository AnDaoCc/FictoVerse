from __future__ import annotations

from typing import Protocol

from novel_world.core.domain.ids import CharacterId, WorldId
from novel_world.modules.character.domain.entities import Character


class CharacterRepository(Protocol):
    def get(self, character_id: CharacterId) -> Character | None: ...

    def list_by_world(self, world_id: WorldId, *, active_only: bool = True) -> list[Character]: ...

    def save(self, character: Character) -> None: ...

    def delete(self, character_id: CharacterId) -> None: ...

    def delete_all(self, world_id: WorldId) -> None: ...
