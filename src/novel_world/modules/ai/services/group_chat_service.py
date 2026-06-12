from __future__ import annotations

import json
import re
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from novel_world.bootstrap.app_factory import AppFactory, create_app
from novel_world.core.domain.ids import CharacterId, WorldId
from novel_world.core.domain.timestamps import utc_now
from novel_world.core.exceptions import NotFoundError, ValidationError
from novel_world.infrastructure.repositories.sqlite_chat_repository import (
    SqliteChatRepository,
    new_stored_message,
)
from novel_world.modules.ai.domain.entities import (
    ChatMessage,
    ChatSession,
    GroupMember,
    SessionId,
    new_session_id,
)
from novel_world.modules.ai.ports.llm_provider import StreamChunk
from novel_world.modules.ai.services.lore_engine import LoreEngine
from novel_world.modules.ai.services.memory_service import MemoryService
from novel_world.modules.ai.services.prompt_assembler import PromptAssembler
from novel_world.modules.ai.services.prompt_context import (
    build_scan_text,
    load_group_lore_entries,
    persist_lore_state,
    scan_lore_for_session,
)
from novel_world.modules.ai.services.chat_service import (
    _compact_mapping,
    _format_character,
)
from novel_world.modules.ai.services.command_parser import parse_at_mention, parse_command
from novel_world.modules.ai.services.user_persona import (
    format_persona_for_prompt,
    format_user_transcript_line,
    merge_session_persona,
    store_persona,
)
from novel_world.modules.extensions.hook_bus import run_hooks

DEFAULT_MAX_ROUND = 5
DEFAULT_MAX_PER_CHARACTER = 0
HARD_MAX_ROUND = 20
EMPTY_REPLY_MAX_ATTEMPTS = 3

# 群聊历史发送给模型时，最多带入的近期气泡数
GROUP_HISTORY_LIMIT = 14

# 进程级停止标记：群聊流式请求与「停止」请求来自不同的 HTTP 连接，
# 各自会新建一个 GroupChatService 实例，因此取消状态必须跨实例共享。
_CANCEL_FLAGS: dict[str, bool] = {}

GROUP_RULES = (
    "你正在主持一个角色群聊，成员来自一个或多个不同的虚构世界。"
    "每次回复，你都要从下列成员中挑选**一个最适合接话**的角色，"
    "以该角色的第一人称身份和口吻说话，像微信/QQ 群聊一样自然、口语化、简短（一般 1-3 句）。"
    "要符合该角色的性格、设定与人物关系；可以回应别人刚才说的话；"
    "若成员来自不同世界，可以自然体现世界观差异与碰撞。"
    "尽量不要连续两次都让同一个角色发言。"
)


