from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from novel_world.modules.ai.domain.entities import ChatMessage
from novel_world.modules.ai.domain.generation_config import GenerationConfig
from novel_world.modules.ai.domain.prompt_layers import PromptLayers
from novel_world.modules.ai.domain.prompt_slots import PromptProfile
from novel_world.modules.ai.services.lore_engine import LoreEngine, LoreResult
from novel_world.modules.ai.services.prompt_macros import (
    MacroContext,
    apply_macros,
    apply_macros_to_layers,
)


@dataclass
class PromptDebugPayload:
    system: str
    messages: list[dict[str, str]]
    lore_matched: list[str] = field(default_factory=list)
    memory_injected: list[str] = field(default_factory=list)
    estimated_tokens: int = 0


class PromptAssembler:
    def __init__(self, lore_engine: LoreEngine | None = None) -> None:
        self._lore = lore_engine or LoreEngine()

    def merge_session_config(
        self, session_config: dict[str, Any] | None
    ) -> tuple[PromptLayers, GenerationConfig, int, PromptProfile | None]:
        cfg = session_config or {}
        profile_raw = cfg.get("prompt_profile")
        profile = PromptProfile.from_dict(profile_raw) if profile_raw else None
        if profile and profile.slots:
            layers = profile.to_layers()
            generation = profile.generation
        else:
            layers = PromptLayers.from_dict(cfg.get("prompt_layers"))
            generation = GenerationConfig.from_dict(cfg.get("generation"))
        budget = int(cfg.get("lore_token_budget") or 2000)
        return layers, generation, budget, profile

    def build_system_block(
        self,
        base_parts: list[str],
        layers: PromptLayers,
        lore_parts: dict[str, str],
        memory_block: str = "",
        macro_ctx: MacroContext | None = None,
    ) -> str:
        work_layers = PromptLayers.from_dict(layers.to_dict())
        if macro_ctx is not None:
            apply_macros_to_layers(work_layers, macro_ctx)
            lore_parts = {k: apply_macros(v, macro_ctx) for k, v in lore_parts.items()}
            memory_block = apply_macros(memory_block, macro_ctx)
            base_parts = [apply_macros(p, macro_ctx) for p in base_parts]

        chunks: list[str] = []
        if lore_parts.get("before_main"):
            chunks.append(lore_parts["before_main"])
        if work_layers.main.strip():
            chunks.append(work_layers.main.strip())
        chunks.extend(p for p in base_parts if p.strip())
        if lore_parts.get("after_char"):
            chunks.append(lore_parts["after_char"])
        if work_layers.system_extra.strip():
            chunks.append(work_layers.system_extra.strip())
        if work_layers.jailbreak.strip():
            chunks.append(work_layers.jailbreak.strip())
        if memory_block.strip():
            chunks.append(memory_block.strip())
        if lore_parts.get("post_history"):
            chunks.append(lore_parts["post_history"])
        if work_layers.post_history.strip():
            chunks.append(work_layers.post_history.strip())
        return "\n\n".join(chunks)

    def build_from_profile(
        self,
        profile: PromptProfile,
        base_parts: list[str],
        lore_parts: dict[str, str],
        memory_block: str = "",
        macro_ctx: MacroContext | None = None,
    ) -> str:
        """按 prompt_order 顺序组装 system（profile.order 非空时使用）。"""
        chunks: list[str] = []
        injected_before = False
        injected_after = False
        skip_ident = {"authors_note", "an"}

        for slot in profile.ordered_slots():
            if not slot.enabled or slot.identifier in skip_ident:
                continue
            if slot.identifier in ("impersonate", "continue", "quiet"):
                continue
            ident = slot.identifier
            text = slot.content.strip()
            if macro_ctx is not None:
                text = apply_macros(text, macro_ctx)

            if ident in ("worldinfo", "world_info", "lore", "wi"):
                if lore_parts.get("before_main"):
                    block = lore_parts["before_main"]
                    if macro_ctx is not None:
                        block = apply_macros(block, macro_ctx)
                    chunks.append(block)
                    injected_before = True
                if text:
                    chunks.append(text)
                continue

            if ident == "main":
                if not injected_before and lore_parts.get("before_main"):
                    block = lore_parts["before_main"]
                    if macro_ctx is not None:
                        block = apply_macros(block, macro_ctx)
                    chunks.append(block)
                    injected_before = True
                if text:
                    chunks.append(text)
                for part in base_parts:
                    p = apply_macros(part, macro_ctx) if macro_ctx else part
                    if p.strip():
                        chunks.append(p.strip())
                continue

            if ident in ("char_description", "description", "persona", "scenario", "char"):
                if text:
                    chunks.append(text)
                if ident in ("char_description", "description", "char") and not injected_after:
                    if lore_parts.get("after_char"):
                        block = lore_parts["after_char"]
                        if macro_ctx is not None:
                            block = apply_macros(block, macro_ctx)
                        chunks.append(block)
                        injected_after = True
                continue

            if text:
                chunks.append(text)

        if lore_parts.get("post_history"):
            block = lore_parts["post_history"]
            if macro_ctx is not None:
                block = apply_macros(block, macro_ctx)
            chunks.append(block)
        if memory_block.strip():
            mem = apply_macros(memory_block, macro_ctx) if macro_ctx else memory_block
            chunks.append(mem.strip())
        return "\n\n".join(chunks)

    def build_system(
        self,
        *,
        profile: PromptProfile | None,
        base_parts: list[str],
        layers: PromptLayers,
        lore_parts: dict[str, str],
        memory_block: str = "",
        macro_ctx: MacroContext | None = None,
    ) -> str:
        if profile and profile.order:
            return self.build_from_profile(
                profile, base_parts, lore_parts, memory_block, macro_ctx=macro_ctx
            )
        return self.build_system_block(
            base_parts, layers, lore_parts, memory_block, macro_ctx=macro_ctx
        )

    def inject_authors_note(
        self,
        messages: list[ChatMessage],
        layers: PromptLayers,
        macro_ctx: MacroContext | None = None,
    ) -> list[ChatMessage]:
        note = layers.authors_note.content.strip()
        if macro_ctx is not None:
            note = apply_macros(note, macro_ctx)
        if not note:
            return messages
        depth = max(0, layers.authors_note.depth)
        out = list(messages)
        insert_at = max(1, len(out) - depth)
        out.insert(insert_at, ChatMessage(role="system", content=f"【Author's Note】\n{note}"))
        return out

    def apply_lore_to_messages(
        self,
        messages: list[ChatMessage],
        lore_result: LoreResult,
    ) -> list[ChatMessage]:
        if not lore_result.before_examples:
            return messages
        block = "\n\n".join(lore_result.before_examples)
        out = list(messages)
        # 插在 system 之后
        insert_at = 1 if out and out[0].role == "system" else 0
        out.insert(insert_at, ChatMessage(role="system", content=f"【示例参考 Lore】\n{block}"))
        return out

    def inject_depth_lore(
        self, messages: list[ChatMessage], lore_result: LoreResult
    ) -> list[ChatMessage]:
        out = list(messages)
        for seg in lore_result.at_depth:
            insert_at = max(1, len(out) - seg.depth)
            out.insert(insert_at, ChatMessage(role="system", content=seg.content))
        return out

    def estimate_tokens(self, text: str) -> int:
        return max(1, len(text) // 2)

    def serialize_messages(
        self, messages: list[ChatMessage], template: str
    ) -> list[dict[str, str]]:
        if template == "chatml":
            parts: list[str] = []
            for m in messages:
                parts.append(f"<|im_start|>{m.role}\n{m.content}")
            parts.append("<|im_start|>assistant\n")
            return [{"role": "prompt", "content": "\n".join(parts)}]
        if template == "alpaca":
            system = "\n\n".join(m.content for m in messages if m.role == "system")
            blocks: list[str] = []
            if system.strip():
                blocks.append(f"### System:\n{system.strip()}")
            for m in messages:
                if m.role == "user":
                    blocks.append(f"### User:\n{m.content}")
                elif m.role == "assistant":
                    blocks.append(f"### Response:\n{m.content}")
            blocks.append("### Response:\n")
            return [{"role": "prompt", "content": "\n\n".join(blocks)}]
        return [{"role": m.role, "content": m.content} for m in messages]

    def build_debug(
        self,
        system: str,
        messages: list[ChatMessage],
        lore_result: LoreResult,
        memory_lines: list[str],
        layers: PromptLayers | None = None,
    ) -> PromptDebugPayload:
        template = layers.template if layers else "chat"
        msg_dicts = self.serialize_messages(messages, template)
        total = self.estimate_tokens(system) + sum(
            self.estimate_tokens(m["content"]) for m in msg_dicts
        )
        return PromptDebugPayload(
            system=system,
            messages=msg_dicts,
            lore_matched=lore_result.matched_ids,
            memory_injected=memory_lines,
            estimated_tokens=total,
        )
