from __future__ import annotations

from collections.abc import Iterator

import httpx

from novel_world.core.exceptions import ValidationError
from novel_world.modules.ai.domain.entities import ChatMessage
from novel_world.modules.ai.domain.generation_config import GenerationConfig
from novel_world.modules.ai.ports.llm_provider import StreamChunk


class AnthropicProvider:
    def __init__(self, *, api_key: str, base_url: str = "https://api.anthropic.com") -> None:
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")

    def complete(
        self,
        messages: list[ChatMessage],
        *,
        model: str,
        generation: GenerationConfig | None = None,
    ) -> str:
        system_parts = [m.content for m in messages if m.role == "system"]
        convo = [{"role": m.role, "content": m.content} for m in messages if m.role != "system"]
        payload: dict = {
            "model": model,
            "max_tokens": generation.max_tokens if generation else 4096,
            "messages": convo,
        }
        if generation:
            payload["temperature"] = generation.temperature
            payload["top_p"] = generation.top_p
            if generation.stop:
                payload["stop_sequences"] = generation.stop
        if system_parts:
            payload["system"] = "\n\n".join(system_parts)

        headers = {
            "x-api-key": self._api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        }
        with httpx.Client(timeout=120.0) as client:
            resp = client.post(f"{self._base_url}/v1/messages", json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()
            try:
                parts = data.get("content", [])
                return "".join(part.get("text", "") for part in parts if part.get("type") == "text")
            except (TypeError, AttributeError) as e:
                raise ValidationError(f"Anthropic 响应格式异常: {data}") from e

    def list_models(self) -> list[str]:
        headers = {
            "x-api-key": self._api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        }
        with httpx.Client(timeout=30.0) as client:
            resp = client.get(f"{self._base_url}/v1/models", headers=headers)
            resp.raise_for_status()
            data = resp.json()
        models: list[str] = []
        for item in data.get("data", []):
            if isinstance(item, dict) and item.get("id"):
                models.append(str(item["id"]))
        return sorted(set(models))

    def stream_complete(
        self,
        messages: list[ChatMessage],
        *,
        model: str,
        generation: GenerationConfig | None = None,
    ) -> Iterator[StreamChunk]:
        text = self.complete(messages, model=model, generation=generation)
        if text:
            yield StreamChunk(kind="content", text=text)
        yield StreamChunk(kind="done")
