from __future__ import annotations

import json
import re
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from novel_world.bootstrap.app_factory import AppFactory, create_app
from novel_world.bootstrap.config import AppConfig, default_config
from novel_world.core.domain.ids import CharacterId, WorldId
from novel_world.core.domain.timestamps import utc_now
from novel_world.core.exceptions import NotFoundError, ValidationError
from novel_world.infrastructure.repositories.sqlite_chat_repository import (
    SqliteChatRepository,
    new_stored_message,
)
from novel_world.modules.ai.domain.entities import ChatMessage, ChatSession, SessionId, new_session_id
from novel_world.modules.ai.domain.generation_config import GenerationConfig
from novel_world.modules.ai.domain.prompt_layers import PromptLayers
from novel_world.modules.ai.services.command_parser import parse_command
from novel_world.modules.ai.services.lore_engine import LoreEngine
from novel_world.modules.ai.services.memory_service import MemoryService
from novel_world.modules.ai.services.prompt_assembler import PromptAssembler
from novel_world.modules.ai.services.prompt_context import (
    build_scan_text,
    load_lore_entries,
    persist_lore_state,
    scan_lore_for_session,
)
from novel_world.modules.ai.services.prompt_macros import apply_macros, build_macro_context
from novel_world.modules.extensions.hook_bus import run_hooks
from novel_world.modules.ai.ports.llm_provider import StreamChunk
from novel_world.modules.ai.services.chat_service import (
    HISTORY_KEEP_RECENT,
    HISTORY_SUMMARY_TRIGGER,
    STREAM_PERSIST_INTERVAL,
    _compact_mapping,
    _format_character,
)
from novel_world.modules.ai.services.provider_registry import ProviderRegistry
from novel_world.modules.character.services.card_mapper import get_avatar_relpath
from novel_world.modules.ai.services.user_persona import (
    display_name,
    format_persona_for_prompt,
    merge_session_persona,
    normalize_persona,
    persona_from_world_settings,
    store_persona,
)

def _greeting_options(profile: dict[str, Any]) -> list[str]:
    first = str(profile.get("first_mes", "")).strip()
    alts = profile.get("alternate_greetings") or []
    if not isinstance(alts, list):
        alts = []
    options: list[str] = []
    if first:
        options.append(first)
    for item in alts:
        text = str(item).strip()
        if text:
            options.append(text)
    return options


def _resolve_greeting(profile: dict[str, Any], index: int) -> str:
    options = _greeting_options(profile)
    if not options:
        return ""
    idx = max(0, min(index, len(options) - 1))
    return options[idx]


ROLEPLAY_RULES = (
    "你正在进行角色扮演对话。你必须始终、完全以指定角色的身份用第一人称说话，"
    "保持性格、语气与世界观一致；不要以 AI 助手身份发言，不要跳出角色解释设定。"
    "回复应自然、口语化，像真实对话；可适度使用 *动作* 描写。"
)


