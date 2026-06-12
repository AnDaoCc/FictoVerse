from __future__ import annotations

import sqlite3
from typing import Any

from novel_world.infrastructure.user_preferences import get_user_prefs
from novel_world.modules.ai.ports.embedding_provider import build_embedding_provider
from novel_world.modules.ai.services.lore_engine import LoreEngine, LoreResult
from novel_world.modules.ai.services.lore_session_state import LoreSessionState
from novel_world.modules.world.domain.lore_entry import LoreEntry


class HybridLoreEngine(LoreEngine):
    def __init__(self, conn: sqlite3.Connection | None = None) -> None:
        super().__init__()
        self._conn = conn

    def scan(
        self,
        entries: list[LoreEntry],
        scan_text: str,
        *,
        token_budget: int = 2000,
        case_sensitive: bool = False,
        session_state: LoreSessionState | None = None,
        active_character_id: str = "",
        active_character_name: str = "",
        messages: list | None = None,
        user_input: str = "",
        scan_limit: int = 12,
        world_id: str = "",
    ) -> LoreResult:
        result = super().scan(
            entries,
            scan_text,
            token_budget=token_budget,
            case_sensitive=case_sensitive,
            session_state=session_state,
            active_character_id=active_character_id,
            active_character_name=active_character_name,
            messages=messages,
            user_input=user_input,
            scan_limit=scan_limit,
        )
        if not self._conn or not scan_text.strip():
            return result

        vector_entries = [e for e in entries if e.enabled and (e.use_vector or e.vectorized)]
        if not vector_entries:
            return result

        prefs = get_user_prefs(self._conn)
        min_score = float(prefs.get("vector_min_score") or 0.2)
        embedder = build_embedding_provider(prefs)
        qvec = embedder.embed([scan_text])[0]
        state = session_state or LoreSessionState()
        used_tokens = sum(max(1, len(c) // 2) for c in result.all_text().split("\n\n") if c)

        scored: list[tuple[LoreEntry, float]] = []
        for entry in vector_entries:
            if entry.id in result.matched_ids:
                continue
            avec = embedder.embed([entry.content])[0]
            from novel_world.modules.ai.services.vector_index import _cosine

            score = _cosine(qvec, avec)
            if score >= min_score:
                scored.append((entry, score))
        scored.sort(key=lambda x: x[1], reverse=True)

        for entry, _score in scored[:8]:
            if entry.id in result.matched_ids:
                continue
            if not self._passes_character_filter(entry, active_character_id, active_character_name):
                continue
            if state.is_on_cooldown(entry.id) and not state.is_sticky_active(entry.id):
                continue
            if not LoreSessionState.passes_probability(entry):
                continue
            est = max(1, len(entry.content) // 2)
            if used_tokens + est > token_budget and not entry.constant:
                continue
            used_tokens += est
            result.append_text(entry.position, entry.content, entry)
        return result