class GroupChatService:
    def __init__(
        self,
        chat_repo: SqliteChatRepository,
        provider_registry: ProviderRegistry,
        world_app: AppFactory | None = None,
        base_dir: Path | None = None,
        memory_service: MemoryService | None = None,
        prompt_assembler: PromptAssembler | None = None,
        default_session_config: dict[str, Any] | None = None,
    ) -> None:
        self._chat_repo = chat_repo
        self._providers = provider_registry
        self._world_app = world_app or create_app(base_dir)
        self._memory = memory_service
        self._assembler = prompt_assembler or PromptAssembler()
        self._default_config = default_session_config or {}
        # session_id -> 请求停止标记（自动接话时检查），进程级共享
        self._cancel_flags = _CANCEL_FLAGS

    # ---------------- 会话与成员 ----------------

    def list_sessions(self) -> list[ChatSession]:
        return self._chat_repo.list_group_sessions()

    def get_session(self, session_id: SessionId) -> ChatSession:
        session = self._chat_repo.get_session(session_id)
        if session is None or session.session_type != "group":
            raise NotFoundError(f"群聊不存在: {session_id}")
        return session

    def get_members(self, session_id: SessionId) -> list[GroupMember]:
        return self._chat_repo.list_group_members(session_id)

    def get_messages(self, session_id: SessionId):
        return self._chat_repo.list_messages(session_id)

    def delete_session(self, session_id: SessionId) -> None:
        self.get_session(session_id)
        self._chat_repo.delete_session(session_id)
        self._cancel_flags.pop(session_id, None)

    def request_stop(self, session_id: SessionId) -> None:
        self._cancel_flags[session_id] = True

    def update_persona(self, session_id: SessionId, *, name: str, description: str) -> ChatSession:
        session = self.get_session(session_id)
        config = dict(session.config or {})
        config["user_persona"] = store_persona(name, description)
        session.config = config
        session.updated_at = utc_now()
        self._chat_repo.update_session(session)
        return session

    def create_group(
        self,
        provider_id: str,
        model: str,
        *,
        title: str,
        members: list[dict[str, str]],
    ) -> ChatSession:
        provider = self._providers.get(provider_id)
        if not model.strip():
            model = str(provider.config.get("model", "")).strip()
        if not model:
            raise ValidationError("必须指定模型名称。")

        resolved = self._resolve_members(members)
        if len(resolved) < 2:
            raw = len(members) if isinstance(members, list) else 0
            if raw >= 2:
                raise ValidationError(
                    f"已选择 {raw} 个角色，但只有 {len(resolved)} 个有效。"
                    "请刷新页面后重新勾选，或确认角色仍存在于对应世界中。"
                )
            raise ValidationError("群聊至少需要选择两个角色。")

        now = utc_now()
        session = ChatSession(
            id=new_session_id(),
            world_id=None,
            title=title.strip() or "角色群聊",
            provider_id=provider_id,
            model=model,
            session_type="group",
            config={
                "max_round": DEFAULT_MAX_ROUND,
                "max_per_character": DEFAULT_MAX_PER_CHARACTER,
                "prompt_layers": dict(self._default_config.get("default_prompt_layers") or {}),
                "generation": dict(self._default_config.get("default_generation") or {}),
                "lore_token_budget": int(self._default_config.get("lore_token_budget") or 2000),
            },
            created_at=now,
            updated_at=now,
        )
        self._chat_repo.create_session(session)
        members_to_add = [
            GroupMember(
                session_id=session.id,
                world_id=m["world_id"],
                character_id=m["character_id"],
                character_name=m["character_name"],
                world_name=m["world_name"],
                sort_order=i,
            )
            for i, m in enumerate(resolved)
        ]
        self._chat_repo.add_group_members(members_to_add)
        return session

    def add_members(
        self, session_id: SessionId, members: list[dict[str, str]]
    ) -> list[GroupMember]:
        self.get_session(session_id)
        resolved = self._resolve_members(members)
        existing = {(m.world_id, m.character_id) for m in self.get_members(session_id)}
        to_add: list[GroupMember] = []
        base_order = len(existing)
        for i, m in enumerate(resolved):
            key = (m["world_id"], m["character_id"])
            if key in existing:
                continue
            to_add.append(
                GroupMember(
                    session_id=session_id,
                    world_id=m["world_id"],
                    character_id=m["character_id"],
                    character_name=m["character_name"],
                    world_name=m["world_name"],
                    sort_order=base_order + i,
                )
            )
        if to_add:
            self._chat_repo.add_group_members(to_add)
        if self._chat_repo.count_group_members(session_id) < 2:
            raise ValidationError("群聊至少需要两个成员。")
        return self.get_members(session_id)

    def remove_member(
        self, session_id: SessionId, world_id: str, character_id: str
    ) -> list[GroupMember]:
        session = self.get_session(session_id)
        if self._chat_repo.count_group_members(session_id) <= 2:
            raise ValidationError("群聊至少保留两个成员。")
        self._chat_repo.remove_group_member(session_id, world_id, character_id)
        config = dict(session.config or {})
        muted = [x for x in config.get("muted", []) if x != character_id]
        config["muted"] = muted
        session.config = config
        session.updated_at = utc_now()
        self._chat_repo.update_session(session)
        return self.get_members(session_id)

    def set_member_muted(
        self, session_id: SessionId, character_id: str, *, muted: bool
    ) -> ChatSession:
        session = self.get_session(session_id)
        member_ids = {m.character_id for m in self.get_members(session_id)}
        if character_id not in member_ids:
            raise NotFoundError(f"成员不存在: {character_id}")
        config = dict(session.config or {})
        muted_list = list(config.get("muted") or [])
        if muted and character_id not in muted_list:
            muted_list.append(character_id)
        elif not muted:
            muted_list = [x for x in muted_list if x != character_id]
        config["muted"] = muted_list
        session.config = config
        session.updated_at = utc_now()
        self._chat_repo.update_session(session)
        return session

    def _speaker_payload(self, member: GroupMember) -> dict[str, str]:
        from novel_world.modules.ai.services.tts_voice_resolver import build_speaker_payload

        avatar_url = f"/api/worlds/{member.world_id}/characters/{member.character_id}/avatar"
        rt = self._world_app.open_world(WorldId(member.world_id))
        try:
            character = rt.character.get(CharacterId(member.character_id))
            return build_speaker_payload(
                character,
                member.world_id,
                avatar_url=avatar_url,
                extra={"world_name": member.world_name},
            )
        except NotFoundError:
            return {
                "character_id": member.character_id,
                "world_id": member.world_id,
                "name": member.character_name,
                "world_name": member.world_name,
                "avatar_url": avatar_url,
                "tts_voice": "",
            }
        finally:
            rt.close()

    def _active_members(
        self, session: ChatSession, members: list[GroupMember]
    ) -> list[GroupMember]:
        muted = set(session.config.get("muted") or [])
        active = [m for m in members if m.character_id not in muted]
        return active if len(active) >= 2 else members

    def _resolve_members(self, members: list[dict[str, str]]) -> list[dict[str, str]]:
        """按世界分组打开世界数据，补全角色名/世界名，过滤无效项。"""
        by_world: dict[str, list[str]] = {}
        order: list[tuple[str, str]] = []
        for m in members:
            if not isinstance(m, dict):
                continue
            world_id = str(
                m.get("world_id") or m.get("worldId") or ""
            ).strip()
            char_id = str(
                m.get("character_id") or m.get("char_id") or m.get("characterId") or ""
            ).strip()
            if not world_id or not char_id:
                continue
            by_world.setdefault(world_id, []).append(char_id)
            order.append((world_id, char_id))

        resolved_map: dict[tuple[str, str], dict[str, str]] = {}
        for world_id, char_ids in by_world.items():
            rt = self._world_app.open_world(WorldId(world_id))
            try:
                world = rt.world.get(WorldId(world_id))
                chars = {
                    str(c.id): c
                    for c in rt.character.list_by_world(world.id, active_only=False)
                }
            finally:
                rt.close()
            for char_id in char_ids:
                c = chars.get(char_id)
                if c is None:
                    continue
                resolved_map[(world_id, char_id)] = {
                    "world_id": world_id,
                    "character_id": char_id,
                    "character_name": c.name,
                    "world_name": world.name,
                }

        out: list[dict[str, str]] = []
        seen: set[tuple[str, str]] = set()
        for key in order:
            if key in resolved_map and key not in seen:
                out.append(resolved_map[key])
                seen.add(key)
        return out

    # ---------------- 接话生成 ----------------

    @staticmethod
    def _resolve_max_round(
        *,
        max_round: int = 0,
        max_replies: int = 0,
        max_total: int = 0,
        session: ChatSession | None = None,
    ) -> int:
        raw = int(max_round or 0)
        if raw <= 0:
            legacy = max(int(max_replies or 0), int(max_total or 0))
            if legacy > 0:
                raw = legacy
        if raw <= 0 and session is not None:
            cfg = session.config or {}
            raw = int(cfg.get("max_round") or 0)
            if raw <= 0:
                raw = max(
                    int(cfg.get("max_replies") or 0),
                    int(cfg.get("max_auto_total") or 0),
                )
        if raw <= 0:
            raw = DEFAULT_MAX_ROUND
        return max(1, min(raw, HARD_MAX_ROUND))

    def reply_round(
        self,
        session_id: SessionId,
        *,
        content: str = "",
        mode: str = "send",
        max_round: int = 0,
        max_replies: int = 0,
        max_total: int = 0,
        max_per_character: int = DEFAULT_MAX_PER_CHARACTER,
        force_character_id: str = "",
    ) -> Iterator[dict[str, Any]]:
        session = self.get_session(session_id)
        members = self.get_members(session_id)
        if len(members) < 2:
            raise ValidationError("该群聊成员不足，无法接话。")

        self._cancel_flags.pop(session_id, None)

        text = (content or "").strip()
        handled, text = parse_command(
            text, {"session_id": session_id, "memory": self._memory}
        )
        if handled:
            yield {"event": "done", "data": {"count": 0, "remembered": True}}
            return

        text, at_force = parse_at_mention(text, members)
        force_id = (force_character_id or at_force or "").strip()

        if text:
            from novel_world.infrastructure.user_preferences import get_user_prefs
            from novel_world.modules.ai.services.regex_engine import RegexEngine

            prefs = get_user_prefs(self._chat_repo.connection)
            regex = RegexEngine.from_prefs_and_session(prefs, session.config)
            text = regex.apply_user_input(text)
            text = run_hooks(
                "message.before_send",
                text,
                session_id=session_id,
                role="user",
            )
            user_msg = new_stored_message(session_id, "user", text)
            self._chat_repo.append_message(user_msg)
            yield {
                "event": "user_message",
                "data": {"content": text, "message_id": user_msg.id},
            }
        elif mode == "send":
            raise ValidationError("消息不能为空。")

        total_cap = self._resolve_max_round(
            max_round=max_round,
            max_replies=max_replies,
            max_total=max_total,
            session=session,
        )
        per_char_cap = max(0, int(max_per_character or 0))
        if per_char_cap <= 0 and session.config:
            per_char_cap = max(0, int(session.config.get("max_per_character") or 0))

        client = self._providers.build_client(session.provider_id)
        active_members = self._active_members(session, members)
        member_block = self._build_members_block(
            members, muted_ids=set(session.config.get("muted") or [])
        )

        produced = 0
        char_counts: dict[str, int] = {}
        empty_attempts = 0
        max_empty_attempts = total_cap * EMPTY_REPLY_MAX_ATTEMPTS

        while produced < total_cap:
            if self._cancel_flags.get(session_id):
                break
            excluded_ids: set[str] = set()
            if per_char_cap > 0:
                excluded_ids = {
                    cid
                    for cid, count in char_counts.items()
                    if count >= per_char_cap
                }
            eligible = [
                m for m in active_members if m.character_id not in excluded_ids
            ]
            if not eligible:
                break

            history = self._chat_repo.list_messages(session_id)
            speaker, reply = self._generate_one_reply(
                client,
                session.model,
                eligible,
                member_block,
                history,
                session=session,
                force_character_id=force_id or None,
                excluded_character_ids=excluded_ids,
            )
            if not reply:
                empty_attempts += 1
                if empty_attempts >= max_empty_attempts:
                    break
                continue
            empty_attempts = 0
            stored = new_stored_message(
                session_id,
                "assistant",
                reply,
                speaker=self._speaker_payload(speaker),
            )
            self._chat_repo.append_message(stored)
            produced += 1
            char_counts[speaker.character_id] = (
                char_counts.get(speaker.character_id, 0) + 1
            )
            yield {
                "event": "character_message",
                "data": {
                    "content": reply,
                    "message_id": stored.id,
                    "speaker": stored.speaker,
                },
            }
            display_content = run_hooks(
                "display.transform",
                reply,
                session_id=session.id,
            )
            if display_content != reply:
                yield {
                    "event": "display",
                    "data": {
                        "content": display_content,
                        "message_id": stored.id,
                    },
                }

        session.updated_at = utc_now()
        self._chat_repo.update_session(session)
        self._cancel_flags.pop(session_id, None)
        yield {"event": "done", "data": {"count": produced}}

    def stream_regenerate(
        self, session_id: SessionId, *, assistant_message_id: str | None = None
    ) -> Iterator[StreamChunk]:
        session = self.get_session(session_id)
        members = self.get_members(session_id)
        if assistant_message_id:
            msg = self._chat_repo.get_message(assistant_message_id)
            if msg is None or msg.session_id != session_id:
                raise NotFoundError(f"消息不存在: {assistant_message_id}")
            if msg.role != "assistant" or not msg.speaker:
                raise ValidationError("只能重新生成角色消息。")
            target_id = msg.speaker.get("character_id", "")
            msg.status = "streaming"
            msg.content = ""
            self._chat_repo.update_message(msg)
            stored = msg
        else:
            stored = None
            target_id = ""

        client = self._providers.build_client(session.provider_id)
        member_block = self._build_members_block(members)
        history = self._chat_repo.list_messages(session_id)
        speaker, reply = self._generate_one_reply(
            client,
            session.model,
            members,
            member_block,
            history,
            session=session,
            force_character_id=target_id or None,
        )
        if not reply:
            yield StreamChunk(kind="done")
            return
        if stored is None:
            stored = new_stored_message(
                session_id,
                "assistant",
                "",
                status="streaming",
                speaker=self._speaker_payload(speaker),
            )
            self._chat_repo.append_message(stored)
        stored.content = reply
        stored.status = "done"
        self._chat_repo.update_message(stored)
        yield StreamChunk(kind="content", text=reply)
        yield StreamChunk(kind="done")

    def preview_prompt(self, session_id: SessionId, user_input: str = "") -> dict[str, Any]:
        session = self.get_session(session_id)
        members = self.get_members(session_id)
        history = self._chat_repo.list_messages(session_id)
        member_block = self._build_members_block(members)
        scan_text = build_scan_text(history, user_input)
        layers, _gen, lore_budget, profile = self._assembler.merge_session_config(session.config)
        layers = run_hooks(
            "prompt.before_build",
            layers,
            session=session,
            session_id=session.id,
        )
        lore_entries = load_group_lore_entries(
            self._world_app,
            [
                (m.world_id, m.character_id, self._character_meta(m))
                for m in members
            ],
            session_config=session.config,
        )
        first_member = members[0] if members else None
        lore_result, lore_state = scan_lore_for_session(
            lore_entries,
            scan_text,
            session,
            token_budget=lore_budget,
            active_character_id=first_member.character_id if first_member else "",
            active_character_name=first_member.character_name if first_member else "",
            tick_user_turn=bool(user_input.strip()),
        )
        session = persist_lore_state(session, lore_state)
        self._chat_repo.update_session(session)
        memory_block, memory_lines = ("", [])
        if self._memory:
            memory_block, memory_lines = self._memory.select_for_prompt(session.id, scan_text)
        from novel_world.modules.ai.services.prompt_macros import build_macro_context
        from novel_world.modules.ai.services.user_persona import display_name, merge_session_persona

        persona = merge_session_persona(session.config)
        first_member = members[0] if members else None
        macro_ctx = build_macro_context(
            char_name=first_member.character_name if first_member else "",
            user_name=display_name(persona),
            persona=persona,
            world_name=first_member.world_id if first_member else "",
        )
        lore_parts = LoreEngine.format_result(lore_result)
        from novel_world.infrastructure.user_preferences import get_user_prefs
        from novel_world.modules.ai.services.regex_engine import RegexEngine

        regex = RegexEngine.from_prefs_and_session(
            get_user_prefs(self._chat_repo.connection), session.config
        )
        lore_parts = {k: regex.apply_prompt(v, macro_ctx=macro_ctx) for k, v in lore_parts.items()}
        system = self._assembler.build_system(
            profile=profile,
            base_parts=[GROUP_RULES, f"【群成员】\n{member_block}"],
            layers=layers,
            lore_parts=lore_parts,
            memory_block=memory_block,
            macro_ctx=macro_ctx,
        )
        debug = self._assembler.build_debug(
            system, [ChatMessage(role="system", content=system)], lore_result, memory_lines, layers
        )
        return {
            "system": debug.system,
            "messages": debug.messages,
            "lore_matched": debug.lore_matched,
            "memory_injected": debug.memory_injected,
            "estimated_tokens": debug.estimated_tokens,
        }

    def update_session_config(self, session_id: SessionId, config_patch: dict[str, Any]) -> ChatSession:
        session = self.get_session(session_id)
        config = dict(session.config or {})
        for key in (
            "prompt_layers",
            "generation",
            "lore_token_budget",
            "max_round",
            "max_per_character",
            "user_persona",
            "max_replies",
            "max_auto_total",
            "background",
            "display_scripts",
            "session_lore",
            "lore_state",
            "prompt_profile",
            "regex_scripts_override",
        ):
            if key in config_patch:
                config[key] = config_patch[key]
        session.config = config
        session.updated_at = utc_now()
        self._chat_repo.update_session(session)
        return session

    def _character_meta(self, member: GroupMember) -> dict | None:
        rt = self._world_app.open_world(WorldId(member.world_id))
        try:
            c = rt.character.get(CharacterId(member.character_id))
            return getattr(c, "metadata", None) or {}
        except Exception:
            return {}
        finally:
            rt.close()

    def _generate_one_reply(
        self,
        client,
        model,
        members,
        member_block,
        history,
        *,
        session: ChatSession | None = None,
        force_character_id: str | None = None,
        excluded_character_ids: set[str] | None = None,
    ) -> tuple[GroupMember, str]:
        excluded_character_ids = excluded_character_ids or set()
        pool = [m for m in members if m.character_id not in excluded_character_ids]
        if not pool:
            pool = list(members)
        user_persona = merge_session_persona(session.config if session else None)
        recent = [m for m in history if m.content.strip()][-GROUP_HISTORY_LIMIT:]
        transcript_lines: list[str] = []
        last_speaker_id = ""
        for m in recent:
            if m.role == "user":
                transcript_lines.append(
                    format_user_transcript_line(user_persona, m.content)
                )
            elif m.speaker:
                name = m.speaker.get("name", "角色")
                world_name = m.speaker.get("world_name", "")
                tag = f"{name}（{world_name}）" if world_name else name
                transcript_lines.append(f"{tag}：{m.content.strip()}")
                last_speaker_id = m.speaker.get("character_id", "")
        transcript = "\n".join(transcript_lines) if transcript_lines else "（暂无对话，请自然开场）"

        avoid = ""
        if last_speaker_id and not force_character_id:
            avoid = f"\n上一句的发言者 character_id 是「{last_speaker_id}」，请尽量换一个角色接话。"

        lore_block = ""
        memory_block = ""
        if session is not None:
            scan_text = build_scan_text(history)
            _, _gen, lore_budget, _ = self._assembler.merge_session_config(session.config)
            lore_entries = load_group_lore_entries(
                self._world_app,
                [(m.world_id, m.character_id, self._character_meta(m)) for m in members],
                session_config=session.config,
            )
            lore_result, lore_state = scan_lore_for_session(
                lore_entries,
                scan_text,
                session,
                token_budget=lore_budget,
                tick_user_turn=False,
            )
            session = persist_lore_state(session, lore_state)
            self._chat_repo.update_session(session)
            formatted = LoreEngine.format_result(lore_result)
            if formatted:
                lore_block = "\n\n【World Info】\n" + "\n\n".join(formatted.values())
            if self._memory:
                memory_block, _ = self._memory.select_for_prompt(session.id, scan_text)
                if memory_block:
                    memory_block = "\n\n" + memory_block

        force_line = ""
        if force_character_id:
            force_line = f"\n你必须让 character_id={force_character_id} 的角色发言。"

        exclude_line = ""
        if excluded_character_ids:
            exclude_line = (
                "\n以下角色在本轮已达发言次数上限，不可再选："
                + "、".join(sorted(excluded_character_ids))
                + "。"
            )

        _, generation, _, _ = self._assembler.merge_session_config(session.config if session else {})

        persona_block = format_persona_for_prompt(user_persona, mode="group")
        prompt = (
            f"{GROUP_RULES}\n\n"
            f"【用户身份】\n{persona_block}\n\n"
            f"【群成员】\n{member_block}\n\n"
            f"【最近的群聊记录】\n{transcript}\n"
            f"{avoid}{force_line}{exclude_line}{lore_block}{memory_block}\n\n"
            "请只输出一行 JSON，格式："
            '{"speaker_id": "<成员的 character_id>", "content": "<该角色这次要说的话>"}。'
            "不要输出 JSON 以外的任何内容、解释或思考过程。"
        )
        raw = client.complete(
            [ChatMessage(role="user", content=prompt)],
            model=model,
            generation=generation,
        ) or ""
        speaker, reply = self._parse_reply(raw, pool, last_speaker_id)
        if session is not None:
            from novel_world.infrastructure.user_preferences import get_user_prefs
            from novel_world.modules.ai.services.regex_engine import RegexEngine

            prefs = get_user_prefs(self._chat_repo.connection)
            regex = RegexEngine.from_prefs_and_session(prefs, session.config)
            reply = regex.apply_ai_output(reply)
            reply = run_hooks(
                "message.after_receive",
                reply,
                session_id=session.id,
                role="assistant",
            )
        return speaker, reply

    def _parse_reply(
        self, raw: str, members: list[GroupMember], last_speaker_id: str
    ) -> tuple[GroupMember, str]:
        by_id = {m.character_id: m for m in members}
        data = self._extract_json(raw)
        if data is not None:
            speaker_id = str(data.get("speaker_id", "")).strip()
            content = str(data.get("content", "")).strip()
            if content and speaker_id in by_id:
                return by_id[speaker_id], content
            if content:
                return self._fallback_speaker(members, last_speaker_id), content

        # 没有解析出 JSON：把整段文本当作发言，轮转选一个发言者
        text = raw.strip()
        if not text:
            return self._fallback_speaker(members, last_speaker_id), ""
        return self._fallback_speaker(members, last_speaker_id), text

    @staticmethod
    def _extract_json(raw: str) -> dict[str, Any] | None:
        text = raw.strip()
        if text.startswith("```"):
            text = re.sub(r"^```[a-zA-Z]*\n?", "", text)
            text = re.sub(r"\n?```$", "", text).strip()
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if not match:
            return None
        try:
            parsed = json.loads(match.group(0))
        except json.JSONDecodeError:
            return None
        return parsed if isinstance(parsed, dict) else None

    @staticmethod
    def _fallback_speaker(members: list[GroupMember], last_speaker_id: str) -> GroupMember:
        if last_speaker_id:
            for i, m in enumerate(members):
                if m.character_id == last_speaker_id:
                    return members[(i + 1) % len(members)]
        return members[0]

    def _build_members_block(
        self, members: list[GroupMember], *, muted_ids: set[str] | None = None
    ) -> str:
        muted_ids = muted_ids or set()
        by_world: dict[str, list[GroupMember]] = {}
        for m in members:
            by_world.setdefault(m.world_id, []).append(m)

        lines: list[str] = []
        for world_id, world_members in by_world.items():
            rt = self._world_app.open_world(WorldId(world_id))
            try:
                world = rt.world.get(WorldId(world_id))
                chars = {
                    str(c.id): c
                    for c in rt.character.list_by_world(world.id, active_only=False)
                }
                world_summary = self._world_summary(world)
            finally:
                rt.close()

            lines.append(f"◆ 世界《{world.name}》：{world_summary}")
            for m in world_members:
                c = chars.get(m.character_id)
                if c is None:
                    lines.append(f"  - {m.character_name}（character_id={m.character_id}）")
                    continue
                detail = _format_character(c)
                detail = detail.replace("\n", "\n  ")
                mute_note = "（暂不参与接话）" if m.character_id in muted_ids else ""
                lines.append(
                    f"  {detail}\n    · character_id={m.character_id}{(' · ' + mute_note) if mute_note else ''}"
                )
        return "\n".join(lines)

    @staticmethod
    def _world_summary(world) -> str:
        segs: list[str] = []
        if getattr(world, "genre", ""):
            segs.append(f"类型 {world.genre}")
        if getattr(world, "description", ""):
            segs.append(world.description)
        rules = _compact_mapping(getattr(world, "rules", {}))
        if rules:
            segs.append(f"规则 {rules}")
        settings = _compact_mapping(getattr(world, "settings", {}))
        if settings:
            segs.append(f"设定 {settings}")
        return "；".join(segs) if segs else "（无额外设定）"
