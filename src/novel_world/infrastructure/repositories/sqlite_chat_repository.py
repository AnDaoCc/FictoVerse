from __future__ import annotations

import json
import sqlite3

from novel_world.core.domain.timestamps import from_iso, to_iso, utc_now
from novel_world.modules.ai.domain.entities import (
    ChatMemory,
    ChatSession,
    GroupMember,
    MessageRole,
    MessageStatus,
    SessionId,
    StoredChatMessage,
    new_memory_id,
    new_message_id,
)


class SqliteChatRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    @property
    def connection(self) -> sqlite3.Connection:
        return self._conn

    def create_session(self, session: ChatSession) -> None:
        now = utc_now()
        created = session.created_at or now
        updated = session.updated_at or now
        self._conn.execute(
            """
            INSERT INTO chat_sessions (
                id, world_id, title, provider_id, model,
                session_type, config_json, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                session.id,
                session.world_id,
                session.title,
                session.provider_id,
                session.model,
                session.session_type,
                json.dumps(session.config, ensure_ascii=False),
                to_iso(created),
                to_iso(updated),
            ),
        )

    def update_session(self, session: ChatSession) -> None:
        self._conn.execute(
            """
            UPDATE chat_sessions
            SET title = ?, config_json = ?, summary_content = ?, summary_until = ?, updated_at = ?
            WHERE id = ?
            """,
            (
                session.title,
                json.dumps(session.config, ensure_ascii=False),
                session.summary_content,
                session.summary_until,
                to_iso(session.updated_at or utc_now()),
                session.id,
            ),
        )

    def get_session(self, session_id: SessionId) -> ChatSession | None:
        row = self._conn.execute(
            "SELECT * FROM chat_sessions WHERE id = ?", (session_id,)
        ).fetchone()
        return _row_to_session(row) if row else None

    def list_sessions(self, *, world_id: str | None = None) -> list[ChatSession]:
        if world_id is None:
            rows = self._conn.execute(
                "SELECT * FROM chat_sessions WHERE world_id IS NULL AND session_type != 'group' "
                "ORDER BY updated_at DESC"
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM chat_sessions WHERE world_id = ? AND session_type != 'roleplay' "
                "ORDER BY updated_at DESC",
                (world_id,),
            ).fetchall()
        return [_row_to_session(row) for row in rows]

    def list_roleplay_sessions(
        self, *, world_id: str, character_id: str | None = None
    ) -> list[ChatSession]:
        if character_id:
            rows = self._conn.execute(
                "SELECT * FROM chat_sessions WHERE world_id = ? AND session_type = 'roleplay' "
                "ORDER BY updated_at DESC",
                (world_id,),
            ).fetchall()
            sessions = [_row_to_session(row) for row in rows]
            return [
                s
                for s in sessions
                if str((s.config or {}).get("character_id", "")) == character_id
            ]
        rows = self._conn.execute(
            "SELECT * FROM chat_sessions WHERE world_id = ? AND session_type = 'roleplay' "
            "ORDER BY updated_at DESC",
            (world_id,),
        ).fetchall()
        return [_row_to_session(row) for row in rows]

    def list_group_sessions(self) -> list[ChatSession]:
        rows = self._conn.execute(
            "SELECT * FROM chat_sessions WHERE session_type = 'group' ORDER BY updated_at DESC"
        ).fetchall()
        return [_row_to_session(row) for row in rows]

    def append_message(self, message: StoredChatMessage) -> None:
        self._conn.execute(
            """
            INSERT INTO chat_messages (
                id, session_id, role, content, thinking_content, status, speaker_json,
                parent_id, variants_json, active_variant, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                message.id,
                message.session_id,
                message.role,
                message.content,
                message.thinking_content,
                message.status,
                json.dumps(message.speaker, ensure_ascii=False) if message.speaker else "",
                message.parent_id or "",
                json.dumps(message.variants, ensure_ascii=False),
                message.active_variant,
                to_iso(message.created_at or utc_now()),
            ),
        )

    def get_message(self, message_id: str) -> StoredChatMessage | None:
        row = self._conn.execute(
            "SELECT * FROM chat_messages WHERE id = ?", (message_id,)
        ).fetchone()
        return _row_to_message(row) if row else None

    def delete_message(self, message_id: str) -> None:
        self._conn.execute("DELETE FROM chat_messages WHERE id = ?", (message_id,))

    def delete_messages_after(self, session_id: SessionId, after_created_at: str) -> None:
        self._conn.execute(
            "DELETE FROM chat_messages WHERE session_id = ? AND created_at > ?",
            (session_id, after_created_at),
        )

    def delete_messages_from(self, session_id: SessionId, from_created_at: str) -> None:
        self._conn.execute(
            "DELETE FROM chat_messages WHERE session_id = ? AND created_at >= ?",
            (session_id, from_created_at),
        )

    def update_message(self, message: StoredChatMessage) -> None:
        self._conn.execute(
            """
            UPDATE chat_messages
            SET content = ?, thinking_content = ?, status = ?,
                variants_json = ?, active_variant = ?
            WHERE id = ?
            """,
            (
                message.content,
                message.thinking_content,
                message.status,
                json.dumps(message.variants, ensure_ascii=False),
                message.active_variant,
                message.id,
            ),
        )

    def list_messages(self, session_id: SessionId) -> list[StoredChatMessage]:
        rows = self._conn.execute(
            "SELECT * FROM chat_messages WHERE session_id = ? ORDER BY created_at",
            (session_id,),
        ).fetchall()
        return [_row_to_message(row) for row in rows]

    def delete_session(self, session_id: SessionId) -> None:
        self._conn.execute("DELETE FROM chat_attachments WHERE session_id = ?", (session_id,))
        self._conn.execute(
            "DELETE FROM group_session_members WHERE session_id = ?", (session_id,)
        )
        self._conn.execute(
            "DELETE FROM chat_messages WHERE session_id = ?", (session_id,)
        )
        self._conn.execute("DELETE FROM chat_memories WHERE session_id = ?", (session_id,))
        self._conn.execute(
            "DELETE FROM chat_sessions WHERE id = ?", (session_id,)
        )

    def delete_sessions_by_world(self, world_id: str) -> None:
        rows = self._conn.execute(
            "SELECT id FROM chat_sessions WHERE world_id = ?", (world_id,)
        ).fetchall()
        for row in rows:
            self.delete_session(row["id"])

    def delete_sessions_by_provider(self, provider_id: str) -> int:
        rows = self._conn.execute(
            "SELECT id FROM chat_sessions WHERE provider_id = ?", (provider_id,)
        ).fetchall()
        for row in rows:
            self.delete_session(row["id"])
        return len(rows)

    # ----- group members -----

    def add_group_members(self, members: list[GroupMember]) -> None:
        for m in members:
            self._conn.execute(
                """
                INSERT OR REPLACE INTO group_session_members (
                    session_id, world_id, character_id, character_name, world_name, sort_order
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    m.session_id,
                    m.world_id,
                    m.character_id,
                    m.character_name,
                    m.world_name,
                    m.sort_order,
                ),
            )

    def list_group_members(self, session_id: SessionId) -> list[GroupMember]:
        rows = self._conn.execute(
            "SELECT * FROM group_session_members WHERE session_id = ? ORDER BY sort_order, character_name",
            (session_id,),
        ).fetchall()
        return [
            GroupMember(
                session_id=row["session_id"],
                world_id=row["world_id"],
                character_id=row["character_id"],
                character_name=row["character_name"],
                world_name=row["world_name"],
                sort_order=row["sort_order"],
            )
            for row in rows
        ]

    def count_group_members(self, session_id: SessionId) -> int:
        row = self._conn.execute(
            "SELECT COUNT(*) AS c FROM group_session_members WHERE session_id = ?",
            (session_id,),
        ).fetchone()
        return int(row["c"]) if row else 0

    def remove_group_member(
        self, session_id: SessionId, world_id: str, character_id: str
    ) -> None:
        self._conn.execute(
            """
            DELETE FROM group_session_members
            WHERE session_id = ? AND world_id = ? AND character_id = ?
            """,
            (session_id, world_id, character_id),
        )

    # ----- memories -----

    def save_memory(self, memory: ChatMemory) -> None:
        self._conn.execute(
            """
            INSERT INTO chat_memories (
                id, session_id, content, keywords_json, pinned, source_message_id, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                memory.id,
                memory.session_id,
                memory.content,
                json.dumps(memory.keywords, ensure_ascii=False),
                1 if memory.pinned else 0,
                memory.source_message_id,
                to_iso(memory.created_at or utc_now()),
            ),
        )

    def list_memories(self, session_id: SessionId, *, pinned_only: bool = False) -> list[ChatMemory]:
        if pinned_only:
            rows = self._conn.execute(
                "SELECT * FROM chat_memories WHERE session_id = ? AND pinned = 1 ORDER BY created_at",
                (session_id,),
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM chat_memories WHERE session_id = ? ORDER BY created_at",
                (session_id,),
            ).fetchall()
        return [_row_to_memory(row) for row in rows]

    def delete_memory(self, memory_id: str) -> None:
        self._conn.execute("DELETE FROM chat_memories WHERE id = ?", (memory_id,))

    def get_memory(self, memory_id: str) -> ChatMemory | None:
        row = self._conn.execute(
            "SELECT * FROM chat_memories WHERE id = ?", (memory_id,)
        ).fetchone()
        return _row_to_memory(row) if row else None

    def update_memory_pinned(self, memory_id: str, *, pinned: bool) -> None:
        self._conn.execute(
            "UPDATE chat_memories SET pinned = ? WHERE id = ?",
            (1 if pinned else 0, memory_id),
        )


