from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal

ProviderType = Literal["openai", "anthropic", "gemini", "openai_compatible"]
SessionType = Literal["chat", "world", "group", "roleplay"]
MessageRole = Literal["system", "user", "assistant"]
MessageStatus = Literal["pending", "streaming", "done", "error"]

ProviderId = str
SessionId = str
MessageId = str


def new_provider_id() -> ProviderId:
    return str(uuid.uuid4())


def new_session_id() -> SessionId:
    return str(uuid.uuid4())


def new_message_id() -> MessageId:
    return str(uuid.uuid4())


@dataclass
class ProviderConfig:
    id: ProviderId
    name: str
    type: ProviderType
    config: dict[str, Any] = field(default_factory=dict)
    enabled: bool = True
    created_at: datetime | None = None
    updated_at: datetime | None = None


@dataclass
class ChatMessage:
    role: MessageRole
    content: str


@dataclass
class StoredChatMessage:
    id: MessageId
    session_id: SessionId
    role: MessageRole
    content: str
    thinking_content: str = ""
    status: MessageStatus = "done"
    speaker: dict[str, str] | None = None
    parent_id: str = ""
    variants: list[dict[str, str]] = field(default_factory=list)
    active_variant: int = 0
    created_at: datetime | None = None


@dataclass
class ChatMemory:
    id: str
    session_id: SessionId
    content: str
    keywords: list[str] = field(default_factory=list)
    pinned: bool = False
    source_message_id: str = ""
    created_at: datetime | None = None


def new_memory_id() -> str:
    return str(uuid.uuid4())


@dataclass
class ChatSession:
    id: SessionId
    provider_id: ProviderId
    model: str
    title: str = ""
    world_id: str | None = None
    session_type: SessionType = "chat"
    config: dict[str, Any] = field(default_factory=dict)
    summary_content: str = ""
    summary_until: int = 0
    created_at: datetime | None = None
    updated_at: datetime | None = None


@dataclass
class GroupMember:
    session_id: SessionId
    world_id: str
    character_id: str
    character_name: str
    world_name: str
    sort_order: int = 0