class RoleplayService:
    def __init__(
        self,
        chat_repo: SqliteChatRepository,
        provider_registry: ProviderRegistry,
        world_app: AppFactory | None = None,
        base_dir: Path | None = None,
        config: AppConfig | None = None,
        memory_service: MemoryService | None = None,
        prompt_assembler: PromptAssembler | None = None,
        default_session_config: dict[str, Any] | None = None,
    ) -> None:
        self._chat_repo = chat_repo
        self._providers = provider_registry
        self._world_app = world_app or create_app(base_dir)
        self._config = config or default_config(base_dir)
        self._memory = memory_service
        self._assembler = prompt_assembler or PromptAssembler()
        self._default_config = default_session_config or {}

    def list_sessions(self, world_id: str, character_id: str | None = None) -> list[ChatSession]:
        return self._chat_repo.list_roleplay_sessions(
            world_id=world_id, character_id=character_id
        )

    def get_session(self, session_id: SessionId) -> ChatSession:
        session = self._chat_repo.get_session(session_id)
        if session is None or session.session_type != "roleplay":
            raise NotFoundError(f"角色扮演会话不存在: {session_id}")
        return session

    def get_messages(self, session_id: SessionId):
        return self._chat_repo.list_messages(session_id)

    def delete_session(self, session_id: SessionId) -> None:
        self.get_session(session_id)
        self._chat_repo.delete_session(session_id)

    def set_greeting_index(self, session_id: SessionId, index: int) -> ChatSession:
        session = self.get_session(session_id)
        messages = self._chat_repo.list_messages(session_id)
        if any(m.role == "user" for m in messages):
            raise ValidationError("已有用户消息，无法切换开场白。")

        character_id = str((session.config or {}).get("character_id", ""))
        character, world = self._load_character(str(session.world_id), character_id)
        profile = character.profile or {}
        options = _greeting_options(profile)
        if len(options) <= 1:
            raise ValidationError("该角色没有备选开场白。")

        idx = max(0, min(index, len(options) - 1))
        config = dict(session.config or {})
        config["greeting_index"] = idx
        session.config = config
        session.updated_at = utc_now()
        self._chat_repo.update_session(session)

        world_settings = world.settings if isinstance(world.settings, dict) else {}
        persona = merge_session_persona(config, world_settings)
        macro_ctx = build_macro_context(
            char_name=character.name,
            user_name=display_name(persona),
            persona=persona,
            character_profile=profile,
            world_name=world.name,
        )
        greeting = apply_macros(options[idx], macro_ctx)
        assistant_msgs = [m for m in messages if m.role == "assistant"]
        if greeting:
            speaker = self._speaker_payload(character, str(session.world_id))
            if assistant_msgs:
                msg = assistant_msgs[0]
                msg.content = greeting
                self._chat_repo.update_message(msg)
            else:
                self._chat_repo.append_message(
                    new_stored_message(
                        session.id,
                        "assistant",
                        greeting,
                        speaker=speaker,
                    )
                )
        elif assistant_msgs:
            self._chat_repo.delete_message(assistant_msgs[0].id)
        return session

    def update_persona(self, session_id: SessionId, *, name: str, description: str) -> ChatSession:
        session = self.get_session(session_id)
        config = dict(session.config or {})
        config["user_persona"] = store_persona(name, description)
        session.config = config
        session.updated_at = utc_now()
        self._chat_repo.update_session(session)
        return session

    def create_session(
        self,
        provider_id: str,
        model: str,
        *,
        world_id: str,
        character_id: str,
        user_persona: dict[str, str] | None = None,
        title: str = "",
    ) -> ChatSession:
        provider = self._providers.get(provider_id)
        if not model.strip():
            model = str(provider.config.get("model", "")).strip()
        if not model:
            raise ValidationError("必须指定模型名称。")

        character, world = self._load_character(world_id, character_id)
        if user_persona is not None:
            persona = normalize_persona(user_persona)
        else:
            persona = persona_from_world_settings(
                world.settings if isinstance(world.settings, dict) else {}
            )
        now = utc_now()
        session = ChatSession(
            id=new_session_id(),
            world_id=world_id,
            title=title.strip() or f"与{character.name}的对话",
            provider_id=provider_id,
            model=model,
            session_type="roleplay",
            config={
                "character_id": character_id,
                "user_persona": persona,
                "greeting_index": 0,
                "prompt_layers": dict(self._default_config.get("default_prompt_layers") or {}),
                "generation": dict(self._default_config.get("default_generation") or {}),
                "lore_token_budget": int(self._default_config.get("lore_token_budget") or 2000),
            },
            created_at=now,
            updated_at=now,
        )
        self._chat_repo.create_session(session)

        macro_ctx = build_macro_context(
            char_name=character.name,
            user_name=display_name(persona),
            persona=persona,
            character_profile=character.profile or {},
            world_name=world.name,
        )
        profile = character.profile or {}
        greeting_index = int((session.config or {}).get("greeting_index") or 0)
        first_mes = apply_macros(_resolve_greeting(profile, greeting_index), macro_ctx)
        if first_mes:
            self._chat_repo.append_message(
                new_stored_message(
                    session.id,
                    "assistant",
                    first_mes,
                    speaker=self._speaker_payload(character, world_id),
                )
            )
        return session

    def stream_message(self, session_id: SessionId, user_text: str) -> Iterator[StreamChunk]:
        text = user_text.strip()
        handled, rest = parse_command(
            text, {"session_id": session_id, "memory": self._memory}
        )
        if handled:
            yield StreamChunk(kind="done")
            return
        yield from self._stream_impl(session_id, rest if rest else user_text)

    def stream_regenerate(
        self, session_id: SessionId, *, assistant_message_id: str | None = None
    ) -> Iterator[StreamChunk]:
        yield from self._stream_impl(
            session_id,
            "",
            skip_user_message=True,
            reuse_assistant_id=assistant_message_id,
        )

    def preview_prompt(self, session_id: SessionId, user_input: str = "") -> dict[str, Any]:
        session = self.get_session(session_id)
        character_id = str((session.config or {}).get("character_id", ""))
        character, world = self._load_character(str(session.world_id), character_id)
        history = self._chat_repo.list_messages(session_id)
        _, debug = self._build_llm_messages(
            session, character, world, history, user_input=user_input
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

    def _stream_impl(
        self,
        session_id: SessionId,
        user_text: str,
        *,
        skip_user_message: bool = False,
        reuse_assistant_id: str | None = None,
    ) -> Iterator[StreamChunk]:
        if not skip_user_message and not user_text.strip():
            raise ValidationError("消息不能为空。")

        session = self.get_session(session_id)
        character_id = str((session.config or {}).get("character_id", ""))
        character, world = self._load_character(str(session.world_id), character_id)

        if not skip_user_message:
            from novel_world.infrastructure.user_preferences import get_user_prefs
            from novel_world.modules.ai.services.regex_engine import RegexEngine
            from novel_world.modules.ai.services.stscript_integration import apply_stscript

            prefs = get_user_prefs(self._chat_repo.connection)
            outgoing = user_text.strip()
            outgoing, scope_patch = apply_stscript(
                "send", outgoing, user_prefs=prefs, session_config=session.config
            )
            if scope_patch:
                session.config = {**(session.config or {}), **scope_patch}
            regex = RegexEngine.from_prefs_and_session(prefs, session.config)
            outgoing = regex.apply_user_input(outgoing)
            outgoing = run_hooks(
                "message.before_send",
                outgoing,
                session_id=session_id,
                role="user",
            )
            user_msg = new_stored_message(session_id, "user", outgoing)
            self._chat_repo.append_message(user_msg)

        history = self._chat_repo.list_messages(session_id)
        client = self._providers.build_client(session.provider_id)
        llm_messages, _debug = self._build_llm_messages(
            session,
            character,
            world,
            history,
            client=client,
            user_input=user_text if not skip_user_message else "",
            skip_user_in_scan=skip_user_message,
        )
        _, generation, _, _ = self._assembler.merge_session_config(session.config)

        if reuse_assistant_id:
            assistant_msg = self._chat_repo.get_message(reuse_assistant_id)
            if assistant_msg is None:
                raise NotFoundError(f"消息不存在: {reuse_assistant_id}")
            assistant_msg.status = "streaming"
            assistant_msg.content = ""
            assistant_msg.thinking_content = assistant_msg.thinking_content or ""
            self._chat_repo.update_message(assistant_msg)
        else:
            assistant_msg = new_stored_message(
                session_id,
                "assistant",
                "",
                thinking_content="",
                status="streaming",
                speaker=self._speaker_payload(character, str(session.world_id)),
            )
            self._chat_repo.append_message(assistant_msg)

        thinking_parts: list[str] = []
        content_parts: list[str] = []
        last_persist = 0.0

        def _maybe_persist(force: bool = False) -> None:
            nonlocal last_persist
            now = time.monotonic()
            if force or (now - last_persist) >= STREAM_PERSIST_INTERVAL:
                self._chat_repo.update_message(assistant_msg)
                last_persist = now

        try:
            for chunk in client.stream_complete(
                llm_messages, model=session.model, generation=generation
            ):
                if chunk.kind == "thinking" and chunk.text:
                    thinking_parts.append(chunk.text)
                    assistant_msg.thinking_content = "".join(thinking_parts)
                    assistant_msg.content = "".join(content_parts)
                    _maybe_persist()
                    yield chunk
                elif chunk.kind == "content" and chunk.text:
                    content_parts.append(chunk.text)
                    assistant_msg.content = "".join(content_parts)
                    _maybe_persist()
                    yield chunk
                elif chunk.kind == "done":
                    from novel_world.infrastructure.user_preferences import get_user_prefs
                    from novel_world.modules.ai.services.regex_engine import RegexEngine

                    from novel_world.modules.ai.services.stscript_integration import apply_stscript

                    prefs = get_user_prefs(self._chat_repo.connection)
                    assistant_msg.content, scope_patch = apply_stscript(
                        "receive",
                        assistant_msg.content,
                        user_prefs=prefs,
                        session_config=session.config,
                    )
                    if scope_patch:
                        session.config = {**(session.config or {}), **scope_patch}
                    regex = RegexEngine.from_prefs_and_session(prefs, session.config)
                    assistant_msg.content = regex.apply_ai_output(assistant_msg.content)
                    final_content = run_hooks(
                        "message.after_receive",
                        assistant_msg.content,
                        session_id=session_id,
                        role="assistant",
                    )
                    assistant_msg.content = final_content
                    assistant_msg.status = "done"
                    _maybe_persist(force=True)
                    session.updated_at = utc_now()
                    self._chat_repo.update_session(session)
                    display_text = run_hooks(
                        "display.transform",
                        final_content,
                        session_id=session_id,
                    )
                    if display_text != final_content:
                        yield StreamChunk(kind="display", text=display_text)
                    yield chunk
        except Exception:
            assistant_msg.status = "error"
            _maybe_persist(force=True)
            raise

    def _load_character(self, world_id: str, character_id: str):
        rt = self._world_app.open_world(WorldId(world_id))
        try:
            world = rt.world.get(WorldId(world_id))
            character = rt.character.get(CharacterId(character_id))
            return character, world
        finally:
            rt.close()

    def _speaker_payload(self, character, world_id: str) -> dict[str, str]:
        from novel_world.modules.ai.services.tts_voice_resolver import build_speaker_payload

        avatar_url = ""
        rel = get_avatar_relpath(character)
        if rel:
            avatar_url = f"/api/worlds/{world_id}/characters/{character.id}/avatar"
        return build_speaker_payload(character, world_id, avatar_url=avatar_url)

    def _build_llm_messages(
        self,
        session,
        character,
        world,
        history,
        *,
        client=None,
        user_input: str = "",
        skip_user_in_scan: bool = False,
    ) -> tuple[list[ChatMessage], Any]:
        persona = merge_session_persona(
            session.config,
            world.settings if isinstance(world.settings, dict) else None,
        )
        base_parts = self._build_system_parts(session, character, world, persona)
        layers, _generation, lore_budget, profile = self._assembler.merge_session_config(session.config)
        layers = run_hooks(
            "prompt.before_build",
            layers,
            session=session,
            session_id=session.id,
        )

        scan_text = build_scan_text(
            history,
            user_input if not skip_user_in_scan else "",
        )
        lore_entries = load_lore_entries(
            self._world_app,
            str(session.world_id),
            character_id=str(character.id),
            character_metadata=getattr(character, "metadata", None) or {},
            session_config=session.config,
        )
        lore_result, lore_state = scan_lore_for_session(
            lore_entries,
            scan_text,
            session,
            token_budget=lore_budget,
            active_character_id=str(character.id),
            active_character_name=character.name,
            tick_user_turn=not skip_user_in_scan and bool(user_input.strip()),
            messages=history,
            user_input=user_input if not skip_user_in_scan else "",
            vector_conn=self._chat_repo.connection,
        )
        session = persist_lore_state(session, lore_state)
        self._chat_repo.update_session(session)
        lore_parts = LoreEngine.format_result(lore_result)
        from novel_world.infrastructure.user_preferences import get_user_prefs
        from novel_world.modules.ai.services.regex_engine import RegexEngine

        macro_ctx = build_macro_context(
            char_name=character.name,
            user_name=display_name(persona),
            persona=persona,
            character_profile=character.profile or {},
            world_name=world.name,
            lore_text=lore_result.all_text(),
        )
        regex = RegexEngine.from_prefs_and_session(
            get_user_prefs(self._chat_repo.connection), session.config
        )
        lore_parts = {k: regex.apply_prompt(v, macro_ctx=macro_ctx) for k, v in lore_parts.items()}
        memory_block, memory_lines = ("", [])
        if self._memory:
            memory_block, memory_lines = self._memory.select_for_prompt(session.id, scan_text)

        system_prompt = self._assembler.build_system(
            profile=profile,
            base_parts=base_parts,
            layers=layers,
            lore_parts=lore_parts,
            memory_block=memory_block,
            macro_ctx=macro_ctx,
        )

        usable = [
            item
            for item in history
            if item.role in ("user", "assistant")
            and item.status != "streaming"
            and item.content.strip()
        ]

        summary_text, recent = self._roll_up_history(session, usable, client=client)

        messages: list[ChatMessage] = [ChatMessage(role="system", content=system_prompt)]
        if summary_text:
            messages.append(
                ChatMessage(
                    role="system",
                    content="【前情提要（较早对话的摘要）】\n" + summary_text,
                )
            )

        mes_raw = apply_macros(
            str((character.profile or {}).get("mes_example", "")),
            macro_ctx,
        )
        examples = self._parse_mes_example(mes_raw)
        messages.extend(examples)

        for item in recent:
            messages.append(ChatMessage(role=item.role, content=item.content.strip()))

        messages = self._assembler.apply_lore_to_messages(messages, lore_result)
        messages = self._assembler.inject_depth_lore(messages, lore_result)
        messages = self._assembler.inject_authors_note(messages, layers, macro_ctx=macro_ctx)
        debug = self._assembler.build_debug(system_prompt, messages, lore_result, memory_lines, layers)
        messages = run_hooks(
            "prompt.after_build",
            messages,
            session=session,
            session_id=session.id,
            debug=debug,
        )
        return messages, debug

    def _build_system_parts(self, session, character, world, persona: dict[str, str]) -> list[str]:
        profile = character.profile or {}
        card_system = str(profile.get("system_prompt", "")).strip()
        post_history = str(profile.get("post_history_instructions", "")).strip()

        world_lines = [f"世界名称：{world.name}"]
        if world.genre:
            world_lines.append(f"类型：{world.genre}")
        if world.description:
            world_lines.append(f"简介：{world.description}")
        rules_text = _compact_mapping(world.rules)
        if rules_text:
            world_lines.append(f"规则：{rules_text}")
        settings_text = _compact_mapping(world.settings)
        if settings_text:
            world_lines.append(f"设定：{settings_text}")

        scenario = str(profile.get("scenario", "")).strip()
        parts = [
            ROLEPLAY_RULES,
            f"【你扮演的角色】\n{_format_character(character)}",
            "【所属世界（精简）】\n" + "\n".join(world_lines),
        ]
        if scenario:
            parts.append(f"【当前场景】\n{scenario}")
        parts.append(
            f"【对话对象（用户 Persona）】\n{format_persona_for_prompt(persona, mode='roleplay')}"
        )
        if card_system:
            parts.append(f"【角色系统指令】\n{card_system}")
        if post_history:
            parts.append(f"【补充指令】\n{post_history}")
        return parts

    def _build_system_prompt(self, session, character, world, persona: dict[str, str]) -> str:
        return "\n\n".join(self._build_system_parts(session, character, world, persona))

    def _roll_up_history(self, session: ChatSession, usable, *, client=None):
        summary_text = session.summary_content or ""
        already = min(session.summary_until or 0, len(usable))
        recent = usable[already:]

        if client is None or len(recent) <= HISTORY_SUMMARY_TRIGGER:
            return summary_text, recent

        to_fold = recent[:-HISTORY_KEEP_RECENT]
        if not to_fold:
            return summary_text, recent

        try:
            new_summary = self._summarize_messages(
                client, session.model, summary_text, to_fold, session
            )
        except Exception:
            return summary_text, recent[-HISTORY_SUMMARY_TRIGGER:]

        session.summary_content = new_summary
        session.summary_until = already + len(to_fold)
        session.updated_at = utc_now()
        self._chat_repo.update_session(session)
        return new_summary, usable[session.summary_until :]

    def _summarize_messages(self, client, model: str, prior_summary: str, to_fold, session):
        persona = merge_session_persona(session.config)
        transcript_lines: list[str] = []
        for item in to_fold:
            if item.role == "user":
                who = display_name(persona, fallback="用户")
            else:
                who = (item.speaker or {}).get("name") or "角色"
            transcript_lines.append(f"{who}：{item.content.strip()}")
        transcript = "\n".join(transcript_lines)
        prior = f"已有摘要：\n{prior_summary}\n\n" if prior_summary else ""
        prompt = (
            "你是对话摘要助手。请把下面的角色扮演对话压缩成简洁的中文要点，"
            "保留关键剧情、关系变化与未决话题。\n\n"
            f"{prior}对话：\n{transcript}"
        )
        result = client.complete([ChatMessage(role="user", content=prompt)], model=model)
        return (result or "").strip() or prior_summary

    @staticmethod
    def _parse_mes_example(text: str) -> list[ChatMessage]:
        if not text.strip():
            return []
        block = text.replace("<START>", "").strip()
        lines = [ln.strip() for ln in block.splitlines() if ln.strip()]
        messages: list[ChatMessage] = []
        for line in lines:
            user_match = re.match(r"^\{\{user\}\}\s*[:：]\s*(.+)$", line, re.I)
            char_match = re.match(r"^\{\{char\}\}\s*[:：]\s*(.+)$", line, re.I)
            if user_match:
                messages.append(ChatMessage(role="user", content=user_match.group(1).strip()))
            elif char_match:
                messages.append(ChatMessage(role="assistant", content=char_match.group(1).strip()))
        return messages
