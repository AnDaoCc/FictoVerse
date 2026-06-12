from __future__ import annotations

import json
from collections.abc import Iterator
from typing import Any

import httpx

from novel_world.core.exceptions import ValidationError
from novel_world.modules.ai.domain.entities import ChatMessage
from novel_world.modules.ai.domain.generation_config import GenerationConfig
from novel_world.modules.ai.ports.llm_provider import StreamChunk


def _apply_generation(payload: dict[str, Any], generation: GenerationConfig | None) -> None:
    if generation is None:
        return
    payload["temperature"] = generation.temperature
    payload["top_p"] = generation.top_p
    payload["max_tokens"] = generation.max_tokens
    if generation.stop:
        payload["stop"] = generation.stop
    if generation.repetition_penalty != 1.0:
        payload["frequency_penalty"] = max(0.0, generation.repetition_penalty - 1.0)


def _extract_text(data: dict) -> str:
    try:
        return data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as e:
        raise ValidationError(f"OpenAI 响应格式异常: {data}") from e


class OpenAIProvider:
    def __init__(self, *, api_key: str, base_url: str = "https://api.openai.com/v1") -> None:
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

    def _payload(
        self,
        messages: list[ChatMessage],
        model: str,
        *,
        stream: bool,
        generation: GenerationConfig | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
        }
        if stream:
            payload["stream"] = True
        _apply_generation(payload, generation)
        return payload

    def complete(
        self,
        messages: list[ChatMessage],
        *,
        model: str,
        generation: GenerationConfig | None = None,
    ) -> str:
        with httpx.Client(timeout=120.0) as client:
            resp = client.post(
                f"{self._base_url}/chat/completions",
                json=self._payload(messages, model, stream=False, generation=generation),
                headers=self._headers(),
            )
            resp.raise_for_status()
            return _extract_text(resp.json())

    def stream_complete(
        self,
        messages: list[ChatMessage],
        *,
        model: str,
        generation: GenerationConfig | None = None,
    ) -> Iterator[StreamChunk]:
        with httpx.Client(timeout=120.0) as client:
            with client.stream(
                "POST",
                f"{self._base_url}/chat/completions",
                json=self._payload(messages, model, stream=True, generation=generation),
                headers=self._headers(),
            ) as resp:
                resp.raise_for_status()
                for line in resp.iter_lines():
                    if not line or not line.startswith("data: "):
                        continue
                    data_str = line[6:].strip()
                    if data_str == "[DONE]":
                        break
                    try:
                        data = json.loads(data_str)
                    except json.JSONDecodeError:
                        continue
                    choices = data.get("choices") or []
                    if not choices:
                        continue
                    delta = choices[0].get("delta") or {}
                    reasoning = delta.get("reasoning_content") or delta.get("reasoning") or ""
                    if reasoning:
                        yield StreamChunk(kind="thinking", text=reasoning)
                    content = delta.get("content") or ""
                    if content:
                        yield StreamChunk(kind="content", text=content)
        yield StreamChunk(kind="done")

    def list_models(self) -> list[str]:
        with httpx.Client(timeout=30.0) as client:
            resp = client.get(f"{self._base_url}/models", headers=self._headers())
            resp.raise_for_status()
            data = resp.json()
        models: list[str] = []
        for item in data.get("data", []):
            if isinstance(item, dict) and item.get("id"):
                models.append(str(item["id"]))
        return sorted(set(models))


class OpenAICompatibleProvider(OpenAIProvider):
    """第三方中转站 / Ollama 等 OpenAI 兼容接口。"""

    def __init__(self, *, api_key: str, base_url: str) -> None:
        if not base_url.strip():
            raise ValidationError("OpenAI 兼容接口必须填写 Base URL。")
        super().__init__(api_key=api_key or "ollama", base_url=base_url)
