from __future__ import annotations

import hashlib
from pathlib import Path

from novel_world.bootstrap.config import AppConfig
from novel_world.core.domain.ids import SaveId, WorldId, new_save_id
from novel_world.core.domain.timestamps import utc_now
from novel_world.core.exceptions import NotFoundError, ValidationError
from novel_world.modules.character.ports.character_repository import CharacterRepository
from novel_world.modules.event.ports.event_repository import EventRepository
from novel_world.modules.save.domain.entities import SaveSlot
from novel_world.modules.save.ports.save_repository import SaveRepository
from novel_world.modules.save.snapshot.decoder import decode_snapshot
from novel_world.modules.save.snapshot.encoder import encode_snapshot
from novel_world.modules.state.ports.state_repository import StateRepository
from novel_world.modules.world.ports.world_repository import WorldRepository
from novel_world.shared.json_codec import dumps_json, loads_json


class SaveService:
    def __init__(
        self,
        config: AppConfig,
        world_repo: WorldRepository,
        character_repo: CharacterRepository,
        state_repo: StateRepository,
        event_repo: EventRepository,
        save_repo: SaveRepository,
    ) -> None:
        self._config = config
        self._world_repo = world_repo
        self._character_repo = character_repo
        self._state_repo = state_repo
        self._event_repo = event_repo
        self._save_repo = save_repo

    def create_save(
        self,
        world_id: WorldId,
        slot_index: int,
        *,
        label: str = "",
    ) -> SaveSlot:
        if slot_index < 0:
            raise ValidationError("存档槽位不能为负数。")

        world = self._world_repo.get(world_id)
        if world is None:
            raise NotFoundError(f"世界不存在: {world_id}")

        characters = self._character_repo.list_by_world(world_id, active_only=False)
        state_entries = self._state_repo.list_by_world(world_id)
        events = self._event_repo.list_by_world(world_id)

        snapshot = encode_snapshot(world, characters, state_entries, events)
        snapshot_text = dumps_json(snapshot)
        checksum = hashlib.sha256(snapshot_text.encode("utf-8")).hexdigest()

        save_id = new_save_id()
        snapshot_path = self._config.snapshot_path(str(save_id))
        self._config.ensure_dirs()
        snapshot_path.write_text(snapshot_text, encoding="utf-8")

        world_time = None
        for entry in state_entries:
            if entry.key == "time.current":
                world_time = str(entry.value)
                break

        now = utc_now()
        relative_snapshot = f"saves/{save_id}.snapshot.json"
        slot = SaveSlot(
            id=save_id,
            world_id=world_id,
            slot_index=slot_index,
            label=label or f"存档 {slot_index}",
            snapshot_path=relative_snapshot,
            snapshot_version=self._config.snapshot_version,
            world_time_at_save=world_time,
            checksum=checksum,
            created_at=now,
        )
        self._save_repo.save(slot)
        return slot

    def load_save(self, save_id: SaveId) -> WorldId:
        slot = self._save_repo.get(save_id)
        if slot is None:
            raise NotFoundError(f"存档不存在: {save_id}")

        snapshot_path = self._resolve_snapshot_path(slot.snapshot_path)
        if not snapshot_path.exists():
            raise NotFoundError(f"快照文件不存在: {snapshot_path}")

        snapshot_text = snapshot_path.read_text(encoding="utf-8")
        checksum = hashlib.sha256(snapshot_text.encode("utf-8")).hexdigest()
        if checksum != slot.checksum:
            raise ValidationError("快照校验失败，文件可能已损坏。")

        snapshot = loads_json(snapshot_text)
        world, characters, state_entries, events = decode_snapshot(snapshot)

        self._event_repo.delete_all(world.id)
        self._state_repo.delete_all(world.id)
        self._character_repo.delete_all(world.id)
        self._world_repo.save(world)
        for character in characters:
            self._character_repo.save(character)
        self._state_repo.replace_all(world.id, state_entries)
        self._event_repo.replace_all(world.id, events)
        return world.id

    def list_saves(self, world_id: WorldId) -> list[SaveSlot]:
        return self._save_repo.list_by_world(world_id)

    def get_save(self, save_id: SaveId) -> SaveSlot:
        slot = self._save_repo.get(save_id)
        if slot is None:
            raise NotFoundError(f"存档不存在: {save_id}")
        return slot

    def _resolve_snapshot_path(self, snapshot_path: str) -> Path:
        path = Path(snapshot_path)
        if path.is_absolute():
            return path
        return self._config.data_dir / path
