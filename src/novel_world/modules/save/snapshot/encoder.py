from __future__ import annotations

from typing import Any

from novel_world.core.domain.schema_version import SNAPSHOT_VERSION
from novel_world.modules.character.domain.entities import Character
from novel_world.modules.event.domain.entities import Event
from novel_world.modules.state.domain.entities import StateEntry
from novel_world.modules.world.domain.entities import World


def world_to_dict(world: World) -> dict[str, Any]:
    return {
        "id": str(world.id),
        "name": world.name,
        "description": world.description,
        "genre": world.genre,
        "rules": world.rules,
        "settings": world.settings,
        "schema_version": world.schema_version,
        "created_at": world.created_at.isoformat() if world.created_at else None,
        "updated_at": world.updated_at.isoformat() if world.updated_at else None,
    }


def character_to_dict(character: Character) -> dict[str, Any]:
    return {
        "id": str(character.id),
        "world_id": str(character.world_id),
        "name": character.name,
        "role": character.role,
        "profile": character.profile,
        "attributes": character.attributes,
        "metadata": character.metadata,
        "is_active": character.is_active,
        "created_at": character.created_at.isoformat() if character.created_at else None,
        "updated_at": character.updated_at.isoformat() if character.updated_at else None,
    }


def state_entry_to_dict(entry: StateEntry) -> dict[str, Any]:
    return {
        "id": str(entry.id),
        "world_id": str(entry.world_id),
        "scope": entry.scope,
        "scope_id": str(entry.scope_id) if entry.scope_id else None,
        "key": entry.key,
        "value": entry.value,
        "value_type": entry.value_type,
        "updated_at": entry.updated_at.isoformat() if entry.updated_at else None,
    }


def event_to_dict(event: Event) -> dict[str, Any]:
    return {
        "id": str(event.id),
        "world_id": str(event.world_id),
        "seq": event.seq,
        "event_type": event.event_type,
        "world_time": event.world_time,
        "real_time": event.real_time.isoformat(),
        "actor_id": str(event.actor_id) if event.actor_id else None,
        "payload": event.payload,
        "causation_id": str(event.causation_id) if event.causation_id else None,
        "created_at": event.created_at.isoformat() if event.created_at else None,
    }


def encode_snapshot(
    world: World,
    characters: list[Character],
    state_entries: list[StateEntry],
    events: list[Event],
) -> dict[str, Any]:
    event_seq_cursor = max((event.seq for event in events), default=0)
    return {
        "snapshot_version": SNAPSHOT_VERSION,
        "world_id": str(world.id),
        "world": world_to_dict(world),
        "characters": [character_to_dict(c) for c in characters],
        "state_entries": [state_entry_to_dict(e) for e in state_entries],
        "events": [event_to_dict(e) for e in events],
        "meta": {
            "event_seq_cursor": event_seq_cursor,
        },
    }
