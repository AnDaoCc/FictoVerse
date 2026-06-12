from __future__ import annotations

from typing import Any

MOD_API_VERSION = 1

PYTHON_HOOKS: list[dict[str, Any]] = [
    {
        "name": "message.before_send",
        "scope": "python",
        "description": "用户消息发送前变换文本。",
        "context": ["session_id", "role"],
    },
    {
        "name": "message.after_receive",
        "scope": "python",
        "description": "助手回复写入前变换文本。",
        "context": ["session_id", "role"],
    },
    {
        "name": "display.transform",
        "scope": "python",
        "description": "展示层文本变换（不改数据库原文）。",
        "context": ["session_id"],
    },
    {
        "name": "prompt.before_build",
        "scope": "python",
        "description": "构建提示词分层前修改 PromptLayers。",
        "context": ["session", "session_id"],
    },
    {
        "name": "prompt.after_build",
        "scope": "python",
        "description": "LLM 消息列表构建完成后修改 messages。",
        "context": ["session", "session_id", "debug"],
    },
]

CLIENT_HOOKS: list[dict[str, Any]] = [
    {
        "name": "chat.message.render",
        "scope": "client",
        "description": "聊天消息 DOM 渲染后回调。",
        "context": ["element", "message", "sessionId"],
    },
    {
        "name": "chat.input.before_send",
        "scope": "client",
        "description": "前端发送前变换输入文本。",
        "context": ["text", "sessionId"],
    },
    {
        "name": "settings.panel",
        "scope": "client",
        "description": "设置页扩展占位（可注入自定义面板）。",
        "context": ["container"],
    },
]

MOD_TYPES = ("python_hooks", "frontend", "composite", "world_content")


def hook_catalog_for_ui() -> list[dict[str, Any]]:
    return list(PYTHON_HOOKS) + list(CLIENT_HOOKS)