def _row_to_memory(row: sqlite3.Row) -> ChatMemory:
    try:
        keywords = json.loads(row["keywords_json"] or "[]")
    except json.JSONDecodeError:
        keywords = []
    return ChatMemory(
        id=row["id"],
        session_id=row["session_id"],
        content=row["content"],
        keywords=[str(k) for k in keywords] if isinstance(keywords, list) else [],
        pinned=bool(row["pinned"]),
        source_message_id=row["source_message_id"] or "",
        created_at=from_iso(row["created_at"]),
    )


def _row_to_session(row: sqlite3.Row) -> ChatSession:
    keys = row.keys()
    summary_content = row["summary_content"] if "summary_content" in keys else ""
    summary_until = row["summary_until"] if "summary_until" in keys else 0
    session_type = row["session_type"] if "session_type" in keys else "chat"
    config_raw = row["config_json"] if "config_json" in keys else "{}"
    try:
        config = json.loads(config_raw) if config_raw else {}
    except (json.JSONDecodeError, TypeError):
        config = {}
    return ChatSession(
        id=row["id"],
        world_id=row["world_id"],
        title=row["title"],
        provider_id=row["provider_id"],
        model=row["model"],
        session_type=session_type or "chat",
        config=config if isinstance(config, dict) else {},
        summary_content=summary_content or "",
        summary_until=summary_until or 0,
        created_at=from_iso(row["created_at"]),
        updated_at=from_iso(row["updated_at"]),
    )


