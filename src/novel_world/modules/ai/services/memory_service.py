from __future__ import annotations

import json
import uuid

from novel_world.core.domain.timestamps import to_iso, utc_now
from novel_world.infrastructure.repositories.sqlite_chat_repository import SqliteChatRepository
from novel_world.modules.ai.domain.entities import ChatMemory, SessionId, new_memory_id


class MemoryService:
    def __init__(self, chat_repo: SqliteChatRepository) -> None:
        self._repo = chat_repo

    def pin(
        self,
        session_id: SessionId,
        content: str,
        *,
        keywords: list[str] | None = None,
        message_id: str = "",
        pinned: bool = True,
    ) -> ChatMemory:
        mem = ChatMemory(
            id=new_memory_id(),
            session_id=session_id,
            content=content.strip(),
            keywords=keywords or [],
            pinned=pinned,
            source_message_id=message_id,
            created_at=utc_now(),
        )
        self._repo.save_memory(mem)
        return mem

    def list(self, session_id: SessionId, *, pinned_only: bool = False) -> list[ChatMemory]:
        return self._repo.list_memories(session_id, pinned_only=pinned_only)

    def delete(self, memory_id: str) -> None:
        self._repo.delete_memory(memory_id)

    def set_pinned(self, memory_id: str, *, pinned: bool) -> ChatMemory:
        mem = self._repo.get_memory(memory_id)
        if mem is None:
            from novel_world.core.exceptions import NotFoundError

            raise NotFoundError(f"记忆不存在: {memory_id}")
        self._repo.update_memory_pinned(memory_id, pinned=pinned)
        mem.pinned = pinned
        return mem

    def select_for_prompt(
        self, session_id: SessionId, scan_text: str, budget: int = 800
    ) -> tuple[str, list[str]]:
        memories = self._repo.list_memories(session_id)
        if not memories:
            return "", []

        selected: list[ChatMemory] = []
        for m in memories:
            if m.pinned:
                selected.append(m)

        hay = scan_text.lower()
        for m in memories:
            if m.pinned or m in selected:
                continue
            for kw in m.keywords:
                if kw.lower() in hay:
                    selected.append(m)
                    break

        lines: list[str] = []
        used = 0
        for m in selected:
            est = max(1, len(m.content) // 2)
            if used + est > budget:
                continue
            used += est
            lines.append(m.content)

        if not lines:
            return "", []
        block = "【需要记住的信息】\n" + "\n".join(f"- {ln}" for ln in lines)
        return block, lines
