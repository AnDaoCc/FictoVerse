from __future__ import annotations

import uuid
from typing import NewType

WorldId = NewType("WorldId", str)
CharacterId = NewType("CharacterId", str)
StateEntryId = NewType("StateEntryId", str)
EventId = NewType("EventId", str)
SaveId = NewType("SaveId", str)


def new_world_id() -> WorldId:
    return WorldId(str(uuid.uuid4()))


def new_character_id() -> CharacterId:
    return CharacterId(str(uuid.uuid4()))


def new_state_entry_id() -> StateEntryId:
    return StateEntryId(str(uuid.uuid4()))


def new_event_id() -> EventId:
    return EventId(str(uuid.uuid4()))


def new_save_id() -> SaveId:
    return SaveId(str(uuid.uuid4()))
