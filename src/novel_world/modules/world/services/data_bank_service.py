from __future__ import annotations

import json
import sqlite3
import uuid
from typing import Any

from novel_world.core.domain.timestamps import utc_now
from novel_world.core.exceptions import ValidationError
from novel_world.modules.ai.ports.embedding_provider import build_embedding_provider
from novel_world.modules.ai.services.vector_index import _cosine
from novel_world.modules.documents.services.document_chunker import chunk_text


class DataBankService:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def list_chunks(self, world_id: str) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            "SELECT * FROM data_bank_chunks WHERE world_id = ? ORDER BY title, chunk_index",
            (world_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    def index_text(
        self,
        *,
        world_id: str,
        title: str,
        content: str,
        document_id: str = "",
        chunk_size: int = 500,
    ) -> int:
        chunks = chunk_text(content, chunk_size=chunk_size)
        if not chunks:
            raise ValidationError("资料库内容为空。")
        doc_id = document_id or str(uuid.uuid4())
        self._conn.execute(
            "DELETE FROM data_bank_chunks WHERE world_id = ? AND document_id = ?",
            (world_id, doc_id),
        )
        vectors = build_embedding_provider({}).embed(chunks)
        now = utc_now().isoformat()
        for idx, (text, vec) in enumerate(zip(chunks, vectors)):
            cid = str(uuid.uuid4())
            self._conn.execute(
                """
                INSERT INTO data_bank_chunks
                (id, scope, world_id, session_ref, document_id, title, chunk_index, content, embedding_json, enabled, created_at, updated_at)
                VALUES (?, 'world', ?, '', ?, ?, ?, ?, ?, 1, ?, ?)
                """,
                (cid, world_id, doc_id, title, idx, text, json.dumps(vec), now, now),
            )
        return len(chunks)

    def search(self, world_id: str, query: str, *, top_k: int = 5, min_score: float = 0.2) -> list[str]:
        if not query.strip():
            return []
        qvec = build_embedding_provider({}).embed([query])[0]
        rows = self._conn.execute(
            "SELECT content, embedding_json FROM data_bank_chunks WHERE world_id = ? AND enabled = 1",
            (world_id,),
        ).fetchall()
        scored: list[tuple[str, float]] = []
        for row in rows:
            vec = json.loads(row["embedding_json"] or "[]")
            score = _cosine(qvec, vec)
            if score >= min_score:
                scored.append((row["content"], score))
        scored.sort(key=lambda x: x[1], reverse=True)
        return [text for text, _ in scored[:top_k]]

    def export_st(self, world_id: str) -> dict[str, Any]:
        rows = self.list_chunks(world_id)
        entries: dict[str, Any] = {}
        for i, row in enumerate(rows):
            entries[str(i)] = {
                "title": row.get("title") or "",
                "content": row.get("content") or "",
                "enabled": bool(row.get("enabled", 1)),
            }
        return {"entries": entries}

    def import_st(self, world_id: str, raw: dict[str, Any] | list[Any]) -> int:
        count = 0
        items = raw.get("entries") if isinstance(raw, dict) else raw
        if isinstance(items, dict):
            iterable = items.values()
        elif isinstance(items, list):
            iterable = items
        else:
            raise ValidationError("Data Bank JSON 无效。")
        for item in iterable:
            if not isinstance(item, dict):
                continue
            title = str(item.get("title") or item.get("name") or "imported")
            content = str(item.get("content") or item.get("text") or "").strip()
            if content:
                self.index_text(world_id=world_id, title=title, content=content)
                count += 1
        return count
