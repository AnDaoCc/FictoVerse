"""SillyTavern Extension API 兼容层（映射到本软件 HookBus / 仓储）。"""
from __future__ import annotations

from typing import Any, Callable

from novel_world.modules.ai.services.command_parser import register_command
from novel_world.modules.extensions import hook_bus

_ST_HOOK_MAP = {
    "chat_completion_bypass": "prompt.before_build",
    "generation_after_commands": "prompt.after_build",
    "message_sent": "message.before_send",
    "message_received": "message.after_receive",
    "render_chat_message": "display.transform",
}


class STExtensionHost:
    def __init__(self, *, chat_repo: Any = None) -> None:
        self._chat_repo = chat_repo
        self._slash_handlers: dict[str, Callable] = {}

    def get_chat_messages(self, session_id: str, limit: int = 100) -> list[dict[str, str]]:
        if self._chat_repo is None:
            return []
        messages = self._chat_repo.list_messages(session_id)
        out = []
        for m in messages[-limit:]:
            out.append({"role": m.role, "content": m.content, "id": m.id})
        return out

    def register_slash_command(self, name: str, handler: Callable[[str, dict], tuple[bool, str]]) -> None:
        self._slash_handlers[name.lower()] = handler
        register_command(name, handler)

    def register_st_hook(self, st_event: str, fn: Callable[..., Any], *, priority: int = 100) -> None:
        local_name = _ST_HOOK_MAP.get(st_event, st_event)
        hook_bus.register_hook(local_name, fn, priority=priority)

    def set_extension_prompt(self, session_config: dict[str, Any], prompt_type: str, content: str) -> dict[str, Any]:
        cfg = dict(session_config or {})
        ext = dict(cfg.get("extension_prompts") or {})
        ext[prompt_type] = content
        cfg["extension_prompts"] = ext
        return cfg

    @staticmethod
    def compatibility_matrix() -> dict[str, str]:
        return {
            "getChatMessages": "supported",
            "registerSlashCommand": "supported",
            "setExtensionPrompt": "supported",
            "eventSource.on (subset)": "partial",
            "generateQuietPrompt": "partial",
            "importEmbeddedWorldInfo": "partial",
            "native JS extensions": "partial via adapter",
            "remote extension install": "unsupported",
        }
