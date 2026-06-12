from __future__ import annotations

from collections.abc import Iterator
from typing import Any

from novel_world.core.domain.timestamps import to_iso, utc_now
from novel_world.core.exceptions import NotFoundError, ValidationError
from novel_world.infrastructure.repositories.sqlite_chat_repository import (
    SqliteChatRepository,
    new_stored_message,
)
from novel_world.modules.ai.domain.entities import SessionId, StoredChatMessage
from novel_world.modules.ai.ports.llm_provider import StreamChunk
from novel_world.modules.ai.services.chat_service import ChatService
from novel_world.modules.ai.services.group_chat_service import GroupChatService
from novel_world.modules.ai.services.roleplay_service import RoleplayService


class MessageOpsService:
    def __init__(
        self,
        chat_repo: SqliteChatRepository,
        roleplay: RoleplayService,
        chat: ChatService,
        group_chat: GroupChatService,
    ) -> None:
        self._repo = chat_repo
        self._roleplay = roleplay
        self._chat = chat
        self._group = group_chat

    def regenerate(
        self, session_id: SessionId, message_id: str, *, swipe: bool = False
    ) -> Iterator[StreamChunk] | Iterator[dict[str, Any]]:
        session = self._require_session(session_id)
        msg = self._require_message(session_id, message_id)
        if msg.role != "assistant":
            raise ValidationError("只能重新生成助手消息。")
        if session.session_type == "group" and not msg.speaker:
            raise ValidationError("群聊中只能重新生成角色消息。")

        if swipe and msg.content.strip():
            msg.variants.append(
                {"content": msg.content, "thinking_content": msg.thinking_content or ""}
            )
            msg.active_variant = len(msg.variants)
            msg.content = ""
            msg.thinking_content = ""
            msg.status = "streaming"
            self._repo.update_message(msg)
            yield from self._stream_regenerate(session, message_id=msg.id)
            return

        self._repo.delete_message(message_id)
        yield from self._stream_regenerate(session)

    def swipe(self, session_id: SessionId, message_id: str, *, direction: str) -> StoredChatMessage:
        msg = self._require_message(session_id, message_id)
        if not msg.variants:
            raise ValidationError("没有可切换的候选回复。")
        idx = msg.active_variant
        if direction == "next":
            idx = min(idx + 1, len(msg.variants) - 1)
        elif direction == "prev":
            idx = max(idx - 1, 0)
        else:
            raise ValidationError("direction 必须为 prev 或 next。")
        if idx == msg.active_variant:
            return msg
        variant = msg.variants[idx]
        msg.active_variant = idx
        msg.content = variant.get("content", "")
        msg.thinking_content = variant.get("thinking_content", "")
        msg.status = "done"
        self._repo.update_message(msg)
        return msg

    def edit(
        self,
        session_id: SessionId,
        message_id: str,
        content: str,
        *,
        regenerate_after: bool = False,
        fork: bool = False,
    ) -> StoredChatMessage:
        session = self._require_session(session_id)
        msg = self._require_message(session_id, message_id)
        from novel_world.infrastructure.user_preferences import get_user_prefs
        from novel_world.modules.ai.services.regex_engine import RegexEngine
        from novel_world.modules.ai.services.stscript_integration import apply_stscript

        prefs = get_user_prefs(self._repo.connection)
        cleaned = content.strip()
        cleaned, scope_patch = apply_stscript(
            "edit", cleaned, user_prefs=prefs, session_config=session.config
        )
        if scope_patch:
            session.config = {**(session.config or {}), **scope_patch}
            self._repo.update_session(session)
        regex = RegexEngine.from_prefs_and_session(prefs, session.config)
        cleaned = regex.apply_on_edit(cleaned)
        if fork:
            fork_msg = new_stored_message(
                session_id,
                msg.role,
                cleaned,
                parent_id=msg.parent_id or msg.id,
                speaker=msg.speaker,
            )
            self._repo.append_message(fork_msg)
            return fork_msg
        msg.content = cleaned
        self._repo.update_message(msg)
        if regenerate_after:
            created_at = to_iso(msg.created_at or utc_now())
            self._repo.delete_messages_after(session_id, created_at)
        return msg

    def list_branches(self, session_id: SessionId) -> list[dict[str, Any]]:
        messages = self._repo.list_messages(session_id)
        by_parent: dict[str, list[StoredChatMessage]] = {}
        for m in messages:
            pid = m.parent_id or ""
            by_parent.setdefault(pid, []).append(m)
        roots = [m for m in messages if not m.parent_id]
        out: list[dict[str, Any]] = []
        for root in roots[:20]:
            out.append(
                {
                    "id": root.id,
                    "role": root.role,
                    "preview": root.content[:80],
                    "children": len(by_parent.get(root.id, [])),
                }
            )
        return out

    def stream_after_edit(self, session_id: SessionId) -> Iterator[StreamChunk] | Iterator[dict[str, Any]]:
        session = self._require_session(session_id)
        yield from self._stream_regenerate(session)

    def delete(
        self, session_id: SessionId, message_id: str, *, cascade: bool = False
    ) -> None:
        msg = self._require_message(session_id, message_id)
        if cascade:
            self._repo.delete_messages_from(session_id, to_iso(msg.created_at or utc_now()))
        else:
            self._repo.delete_message(message_id)

    def _stream_regenerate(
        self, session, *, message_id: str | None = None
    ) -> Iterator[StreamChunk] | Iterator[dict[str, Any]]:
        if session.session_type == "roleplay":
            yield from self._roleplay.stream_regenerate(session.id, assistant_message_id=message_id)
        elif session.session_type == "group":
            yield from self._group.stream_regenerate(session.id, assistant_message_id=message_id)
        else:
            yield from self._chat.stream_regenerate(session.id, assistant_message_id=message_id)

    def _require_session(self, session_id: SessionId):
        session = self._repo.get_session(session_id)
        if session is None:
            raise NotFoundError(f"会话不存在: {session_id}")
        return session

    def _require_message(self, session_id: SessionId, message_id: str) -> StoredChatMessage:
        msg = self._repo.get_message(message_id)
        if msg is None or msg.session_id != session_id:
            raise NotFoundError(f"消息不存在: {message_id}")
        return msg
