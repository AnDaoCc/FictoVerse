from __future__ import annotations

import sqlite3
from typing import Any

from novel_world.core.domain.ids import (
    CharacterId,
    EventId,
    SaveId,
    StateEntryId,
    WorldId,
)
from novel_world.core.domain.timestamps import from_iso, to_iso
from novel_world.modules.character.domain.entities import Character
from novel_world.modules.event.domain.entities import Event
from novel_world.modules.save.domain.entities import SaveSlot
from novel_world.modules.state.domain.entities import StateEntry, StateScope
from novel_world.modules.world.domain.entities import World
from novel_world.shared.json_codec import dumps_json, loads_json


class SqliteWorldRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def get(self, world_id: WorldId) -> World | None:
        row = self._conn.execute(
            "SELECT * FROM worlds WHERE id = ?", (str(world_id),)
        ).fetchone()
        return _row_to_world(row) if row else None

    def save(self, world: World) -> None:
        self._conn.execute(
            """
            INSERT INTO worlds (
                id, name, description, genre, rules_json, settings_json,
                schema_version, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                name = excluded.name,
                description = excluded.description,
                genre = excluded.genre,
                rules_json = excluded.rules_json,
                settings_json = excluded.settings_json,
                schema_version = excluded.schema_version,
                updated_at = excluded.updated_at
            """,
            (
                str(world.id),
                world.name,
                world.description,
                world.genre,
                dumps_json(world.rules),
                dumps_json(world.settings),
                world.schema_version,
                to_iso(world.created_at) if world.created_at else to_iso(_now_fallback()),
                to_iso(world.updated_at) if world.updated_at else to_iso(_now_fallback()),
            ),
        )

    def delete(self, world_id: WorldId) -> None:
        self._conn.execute("DELETE FROM worlds WHERE id = ?", (str(world_id),))


class SqliteCharacterRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def get(self, character_id: CharacterId) -> Character | None:
        row = self._conn.execute(
            "SELECT * FROM characters WHERE id = ?", (str(character_id),)
        ).fetchone()
        return _row_to_character(row) if row else None

    def list_by_world(self, world_id: WorldId, *, active_only: bool = True) -> list[Character]:
        if active_only:
            rows = self._conn.execute(
                "SELECT * FROM characters WHERE world_id = ? AND is_active = 1 ORDER BY name",
                (str(world_id),),
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM characters WHERE world_id = ? ORDER BY name",
                (str(world_id),),
            ).fetchall()
        return [_row_to_character(row) for row in rows]

    def save(self, character: Character) -> None:
        self._conn.execute(
            """
            INSERT INTO characters (
                id, world_id, name, role, profile_json, attributes_json,
                metadata_json, is_active, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                name = excluded.name,
                role = excluded.role,
                profile_json = excluded.profile_json,
                attributes_json = excluded.attributes_json,
                metadata_json = excluded.metadata_json,
                is_active = excluded.is_active,
                updated_at = excluded.updated_at
            """,
            (
                str(character.id),
                str(character.world_id),
                character.name,
                character.role,
                dumps_json(character.profile),
                dumps_json(character.attributes),
                dumps_json(character.metadata),
                1 if character.is_active else 0,
                to_iso(character.created_at) if character.created_at else to_iso(_now_fallback()),
                to_iso(character.updated_at) if character.updated_at else to_iso(_now_fallback()),
            ),
        )

    def delete(self, character_id: CharacterId) -> None:
        self._conn.execute("DELETE FROM characters WHERE id = ?", (str(character_id),))

    def delete_all(self, world_id: WorldId) -> None:
        self._conn.execute("DELETE FROM characters WHERE world_id = ?", (str(world_id),))


class SqliteStateRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def get_entry(
        self,
        world_id: WorldId,
        scope: StateScope,
        key: str,
        scope_id: CharacterId | None = None,
    ) -> StateEntry | None:
        scope_id_value = str(scope_id) if scope_id else ""
        row = self._conn.execute(
            """
            SELECT * FROM state_entries
            WHERE world_id = ? AND scope = ? AND key = ?
              AND scope_id = ?
            """,
            (str(world_id), scope, key, scope_id_value),
        ).fetchone()
        return _row_to_state_entry(row) if row else None

    def list_by_world(self, world_id: WorldId) -> list[StateEntry]:
        rows = self._conn.execute(
            "SELECT * FROM state_entries WHERE world_id = ? ORDER BY key",
            (str(world_id),),
        ).fetchall()
        return [_row_to_state_entry(row) for row in rows]

    def upsert(self, entry: StateEntry) -> None:
        self._conn.execute(
            """
            INSERT INTO state_entries (
                id, world_id, scope, scope_id, key, value_json, value_type, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(world_id, scope, scope_id, key) DO UPDATE SET
                value_json = excluded.value_json,
                value_type = excluded.value_type,
                updated_at = excluded.updated_at
            """,
            (
                str(entry.id),
                str(entry.world_id),
                entry.scope,
                str(entry.scope_id) if entry.scope_id else "",
                entry.key,
                dumps_json(entry.value),
                entry.value_type,
                to_iso(entry.updated_at) if entry.updated_at else to_iso(_now_fallback()),
            ),
        )

    def delete_entry(
        self,
        world_id: WorldId,
        scope: StateScope,
        key: str,
        scope_id: CharacterId | None = None,
    ) -> None:
        scope_id_value = str(scope_id) if scope_id else ""
        self._conn.execute(
            """
            DELETE FROM state_entries
            WHERE world_id = ? AND scope = ? AND key = ?
              AND scope_id = ?
            """,
            (str(world_id), scope, key, scope_id_value),
        )

    def delete_all(self, world_id: WorldId) -> None:
        self._conn.execute("DELETE FROM state_entries WHERE world_id = ?", (str(world_id),))

    def replace_all(self, world_id: WorldId, entries: list[StateEntry]) -> None:
        self.delete_all(world_id)
        for entry in entries:
            self.upsert(entry)


class SqliteEventRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def append(self, event: Event) -> None:
        self._conn.execute(
            """
            INSERT INTO events (
                id, world_id, seq, event_type, world_time, real_time,
                actor_id, payload_json, causation_id, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(event.id),
                str(event.world_id),
                event.seq,
                event.event_type,
                event.world_time,
                to_iso(event.real_time),
                str(event.actor_id) if event.actor_id else None,
                dumps_json(event.payload),
                str(event.causation_id) if event.causation_id else None,
                to_iso(event.created_at) if event.created_at else to_iso(event.real_time),
            ),
        )

    def get(self, event_id: EventId) -> Event | None:
        row = self._conn.execute(
            "SELECT * FROM events WHERE id = ?", (str(event_id),)
        ).fetchone()
        return _row_to_event(row) if row else None

    def list_by_world(self, world_id: WorldId) -> list[Event]:
        rows = self._conn.execute(
            "SELECT * FROM events WHERE world_id = ? ORDER BY seq",
            (str(world_id),),
        ).fetchall()
        return [_row_to_event(row) for row in rows]

    def next_seq(self, world_id: WorldId) -> int:
        row = self._conn.execute(
            "SELECT COALESCE(MAX(seq), 0) + 1 FROM events WHERE world_id = ?",
            (str(world_id),),
        ).fetchone()
        return int(row[0])

    def delete_all(self, world_id: WorldId) -> None:
        self._conn.execute("DELETE FROM events WHERE world_id = ?", (str(world_id),))

    def replace_all(self, world_id: WorldId, events: list[Event]) -> None:
        self.delete_all(world_id)
        for event in events:
            self.append(event)


class SqliteSaveRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def get(self, save_id: SaveId) -> SaveSlot | None:
        row = self._conn.execute(
            "SELECT * FROM save_slots WHERE id = ?", (str(save_id),)
        ).fetchone()
        return _row_to_save_slot(row) if row else None

    def get_by_slot(self, world_id: WorldId, slot_index: int) -> SaveSlot | None:
        row = self._conn.execute(
            "SELECT * FROM save_slots WHERE world_id = ? AND slot_index = ?",
            (str(world_id), slot_index),
        ).fetchone()
        return _row_to_save_slot(row) if row else None

    def list_by_world(self, world_id: WorldId) -> list[SaveSlot]:
        rows = self._conn.execute(
            "SELECT * FROM save_slots WHERE world_id = ? ORDER BY slot_index",
            (str(world_id),),
        ).fetchall()
        return [_row_to_save_slot(row) for row in rows]

    def save(self, slot: SaveSlot) -> None:
        self._conn.execute(
            """
            INSERT INTO save_slots (
                id, world_id, slot_index, label, snapshot_path,
                snapshot_version, world_time_at_save, checksum, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(world_id, slot_index) DO UPDATE SET
                id = excluded.id,
                label = excluded.label,
                snapshot_path = excluded.snapshot_path,
                snapshot_version = excluded.snapshot_version,
                world_time_at_save = excluded.world_time_at_save,
                checksum = excluded.checksum,
                created_at = excluded.created_at
            """,
            (
                str(slot.id),
                str(slot.world_id),
                slot.slot_index,
                slot.label,
                slot.snapshot_path,
                slot.snapshot_version,
                slot.world_time_at_save,
                slot.checksum,
                to_iso(slot.created_at) if slot.created_at else to_iso(_now_fallback()),
            ),
        )

    def delete(self, save_id: SaveId) -> None:
        self._conn.execute("DELETE FROM save_slots WHERE id = ?", (str(save_id),))


def _now_fallback():
    from novel_world.core.domain.timestamps import utc_now
    return utc_now()


def _row_to_world(row: sqlite3.Row) -> World:
    return World(
        id=WorldId(row["id"]),
        name=row["name"],
        description=row["description"],
        genre=row["genre"],
        rules=loads_json(row["rules_json"]),
        settings=loads_json(row["settings_json"]),
        schema_version=row["schema_version"],
        created_at=from_iso(row["created_at"]),
        updated_at=from_iso(row["updated_at"]),
    )


def _row_to_character(row: sqlite3.Row) -> Character:
    return Character(
        id=CharacterId(row["id"]),
        world_id=WorldId(row["world_id"]),
        name=row["name"],
        role=row["role"],
        profile=loads_json(row["profile_json"]),
        attributes=loads_json(row["attributes_json"]),
        metadata=loads_json(row["metadata_json"]),
        is_active=bool(row["is_active"]),
        created_at=from_iso(row["created_at"]),
        updated_at=from_iso(row["updated_at"]),
    )


def _row_to_state_entry(row: sqlite3.Row) -> StateEntry:
    scope: StateScope = row["scope"]
    return StateEntry(
        id=StateEntryId(row["id"]),
        world_id=WorldId(row["world_id"]),
        scope=scope,
        scope_id=CharacterId(row["scope_id"]) if row["scope_id"] else None,
        key=row["key"],
        value=loads_json(row["value_json"]),
        value_type=row["value_type"],
        updated_at=from_iso(row["updated_at"]),
    )


def _row_to_event(row: sqlite3.Row) -> Event:
    return Event(
        id=EventId(row["id"]),
        world_id=WorldId(row["world_id"]),
        seq=row["seq"],
        event_type=row["event_type"],
        world_time=row["world_time"],
        real_time=from_iso(row["real_time"]),
        actor_id=CharacterId(row["actor_id"]) if row["actor_id"] else None,
        payload=loads_json(row["payload_json"]),
        causation_id=EventId(row["causation_id"]) if row["causation_id"] else None,
        created_at=from_iso(row["created_at"]),
    )


def _row_to_save_slot(row: sqlite3.Row) -> SaveSlot:
    return SaveSlot(
        id=SaveId(row["id"]),
        world_id=WorldId(row["world_id"]),
        slot_index=row["slot_index"],
        label=row["label"],
        snapshot_path=row["snapshot_path"],
        snapshot_version=row["snapshot_version"],
        world_time_at_save=row["world_time_at_save"],
        checksum=row["checksum"],
        created_at=from_iso(row["created_at"]),
    )