def _row_to_message(row: sqlite3.Row) -> StoredChatMessage:
    role: MessageRole = row["role"]
    keys = row.keys()
    thinking = row["thinking_content"] if "thinking_content" in keys else ""
    status: MessageStatus = row["status"] if "status" in keys else "done"
    speaker_raw = row["speaker_json"] if "speaker_json" in keys else ""
    speaker: dict[str, str] | None = None
    if speaker_raw:
        try:
            parsed = json.loads(speaker_raw)
            if isinstance(parsed, dict):
                speaker = {str(k): str(v) for k, v in parsed.items()}
        except (json.JSONDecodeError, TypeError):
            speaker = None
    parent_id = row["parent_id"] if "parent_id" in keys else ""
    variants_raw = row["variants_json"] if "variants_json" in keys else "[]"
    active_variant = row["active_variant"] if "active_variant" in keys else 0
    variants: list[dict[str, str]] = []
    if variants_raw:
        try:
            parsed_v = json.loads(variants_raw)
            if isinstance(parsed_v, list):
                variants = [v for v in parsed_v if isinstance(v, dict)]
        except json.JSONDecodeError:
            variants = []
    return StoredChatMessage(
        id=row["id"],
        session_id=row["session_id"],
        role=role,
        content=row["content"],
        thinking_content=thinking or "",
        status=status or "done",
        speaker=speaker,
        parent_id=parent_id or "",
        variants=variants,
        active_variant=int(active_variant or 0),
        created_at=from_iso(row["created_at"]),
    )


def new_stored_message(
    session_id: SessionId,
    role: MessageRole,
    content: str,
    *,
    thinking_content: str = "",
    status: MessageStatus = "done",
    speaker: dict[str, str] | None = None,
    parent_id: str = "",
) -> StoredChatMessage:
    return StoredChatMessage(
        id=new_message_id(),
        session_id=session_id,
        role=role,
        content=content,
        thinking_content=thinking_content,
        status=status,
        speaker=speaker,
        parent_id=parent_id,
        created_at=utc_now(),
    )
