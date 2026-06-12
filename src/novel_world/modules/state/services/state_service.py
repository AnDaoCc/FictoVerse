from __future__ import annotations

from typing import Any

from novel_world.core.domain.ids import CharacterId, WorldId, new_state_entry_id
from novel_world.core.domain.timestamps import utc_now
from novel_world.core.exceptions import NotFoundError, ValidationError
from novel_world.modules.state.domain.entities import StateEntry, StateScope
from novel_world.modules.state.ports.state_repository import StateRepository
from novel_world.shared.json_codec import infer_value_type


class StateService:
    VALID_SCOPES: set[StateScope] = {"world", "character", "global"}

    def __init__(self, repository: StateRepository) -> None:
        self._repository = repository

    def set_value(
        self,
        world_id: WorldId,
        key: str,
        value: Any,
        *,
        scope: StateScope = "world",
        scope_id: CharacterId | None = None,
    ) -> StateEntry:
        if not key.strip():
            raise ValidationError("状态键不能为空。")
        if scope not in self.VALID_SCOPES:
            raise ValidationError(f"无效的状态范围: {scope}")
        if scope == "character" and scope_id is None:
            raise ValidationError("角色范围状态必须提供 scope_id。")
        if scope != "character" and scope_id is not None:
            raise ValidationError("非角色范围状态不能提供 scope_id。")

        existing = self._repository.get_entry(world_id, scope, key.strip(), scope_id)
        now = utc_now()
        entry = StateEntry(
            id=existing.id if existing else new_state_entry_id(),
            world_id=world_id,
            scope=scope,
            scope_id=scope_id,
            key=key.strip(),
            value=value,
            value_type=infer_value_type(value),
            updated_at=now,
        )
        self._repository.upsert(entry)
        return entry

    def get_value(
        self,
        world_id: WorldId,
        key: str,
        *,
        scope: StateScope = "world",
        scope_id: CharacterId | None = None,
        default: Any = None,
    ) -> Any:
        entry = self._repository.get_entry(world_id, scope, key.strip(), scope_id)
        if entry is None:
            return default
        return entry.value

    def get_entry(
        self,
        world_id: WorldId,
        key: str,
        *,
        scope: StateScope = "world",
        scope_id: CharacterId | None = None,
    ) -> StateEntry:
        entry = self._repository.get_entry(world_id, scope, key.strip(), scope_id)
        if entry is None:
            raise NotFoundError(f"状态不存在: {scope}/{key}")
        return entry

    def list_by_world(self, world_id: WorldId) -> list[StateEntry]:
        return self._repository.list_by_world(world_id)

    def delete_value(
        self,
        world_id: WorldId,
        key: str,
        *,
        scope: StateScope = "world",
        scope_id: CharacterId | None = None,
    ) -> None:
        self._repository.delete_entry(world_id, scope, key.strip(), scope_id)
