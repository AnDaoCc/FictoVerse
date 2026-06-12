from __future__ import annotations

import json
import time
from collections.abc import Iterator
from dataclasses import dataclass
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
from novel_world.modules.ai.domain.entities import ChatMessage, ChatSession, SessionId, StoredChatMessage, new_session_id
from novel_world.modules.ai.domain.generation_config import GenerationConfig
from novel_world.modules.ai.services.command_parser import parse_command
from novel_world.modules.ai.services.lore_engine import LoreEngine, LoreResult
from novel_world.modules.ai.services.memory_service import MemoryService
from novel_world.modules.ai.services.prompt_assembler import PromptAssembler
from novel_world.modules.ai.services.prompt_context import (
    build_scan_text,
    load_lore_entries,
    persist_lore_state,
    scan_lore_for_session,
)
from novel_world.modules.extensions.hook_bus import run_hooks
from novel_world.modules.ai.ports.llm_provider import StreamChunk
from novel_world.modules.ai.services.provider_registry import ProviderRegistry
from novel_world.modules.ai.services.user_persona import (
    display_name,
    format_persona_for_prompt,
    merge_session_persona,
    normalize_persona,
    persona_from_world_settings,
    store_persona,
)
from novel_world.modules.ai.services.world_speaker import parse_world_reply
from novel_world.modules.documents.services.document_service import ChatAttachment, DocumentService


DEFAULT_SYSTEM_PROMPT = "你是一个有帮助的 AI 助手。请用中文简洁、清晰地回答用户问题。"

WORLD_REPLY_RULES = (
    "\n\n【输出格式】请只输出一行 JSON，不要 Markdown 代码块或其它解释："
    '{"speaker_id":"<角色 character_id，旁白用 narrator>","content":"<台词或叙述>"}。'
    "speaker_id 必须来自上方【角色】列表标注的 id；临时路人若无对应角色可用 narrator，"
    "并在 content 中以该角色口吻叙述。"
)

CONTINUE_WRITING_INSTRUCTION = (
    "请基于前文、当前世界观、角色设定及角色之间的关系，继续把小说情节往下写一段："
    "自然推进剧情，保持与世界观设定、人物性格和人物关系一致；"
    "在合理处发展或揭示角色之间的关系；只输出小说正文，不要额外解释。"
)

# system prompt 体积上限，用于控制 token 消耗
MAX_PROMPT_CHARACTERS = 12
MAX_PROMPT_STATES = 20
MAX_PROMPT_EVENTS = 8
MAX_PROMPT_DOCS = 3
MAX_PROMPT_DOC_CHARS = 2500

# 对话历史滚动摘要阈值
HISTORY_KEEP_RECENT = 8
HISTORY_SUMMARY_TRIGGER = 16

# 流式持久化节流间隔（秒）：避免每个 token 都写一次 SQLite
STREAM_PERSIST_INTERVAL = 0.2

# 世界数据缓存 TTL（秒）：避免连续消息时反复打开 WorldRuntime
WORLD_CACHE_TTL = 60.0


@dataclass
class _WorldCacheEntry:
    """缓存的系统提示词片段，避免重复打开世界数据库。"""
    prompt: str
    cached_at: float


def _compact_mapping(data: Any) -> str:
    """把规则/设定字典渲染成紧凑的「键：值；键：值」文本，空则返回空串。"""
    if not data:
        return ""
    if not isinstance(data, dict):
        return json.dumps(data, ensure_ascii=False)
    segs: list[str] = []
    for key, value in data.items():
        if isinstance(value, (dict, list)):
            value_text = json.dumps(value, ensure_ascii=False)
        else:
            value_text = str(value)
        segs.append(f"{key}：{value_text}")
    return "；".join(segs)


def _format_character(c) -> str:
    lines = [f"- {c.name}（{c.role}）[id={c.id}]"]
    profile = c.profile or {}
    for key, label in (
        ("summary", "简介"),
        ("personality", "性格"),
        ("appearance", "外貌"),
        ("background", "背景"),
    ):
        val = profile.get(key)
        if val:
            lines.append(f"  · {label}：{val}")
    if c.attributes:
        lines.append(f"  · 属性：{json.dumps(c.attributes, ensure_ascii=False)}")
    rel_text = _format_relationships(c)
    if rel_text:
        lines.append(f"  · 关系：{rel_text}")
    return "\n".join(lines)


