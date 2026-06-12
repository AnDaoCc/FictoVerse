from __future__ import annotations

from datetime import datetime
from typing import Any

from novel_world.core.domain.ids import (
    CharacterId,
    EventId,
    StateEntryId,
    WorldId,
)
from novel_world.core.domain.schema_version import SCHEMA_VERSION
from novel_world.core.exceptions import ValidationError
from novel_world.modules.character.domain.entities import Character
from novel_world.modules.event.domain.entities import Event
from novel_world.modules.state.domain.entities import StateEntry, StateScope
from novel_world.modules.world.domain.entities import World


def _parse_dt(value: str | None) -> datetime | None:
    if value is None:
        return None
    return datetime.fromisoformat(value)


def world_from_dict(data: dict[str, Any]) -> World:
    return World(
        id=WorldId(data["id"]),
        name=data["name"],
        description=data.get("description", ""),
        genre=data.get("genre", ""),
        rules=data.get("rules", {}),
        settings=data.get("settings", {}),
        schema_version=data.get("schema_version", SCHEMA_VERSION),
        created_at=_parse_dt(data.get("created_at")),
        updated_at=_parse_dt(data.get("updated_at")),
    )


def character_from_dict(data: dict[str, Any]) -> Character:
    return Character(
        id=CharacterId(data["id"]),
        world_id=WorldId(data["world_id"]),
        name=data["name"],
        role=data.get("role", "npc"),
        profile=data.get("profile", {}),
        attributes=data.get("attributes", {}),
        metadata=data.get("metadata", {}),
        is_active=bool(data.get("is_active", True)),
        created_at=_parse_dt(data.get("created_at")),
        updated_at=_parse_dt(data.get("updated_at")),
    )


def state_entry_from_dict(data: dict[str, Any]) -> StateEntry:
    scope: StateScope = data["scope"]
    return StateEntry(
        id=StateEntryId(data["id"]),
        world_id=WorldId(data["world_id"]),
        scope=scope,
        scope_id=CharacterId(data["scope_id"]) if data.get("scope_id") else None,
        key=data["key"],
        value=data["value"],
        value_type=data["value_type"],
        updated_at=_parse_dt(data.get("updated_at")),
    )


def event_from_dict(data: dict[str, Any]) -> Event:
    return Event(
        id=EventId(data["id"]),
        world_id=WorldId(data["world_id"]),
        seq=int(data["seq"]),
        event_type=data["event_type"],
        world_time=data.get("world_time"),
        real_time=datetime.fromisoformat(data["real_time"]),
        actor_id=CharacterId(data["actor_id"]) if data.get("actor_id") else None,
        payload=data.get("payload", {}),
        causation_id=EventId(data["causation_id"]) if data.get("causation_id") else None,
        created_at=_parse_dt(data.get("created_at")),
    )


def decode_snapshot(data: dict[str, Any]) -> tuple[World, list[Character], list[StateEntry], list[Event]]:
    version = data.get("snapshot_version")
    if version is None:
        raise ValidationError("快照缺少 snapshot_version。")
    world = world_from_dict(data["world"])
    characters = [character_from_dict(item) for item in data.get("characters", [])]
    state_entries = [state_entry_from_dict(item) for item in data.get("state_entries", [])]
    events = [event_from_dict(item) for item in data.get("events", [])]
    return world, characters, state_entries, events
