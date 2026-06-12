from __future__ import annotations

import json

from novel_world.modules.ai.domain.entities import ChatSession, new_session_id
from novel_world.modules.ai.services.lore_engine import LoreEngine
from novel_world.modules.ai.services.session_lore_service import SessionLoreService
from novel_world.modules.ai.services.prompt_context import merge_session_lore


def _session() -> ChatSession:
    return ChatSession(id=new_session_id(), provider_id="p1", model="m", config={})


def test_session_lore_crud_round_trip() -> None:
    session = _session()
    session, entry = SessionLoreService.create_entry(
        session,
        {"keys": ["chat"], "content": "Session only lore", "selective": True},
    )
    assert len(SessionLoreService.list_entries(session)) == 1
    session = SessionLoreService.update_entry(session, entry.id, {"content": "Updated"})
    assert SessionLoreService.get_entry(session, entry.id).content == "Updated"
    session = SessionLoreService.delete_entry(session, entry.id)
    assert SessionLoreService.list_entries(session) == []


def test_session_lore_import_st() -> None:
    session = _session()
    wi = {"entries": {"0": {"keys": ["a"], "content": "Session WI", "probability": 0.5}}}
    session, count = SessionLoreService.import_st(session, json.dumps(wi).encode("utf-8"))
    assert count == 1
    assert SessionLoreService.list_entries(session)[0].probability == 0.5


def test_merge_session_lore() -> None:
    from novel_world.modules.world.domain.lore_entry import LoreEntry

    world_entries = [LoreEntry(id="w1", content="world")]
    session_cfg = {"session_lore": [{"id": "s1", "content": "sess", "keys": ["k"], "scope": "session"}]}
    merged = merge_session_lore(world_entries, session_cfg)
    assert len(merged) == 2
