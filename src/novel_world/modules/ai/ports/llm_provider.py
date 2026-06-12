from __future__ import annotations

from dataclasses import dataclass
from typing import Iterator, Literal, Protocol

from novel_world.modules.ai.domain.entities import ChatMessage
from novel_world.modules.ai.domain.generation_config import GenerationConfig

StreamKind = Literal["thinking", "content", "display", "done", "speaker"]


@dataclass(frozen=True)
class StreamChunk:
    kind: StreamKind
    text: str = ""


class LLMProvider(Protocol):
    def complete(
        self,
        messages: list[ChatMessage],
        *,
        model: str,
        generation: GenerationConfig | None = None,
    ) -> str: ...

    def stream_complete(
        self,
        messages: list[ChatMessage],
        *,
        model: str,
        generation: GenerationConfig | None = None,
    ) -> Iterator[StreamChunk]: ...


class ProviderRepository(Protocol):
    def list_all(self): ...

    def list_enabled(self): ...

    def get(self, provider_id): ...

    def save(self, provider) -> None: ...

    def delete(self, provider_id) -> None: ...
