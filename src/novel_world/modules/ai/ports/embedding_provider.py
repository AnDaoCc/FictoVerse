from __future__ import annotations

import json
from typing import Any, Protocol

import httpx


class EmbeddingProvider(Protocol):
    def embed(self, texts: list[str]) -> list[list[float]]: ...

    @property
    def dimension(self) -> int: ...


class OpenAIEmbeddingProvider:
    def __init__(self, *, api_key: str, base_url: str = "https://api.openai.com/v1", model: str = "text-embedding-3-small") -> None:
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._dimension = 1536

    @property
    def dimension(self) -> int:
        return self._dimension

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        with httpx.Client(timeout=60.0) as client:
            resp = client.post(
                f"{self._base_url}/embeddings",
                headers={"Authorization": f"Bearer {self._api_key}"},
                json={"model": self._model, "input": texts},
            )
            resp.raise_for_status()
            data = resp.json()
        items = sorted(data.get("data") or [], key=lambda x: x.get("index", 0))
        return [list(item.get("embedding") or []) for item in items]


class OllamaEmbeddingProvider:
    def __init__(self, *, base_url: str = "http://127.0.0.1:11434", model: str = "nomic-embed-text") -> None:
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._dimension = 768

    @property
    def dimension(self) -> int:
        return self._dimension

    def embed(self, texts: list[str]) -> list[list[float]]:
        out: list[list[float]] = []
        with httpx.Client(timeout=120.0) as client:
            for text in texts:
                resp = client.post(
                    f"{self._base_url}/api/embeddings",
                    json={"model": self._model, "prompt": text},
                )
                resp.raise_for_status()
                payload = resp.json()
                vec = list(payload.get("embedding") or [])
                if vec and len(vec) != self._dimension:
                    self._dimension = len(vec)
                out.append(vec)
        return out


class HashEmbeddingProvider:
    """无外部依赖的确定性伪向量（测试/离线 fallback）。"""

    def __init__(self, dimension: int = 128) -> None:
        self._dimension = dimension

    @property
    def dimension(self) -> int:
        return self._dimension

    def embed(self, texts: list[str]) -> list[list[float]]:
        import hashlib
        import math

        out: list[list[float]] = []
        for text in texts:
            digest = hashlib.sha256(text.encode("utf-8")).digest()
            vec = []
            for i in range(self._dimension):
                b = digest[i % len(digest)]
                vec.append((b / 127.5) - 1.0)
            norm = math.sqrt(sum(x * x for x in vec)) or 1.0
            out.append([x / norm for x in vec])
        return out


def build_embedding_provider(prefs: dict[str, Any] | None) -> EmbeddingProvider:
    cfg = prefs or {}
    provider = str(cfg.get("embedding_provider") or "hash").lower()
    if provider == "openai":
        return OpenAIEmbeddingProvider(
            api_key=str(cfg.get("embedding_api_key") or cfg.get("openai_api_key") or ""),
            base_url=str(cfg.get("embedding_base_url") or "https://api.openai.com/v1"),
            model=str(cfg.get("embedding_model") or "text-embedding-3-small"),
        )
    if provider == "ollama":
        return OllamaEmbeddingProvider(
            base_url=str(cfg.get("embedding_base_url") or "http://127.0.0.1:11434"),
            model=str(cfg.get("embedding_model") or "nomic-embed-text"),
        )
    dim = int(cfg.get("vector_dimension") or 128)
    return HashEmbeddingProvider(dimension=dim)
