from __future__ import annotations

import json
import math
import sqlite3
import uuid
from dataclasses import dataclass
from typing import Any

from novel_world.core.domain.timestamps import utc_now
from novel_world.modules.ai.ports.embedding_provider import EmbeddingProvider


def _cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


@dataclass
class VectorChunk:
    id: str
    scope: str
    scope_id: str
    source_type: str
    source_id: str
    chunk_index: int
    content: str
    embedding: list[float]
    metadata: dict[str, Any]


class VectorIndex:
    def __init__(self, conn: sqlite3.Connection, embedder: EmbeddingProvider) -> None:
        self._conn = conn
        self._embedder = embedder

    def delete_source(self, *, source_type: str, source_id: str) -> None:
        self._conn.execute(
            "DELETE FROM vector_chunks WHERE source_type = ? AND source_id = ?",
            (source_type, source_id),
        )

    def upsert_chunks(
        self,
        *,
        scope: str,
        scope_id: str,
        source_type: str,
        source_id: str,
        chunks: list[str],
        metadata: dict[str, Any] | None = None,
    ) -> int:
        self.delete_source(source_type=source_type, source_id=source_id)
        if not chunks:
            return 0
        vectors = self._embedder.embed(chunks)
        now = utc_now().isoformat()
        meta_json = json.dumps(metadata or {}, ensure_ascii=False)
        for idx, (text, vec) in enumerate(zip(chunks, vectors)):
            cid = str(uuid.uuid4())
            self._conn.execute(
                """
                INSERT INTO vector_chunks
                (id, scope, scope_id, source_type, source_id, chunk_index, content, embedding_json, metadata_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    cid,
                    scope,
                    scope_id,
                    source_type,
                    source_id,
                    idx,
                    text,
                    json.dumps(vec),
                    meta_json,
                    now,
                ),
            )
        return len(chunks)

    def search(
        self,
        query: str,
        *,
        scope: str | None = None,
        scope_id: str | None = None,
        source_type: str | None = None,
        top_k: int = 5,
    ) -> list[tuple[VectorChunk, float]]:
        qvec = self._embedder.embed([query])[0]
        sql = "SELECT * FROM vector_chunks WHERE 1=1"
        params: list[Any] = []
        if scope:
            sql += " AND scope = ?"
            params.append(scope)
        if scope_id:
            sql += " AND scope_id = ?"
            params.append(scope_id)
        if source_type:
            sql += " AND source_type = ?"
            params.append(source_type)
        rows = self._conn.execute(sql, params).fetchall()
        scored: list[tuple[VectorChunk, float]] = []
        for row in rows:
            vec = json.loads(row["embedding_json"] or "[]")
            score = _cosine(qvec, vec)
            scored.append(
                (
                    VectorChunk(
                        id=row["id"],
                        scope=row["scope"],
                        scope_id=row["scope_id"],
                        source_type=row["source_type"],
                        source_id=row["source_id"],
                        chunk_index=int(row["chunk_index"]),
                        content=row["content"],
                        embedding=vec,
                        metadata=json.loads(row["metadata_json"] or "{}"),
                    ),
                    score,
                )
            )
        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[: max(1, top_k)]
