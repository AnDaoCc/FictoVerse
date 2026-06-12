from __future__ import annotations

from collections.abc import Iterator

import httpx

from novel_world.core.exceptions import ValidationError
from novel_world.modules.ai.domain.entities import ChatMessage
from novel_world.modules.ai.domain.generation_config import GenerationConfig
from novel_world.modules.ai.ports.llm_provider import StreamChunk


class GeminiProvider:
    def __init__(
        self,
        *,
        api_key: str,
        base_url: str = "https://generativelanguage.googleapis.com/v1beta",
    ) -> None:
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")

    def complete(
        self,
        messages: list[ChatMessage],
        *,
        model: str,
        generation: GenerationConfig | None = None,
    ) -> str:
        contents = []
        system_text = "\n\n".join(m.content for m in messages if m.role == "system")
        for m in messages:
            if m.role == "system":
                continue
            role = "user" if m.role == "user" else "model"
            contents.append({"role": role, "parts": [{"text": m.content}]})

        payload: dict = {"contents": contents}
        if system_text:
            payload["systemInstruction"] = {"parts": [{"text": system_text}]}
        gen_cfg: dict = {}
        if generation:
            gen_cfg = {
                "temperature": generation.temperature,
                "topP": generation.top_p,
                "maxOutputTokens": generation.max_tokens,
            }
            if generation.stop:
                gen_cfg["stopSequences"] = generation.stop
        if gen_cfg:
            payload["generationConfig"] = gen_cfg

        url = f"{self._base_url}/models/{model}:generateContent?key={self._api_key}"
        with httpx.Client(timeout=120.0) as client:
            resp = client.post(url, json=payload)
            resp.raise_for_status()
            data = resp.json()
            try:
                return data["candidates"][0]["content"]["parts"][0]["text"]
            except (KeyError, IndexError, TypeError) as e:
                raise ValidationError(f"Gemini 响应格式异常: {data}") from e

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
