"""会话级 Lorebook CRUD（存 session.config.session_lore）。"""
from __future__ import annotations

import json
from typing import Any

from novel_world.core.domain.timestamps import utc_now
from novel_world.core.exceptions import NotFoundError, ValidationError
from novel_world.modules.ai.domain.entities import ChatSession
from novel_world.modules.ai.services.lore_engine import LoreEngine
from novel_world.modules.world.domain.lore_entry import LoreEntry, new_lore_entry_id
from novel_world.modules.world.services.st_lore_codec import parse_st_world_info_bytes, parse_st_world_info


class SessionLoreService:
    @staticmethod
    def list_entries(session: ChatSession) -> list[LoreEntry]:
        return LoreEngine.session_lore_from_config(session.config)

    @staticmethod
    def get_entry(session: ChatSession, entry_id: str) -> LoreEntry:
        for entry in SessionLoreService.list_entries(session):
            if entry.id == entry_id:
                return entry
        raise NotFoundError(f"会话 Lore 条目不存在: {entry_id}")

    @staticmethod
    def save_entries(session: ChatSession, entries: list[LoreEntry]) -> ChatSession:
        config = dict(session.config or {})
        config["session_lore"] = [e.to_dict() for e in entries]
        session.config = config
        session.updated_at = utc_now()
        return session

    @staticmethod
    def create_entry(session: ChatSession, payload: dict[str, Any]) -> tuple[ChatSession, LoreEntry]:
        entries = SessionLoreService.list_entries(session)
        entry = LoreEntry.from_dict({**payload, "id": new_lore_entry_id(), "scope": "session", "source": "session"})
        if not entry.content.strip():
            raise ValidationError("Lore 内容不能为空。")
        entries.append(entry)
        return SessionLoreService.save_entries(session, entries), entry

    @staticmethod
    def update_entry(session: ChatSession, entry_id: str, payload: dict[str, Any]) -> ChatSession:
        entries = SessionLoreService.list_entries(session)
        found = False
        for i, entry in enumerate(entries):
            if entry.id != entry_id:
                continue
            merged = {**entry.to_dict(), **payload, "id": entry_id, "scope": "session", "source": "session"}
            entries[i] = LoreEntry.from_dict(merged)
            found = True
            break
        if not found:
            raise NotFoundError(f"会话 Lore 条目不存在: {entry_id}")
        return SessionLoreService.save_entries(session, entries)

    @staticmethod
    def delete_entry(session: ChatSession, entry_id: str) -> ChatSession:
        entries = [e for e in SessionLoreService.list_entries(session) if e.id != entry_id]
        if len(entries) == len(SessionLoreService.list_entries(session)):
            raise NotFoundError(f"会话 Lore 条目不存在: {entry_id}")
        return SessionLoreService.save_entries(session, entries)

    @staticmethod
    def import_st(session: ChatSession, data: bytes, *, mode: str = "merge") -> tuple[ChatSession, int]:
        parsed = parse_st_world_info_bytes(data)
        imported = parse_st_world_info(parsed, scope="session", source="session")
        if not imported:
            raise ValidationError("未解析到有效 Lore 条目。")
        existing = SessionLoreService.list_entries(session)
        if mode == "replace":
            merged = imported
        else:
            by_ref = {e.source_ref: e for e in existing if e.source_ref}
            merged = list(existing)
            for item in imported:
                if item.source_ref and item.source_ref in by_ref:
                    idx = next(i for i, e in enumerate(merged) if e.source_ref == item.source_ref)
                    item.id = merged[idx].id
                    merged[idx] = item
                else:
                    merged.append(item)
        session = SessionLoreService.save_entries(session, merged)
        return session, len(imported)

    @staticmethod
    def export_st(session: ChatSession) -> dict[str, Any]:
        from novel_world.modules.world.services.st_lore_codec import export_st_world_info

        return export_st_world_info(SessionLoreService.list_entries(session))