def _format_relationships(c) -> str:
    metadata = getattr(c, "metadata", None) or {}
    relationships = metadata.get("relationships") or []
    parts: list[str] = []
    for rel in relationships:
        if not isinstance(rel, dict):
            continue
        target = str(rel.get("target", "")).strip()
        if not target:
            continue
        rel_type = str(rel.get("type", "")).strip()
        note = str(rel.get("note", "")).strip()
        seg = target
        if rel_type:
            seg += f"（{rel_type}）"
        if note:
            seg += f"：{note}"
        parts.append(seg)
    return "；".join(parts)


class ChatService:
    def __init__(
        self,
        chat_repo: SqliteChatRepository,
        provider_registry: ProviderRegistry,
        world_app: AppFactory | None = None,
        base_dir: Path | None = None,
        documents: DocumentService | None = None,
        memory_service: MemoryService | None = None,
        prompt_assembler: PromptAssembler | None = None,
        default_session_config: dict[str, Any] | None = None,
    ) -> None:
        self._chat_repo = chat_repo
        self._providers = provider_registry
        self._world_app = world_app or create_app(base_dir)
        self._documents = documents
        self._memory = memory_service
        self._assembler = prompt_assembler or PromptAssembler()
        self._default_config = default_session_config or {}
        # 世界系统提示词缓存：world_id -> (prompt, cached_at)
        self._world_cache: dict[str, _WorldCacheEntry] = {}

    def list_sessions(self, *, world_id: str | None = None) -> list[ChatSession]:
        return self._chat_repo.list_sessions(world_id=world_id)

    def get_session(self, session_id: SessionId) -> ChatSession:
        session = self._chat_repo.get_session(session_id)
        if session is None:
            raise NotFoundError(f"会话不存在: {session_id}")
        return session

    def get_messages(self, session_id: SessionId):
        return self._chat_repo.list_messages(session_id)

    def delete_session(self, session_id: SessionId) -> None:
        self.get_session(session_id)
        self._chat_repo.delete_session(session_id)

    def delete_sessions_by_world(self, world_id: str) -> None:
        self._chat_repo.delete_sessions_by_world(world_id)

    def delete_sessions_by_provider(self, provider_id: str) -> int:
        return self._chat_repo.delete_sessions_by_provider(provider_id)

    def clear_world_cache(self, world_id: str) -> None:
        """世界数据变更后清除缓存，确保下次 prompt 重新读取。"""
        self._world_cache.pop(world_id, None)

    def create_session(
        self,
        provider_id: str,
        model: str,
        *,
        world_id: str | None = None,
        title: str = "",
    ) -> ChatSession:
        provider = self._providers.get(provider_id)
        if not model.strip():
            model = str(provider.config.get("model", "")).strip()
        if not model:
            raise ValidationError("必须指定模型名称。")
        session_config: dict[str, Any] = {
            "prompt_layers": dict(self._default_config.get("default_prompt_layers") or {}),
            "generation": dict(self._default_config.get("default_generation") or {}),
            "lore_token_budget": int(self._default_config.get("lore_token_budget") or 2000),
        }
        if world_id:
            rt = self._world_app.open_world(WorldId(world_id))
            try:
                world = rt.world.get(WorldId(world_id))
                session_config["user_persona"] = persona_from_world_settings(
                    world.settings if isinstance(world.settings, dict) else {}
                )
            finally:
                rt.close()
        now = utc_now()
        session = ChatSession(
            id=new_session_id(),
            world_id=world_id,
            title=title or ("新对话" if not world_id else "世界对话"),
            provider_id=provider_id,
            model=model,
            config=session_config,
            created_at=now,
            updated_at=now,
        )
        self._chat_repo.create_session(session)
        return session

    def update_persona(self, session_id: SessionId, *, name: str, description: str) -> ChatSession:
        session = self.get_session(session_id)
        config = dict(session.config or {})
        config["user_persona"] = store_persona(name, description)
        session.config = config
        session.updated_at = utc_now()
        self._chat_repo.update_session(session)
        return session

    def send_message(
        self,
        session_id: SessionId,
        user_text: str,
        *,
        message_attachment_ids: list[str] | None = None,
    ) -> StoredChatMessage:
        for _ in self._stream_impl(
            session_id, user_text, message_attachment_ids=message_attachment_ids
        ):
            pass
        messages = self._chat_repo.list_messages(session_id)
        return messages[-1]

    def stream_message(
        self,
        session_id: SessionId,
        user_text: str,
        *,
        message_attachment_ids: list[str] | None = None,
        mode: str = "chat",
    ) -> Iterator[StreamChunk]:
        text = user_text.strip()
        handled, rest = parse_command(
            text, {"session_id": session_id, "memory": self._memory}
        )
        if handled:
            yield StreamChunk(kind="done")
            return
        yield from self._stream_impl(
            session_id, rest if rest else user_text, message_attachment_ids=message_attachment_ids, mode=mode
        )

    def stream_regenerate(
        self, session_id: SessionId, *, assistant_message_id: str | None = None
    ) -> Iterator[StreamChunk]:
        yield from self._stream_impl(
            session_id,
            "",
            mode="chat",
            skip_user_message=True,
            reuse_assistant_id=assistant_message_id,
        )

    def preview_prompt(self, session_id: SessionId, user_input: str = "") -> dict[str, Any]:
        session = self.get_session(session_id)
        history = self._chat_repo.list_messages(session_id)
        _, debug = self._build_llm_messages(session, history, user_input=user_input)
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
            "user_persona",
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
        message_attachment_ids: list[str] | None = None,
        mode: str = "chat",
        skip_user_message: bool = False,
        reuse_assistant_id: str | None = None,
    ) -> Iterator[StreamChunk]:
        is_continue = mode == "continue"
        if not skip_user_message and not user_text.strip() and not message_attachment_ids and not is_continue:
            raise ValidationError("消息不能为空。")

        session = self.get_session(session_id)
        if skip_user_message:
            enriched = ""
        elif is_continue and not user_text.strip():
            _, _gen, _, profile = self._assembler.merge_session_config(session.config)
            continue_text = profile.slot_content("continue") if profile else ""
            enriched = continue_text or CONTINUE_WRITING_INSTRUCTION
        else:
            enriched = self._enrich_user_text(
                session_id, user_text.strip(), message_attachment_ids or []
            )
            from novel_world.infrastructure.user_preferences import get_user_prefs
            from novel_world.modules.ai.services.regex_engine import RegexEngine
            from novel_world.modules.ai.services.stscript_integration import apply_stscript

            prefs = get_user_prefs(self._chat_repo.connection)
            enriched, scope_patch = apply_stscript(
                "send", enriched, user_prefs=prefs, session_config=session.config
            )
            if scope_patch:
                session.config = {**(session.config or {}), **scope_patch}
            regex = RegexEngine.from_prefs_and_session(prefs, session.config)
            enriched = regex.apply_user_input(enriched)
            enriched = run_hooks(
                "message.before_send",
                enriched,
                session_id=session_id,
                role="user",
            )
            if is_continue:
                enriched = f"{enriched}\n\n{CONTINUE_WRITING_INSTRUCTION}".strip()
        if not skip_user_message:
            user_msg = new_stored_message(session_id, "user", enriched)
            self._chat_repo.append_message(user_msg)

            if message_attachment_ids and self._documents:
                self._documents.bind_attachments_to_message(message_attachment_ids, user_msg.id)

        history = self._chat_repo.list_messages(session_id)
        is_world_session = bool(session.world_id)
        client = self._providers.build_client(session.provider_id)
        llm_messages, _debug = self._build_llm_messages(
            session,
            history,
            client=client,
            user_input=enriched if not skip_user_message else "",
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
                session_id, "assistant", "", thinking_content="", status="streaming"
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
                    if not is_world_session:
                        yield chunk
                elif chunk.kind == "done":
                    from novel_world.infrastructure.user_preferences import get_user_prefs
                    from novel_world.modules.ai.services.regex_engine import RegexEngine

                    raw_content = assistant_msg.content
                    speaker_payload: dict[str, str] | None = None
                    if is_world_session and session.world_id:
                        speaker_payload, parsed = parse_world_reply(
                            self._world_app, str(session.world_id), raw_content
                        )
                        raw_content = parsed
                        assistant_msg.speaker = speaker_payload
                    from novel_world.modules.ai.services.stscript_integration import apply_stscript

                    prefs = get_user_prefs(self._chat_repo.connection)
                    raw_content, scope_patch = apply_stscript(
                        "receive",
                        raw_content,
                        user_prefs=prefs,
                        session_config=session.config,
                    )
                    if scope_patch:
                        session.config = {**(session.config or {}), **scope_patch}
                    regex = RegexEngine.from_prefs_and_session(prefs, session.config)
                    raw_content = regex.apply_ai_output(raw_content)
                    final_content = run_hooks(
                        "message.after_receive",
                        raw_content,
                        session_id=session_id,
                        role="assistant",
                    )
                    assistant_msg.content = final_content
                    assistant_msg.status = "done"
                    _maybe_persist(force=True)
                    self._maybe_update_title(session, user_text)
                    if is_world_session:
                        yield StreamChunk(kind="content", text=final_content)
                        if speaker_payload:
                            yield StreamChunk(
                                kind="speaker",
                                text=json.dumps(speaker_payload, ensure_ascii=False),
                            )
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

    def _collect_stream(
        self,
        session_id: SessionId,
        user_text: str,
        *,
        message_attachment_ids: list[str] | None = None,
    ) -> tuple[str, str]:
        thinking_parts: list[str] = []
        content_parts: list[str] = []
        for chunk in self._stream_impl(
            session_id, user_text, message_attachment_ids=message_attachment_ids
        ):
            if chunk.kind == "thinking":
                thinking_parts.append(chunk.text)
            elif chunk.kind == "content":
                content_parts.append(chunk.text)
        return "".join(thinking_parts), "".join(content_parts)

    def _enrich_user_text(
        self, session_id: str, user_text: str, message_attachment_ids: list[str]
    ) -> str:
        if not self._documents:
            return user_text
        parts = [user_text] if user_text else []
        session_atts = self._documents.list_session_attachments(session_id)
        session_docs = [a for a in session_atts if a.message_id is None]
        if session_docs:
            parts.append("\n\n【会话背景附件】")
            for att in session_docs:
                parts.append(self._attachment_block(att))
        if message_attachment_ids:
            parts.append("\n\n【本条消息附件】")
            for att_id in message_attachment_ids:
                att = next((a for a in self._documents.list_all_session_attachments(session_id) if a.id == att_id), None)
                if att:
                    parts.append(self._attachment_block(att))
        return "\n".join(p for p in parts if p).strip() or "（用户发送了附件）"

    def _attachment_block(self, att: ChatAttachment) -> str:
        if att.extracted_text:
            return f"文件《{att.filename}》：\n{att.extracted_text[:8000]}"
        lower = att.filename.lower()
        if lower.endswith((".png", ".jpg", ".jpeg", ".gif", ".webp")):
            return f"图片附件《{att.filename}》（已上传，当前模型若为纯文本模式则无法识别图像内容）"
        return f"附件《{att.filename}》"

    def _maybe_update_title(self, session: ChatSession, user_text: str) -> None:
        if session.title in ("新对话", "世界对话") and user_text.strip():
            session.title = user_text.strip()[:24]
            session.updated_at = utc_now()
            self._chat_repo.update_session(session)

    def _build_llm_messages(
        self,
        session: ChatSession,
        history,
        *,
        client=None,
        user_input: str = "",
        skip_user_in_scan: bool = False,
    ) -> tuple[list[ChatMessage], Any]:
        base_prompt = self._build_system_prompt(session.world_id, session.id)
        base_parts = [base_prompt] if base_prompt.strip() else []
        world_settings = None
        if session.world_id:
            rt = self._world_app.open_world(WorldId(session.world_id))
            try:
                world = rt.world.get(WorldId(session.world_id))
                world_settings = world.settings if isinstance(world.settings, dict) else {}
            finally:
                rt.close()
        persona = merge_session_persona(session.config, world_settings)
        persona_line = format_persona_for_prompt(persona, mode="world")
        if persona_line:
            base_parts.append(f"【用户身份】\n{persona_line}")
        from novel_world.modules.ai.services.prompt_macros import build_macro_context

        macro_ctx = build_macro_context(
            user_name=display_name(persona),
            persona=persona,
            world_name="",
        )
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
        lore_result = LoreResult()
        lore_parts: dict[str, str] = {}
        if session.world_id:
            rt = self._world_app.open_world(WorldId(session.world_id))
            try:
                world = rt.world.get(WorldId(session.world_id))
                macro_ctx.world_name = world.name
                characters = rt.character.list_by_world(WorldId(session.world_id), active_only=True)
                extra = [(str(c.id), getattr(c, "metadata", None) or {}) for c in characters]
            finally:
                rt.close()
            lore_entries = load_lore_entries(
                self._world_app,
                session.world_id,
                extra_characters=extra,
                session_config=session.config,
            )
            lore_result, lore_state = scan_lore_for_session(
                lore_entries,
                scan_text,
                session,
                token_budget=lore_budget,
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
                ChatMessage(role="system", content="【前情提要（较早对话的摘要）】\n" + summary_text)
            )
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

    def _roll_up_history(self, session: ChatSession, usable, *, client=None):
        """返回 (摘要文本, 需原文发送的近期消息)。超过阈值时把较早消息压成摘要并存回会话。"""
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
            # 摘要失败：安全回退，仅保留最近若干条原文，不更新会话摘要
            return summary_text, recent[-HISTORY_SUMMARY_TRIGGER:]

        session.summary_content = new_summary
        session.summary_until = already + len(to_fold)
        session.updated_at = utc_now()
        self._chat_repo.update_session(session)
        return new_summary, usable[session.summary_until:]

    def _summarize_messages(
        self, client, model: str, prior_summary: str, to_fold, session: ChatSession | None = None
    ) -> str:
        persona = merge_session_persona(session.config if session else None)
        transcript_lines: list[str] = []
        for item in to_fold:
            if item.role == "user":
                who = display_name(persona, fallback="用户")
            else:
                who = "助手"
            transcript_lines.append(f"{who}：{item.content.strip()}")
        transcript = "\n".join(transcript_lines)
        prior = f"已有摘要：\n{prior_summary}\n\n" if prior_summary else ""
        prompt = (
            "你是对话摘要助手。请把下面的小说创作对话压缩成简洁的中文要点摘要，"
            "保留关键剧情进展、人物关系变化、重要设定与未决伏笔，省略寒暄与重复内容。"
            "输出连续的要点段落，不要分点编号，不要额外解释。\n\n"
            f"{prior}需要纳入摘要的对话：\n{transcript}"
        )
        result = client.complete(
            [ChatMessage(role="user", content=prompt)], model=model
        )
        return (result or "").strip() or prior_summary

    def _build_system_prompt(self, world_id: str | None, session_id: str | None = None) -> str:
        extra = ""
        if session_id and self._documents:
            session_atts = self._documents.list_session_attachments(session_id)
            bg = [a for a in session_atts if a.message_id is None and a.extracted_text]
            if bg:
                blocks = [self._attachment_block(a) for a in bg]
                extra = "\n\n【会话背景资料】\n" + "\n\n".join(blocks)

        if not world_id:
            return DEFAULT_SYSTEM_PROMPT + extra

        # 检查缓存
        cached = self._world_cache.get(world_id)
        if cached is not None and (time.monotonic() - cached.cached_at) < WORLD_CACHE_TTL:
            return cached.prompt + extra

        rt = self._world_app.open_world(WorldId(world_id))
        try:
            world = rt.world.get(WorldId(world_id))
            characters = rt.character.list_by_world(world.id, active_only=True)
            states = rt.state.list_by_world(world.id)
            events = rt.event.list_by_world(world.id)
        finally:
            rt.close()

        # 仅保留生效角色，且数量上限收紧，控制 token
        char_lines = [_format_character(c) for c in characters[:MAX_PROMPT_CHARACTERS]]
        state_lines = [
            f"- {s.key} = {json.dumps(s.value, ensure_ascii=False)}"
            for s in states[:MAX_PROMPT_STATES]
        ]
        event_lines = [
            f"- [{e.seq}] {e.event_type}: {json.dumps(e.payload, ensure_ascii=False)}"
            for e in events[-MAX_PROMPT_EVENTS:]
        ]

        doc_section = ""
        if self._documents:
            docs = self._documents.list_world_documents(world_id)
            if docs:
                doc_blocks = [
                    f"《{d.filename}》\n{d.extracted_text[:MAX_PROMPT_DOC_CHARS]}"
                    for d in docs[:MAX_PROMPT_DOCS]
                    if d.extracted_text
                ]
                if doc_blocks:
                    doc_section = "\n\n【参考文档摘录（只读，上传快照）】\n" + "\n\n".join(doc_blocks)

        # 仅输出非空字段，避免占位与冗余 JSON
        world_lines = ["【当前世界观（可编辑，以这里为准）】", f"世界名称：{world.name}"]
        if world.genre:
            world_lines.append(f"类型：{world.genre}")
        if world.description:
            world_lines.append(f"世界简介：{world.description}")
        rules_text = _compact_mapping(world.rules)
        if rules_text:
            world_lines.append(f"规则：{rules_text}")
        settings_text = _compact_mapping(world.settings)
        if settings_text:
            world_lines.append(f"设定：{settings_text}")

        parts = [
            "你是 FictoVerse（虚构宇宙）中的叙事助手。请基于以下世界观信息进行对话，不要编造与设定冲突的内容。",
            "\n".join(world_lines),
        ]
        if char_lines:
            parts.append("【角色】\n" + "\n".join(char_lines))
        if state_lines:
            parts.append("【当前状态】\n" + "\n".join(state_lines))
        if event_lines:
            parts.append("【近期事件】\n" + "\n".join(event_lines))
        if doc_section:
            parts.append(doc_section.strip())
        if extra:
            parts.append(extra.strip())

        prompt = "\n\n".join(parts) + WORLD_REPLY_RULES

        # 写入缓存
        self._world_cache[world_id] = _WorldCacheEntry(prompt=prompt, cached_at=time.monotonic())
        return prompt