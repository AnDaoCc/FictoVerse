from __future__ import annotations

import json
import sqlite3
from typing import Any

from novel_world.core.domain.timestamps import from_iso, to_iso, utc_now
from novel_world.modules.world.domain.lore_entry import LoreEntry, LoreEntryId, new_lore_entry_id


class SqliteLoreRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def list_all(self, *, character_id: str | None = None) -> list[LoreEntry]:
        if character_id:
            rows = self._conn.execute(
                """
                SELECT * FROM lore_entries
                WHERE (scope = 'world' OR (scope = 'character' AND character_id = ?))
                ORDER BY priority DESC, insertion_order ASC
                """,
                (character_id,),
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM lore_entries ORDER BY priority DESC, insertion_order ASC"
            ).fetchall()
        return [_row_to_lore(row) for row in rows if row["enabled"]]

    def list_all_admin(self, *, character_id: str | None = None) -> list[LoreEntry]:
        if character_id:
            rows = self._conn.execute(
                """
                SELECT * FROM lore_entries
                WHERE scope = 'world' OR (scope = 'character' AND character_id = ?)
                ORDER BY priority DESC, insertion_order ASC
                """,
                (character_id,),
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM lore_entries ORDER BY priority DESC, insertion_order ASC"
            ).fetchall()
        return [_row_to_lore(row) for row in rows]

    def get(self, entry_id: LoreEntryId) -> LoreEntry | None:
        row = self._conn.execute("SELECT * FROM lore_entries WHERE id = ?", (entry_id,)).fetchone()
        return _row_to_lore(row) if row else None

    def save(self, entry: LoreEntry) -> None:
        now = utc_now()
        created = entry.created_at or now
        updated = entry.updated_at or now
        self._conn.execute(
            """
            INSERT INTO lore_entries (
                id, scope, character_id, keys_json, content, constant, selective,
                recursive, priority, insertion_order, position, depth, enabled,
                comment, source, source_ref, created_at, updated_at,
                probability, lore_group, group_override, group_weight,
                cooldown, sticky, character_filter_json, filter_type,
                scan_depth, use_group_scoring,
                keys_secondary_json, selective_logic, match_whole_words, use_vector, vectorized
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                scope = excluded.scope,
                character_id = excluded.character_id,
                keys_json = excluded.keys_json,
                content = excluded.content,
                constant = excluded.constant,
                selective = excluded.selective,
                recursive = excluded.recursive,
                priority = excluded.priority,
                insertion_order = excluded.insertion_order,
                position = excluded.position,
                depth = excluded.depth,
                enabled = excluded.enabled,
                comment = excluded.comment,
                source = excluded.source,
                source_ref = excluded.source_ref,
                updated_at = excluded.updated_at,
                probability = excluded.probability,
                lore_group = excluded.lore_group,
                group_override = excluded.group_override,
                group_weight = excluded.group_weight,
                cooldown = excluded.cooldown,
                sticky = excluded.sticky,
                character_filter_json = excluded.character_filter_json,
                filter_type = excluded.filter_type,
                scan_depth = excluded.scan_depth,
                use_group_scoring = excluded.use_group_scoring,
                keys_secondary_json = excluded.keys_secondary_json,
                selective_logic = excluded.selective_logic,
                match_whole_words = excluded.match_whole_words,
                use_vector = excluded.use_vector,
                vectorized = excluded.vectorized
            """,
            (
                entry.id,
                entry.scope,
                entry.character_id,
                json.dumps(entry.keys, ensure_ascii=False),
                entry.content,
                1 if entry.constant else 0,
                1 if entry.selective else 0,
                1 if entry.recursive else 0,
                entry.priority,
                entry.insertion_order,
                entry.position,
                entry.depth,
                1 if entry.enabled else 0,
                entry.comment,
                entry.source,
                entry.source_ref,
                to_iso(created),
                to_iso(updated),
                entry.probability,
                entry.lore_group,
                1 if entry.group_override else 0,
                entry.group_weight,
                entry.cooldown,
                entry.sticky,
                json.dumps(entry.character_filter, ensure_ascii=False),
                entry.filter_type,
                entry.scan_depth,
                1 if entry.use_group_scoring else 0,
                json.dumps(entry.keys_secondary, ensure_ascii=False),
                entry.selective_logic,
                1 if entry.match_whole_words else 0,
                1 if entry.use_vector else 0,
                1 if entry.vectorized else 0,
            ),
        )

    def delete(self, entry_id: LoreEntryId) -> None:
        self._conn.execute("DELETE FROM lore_entries WHERE id = ?", (entry_id,))

    def delete_by_source(self, source: str, source_ref: str = "") -> None:
        if source_ref:
            self._conn.execute(
                "DELETE FROM lore_entries WHERE source = ? AND source_ref = ?",
                (source, source_ref),
            )
        else:
            self._conn.execute("DELETE FROM lore_entries WHERE source = ?", (source,))


def _row_get(row: sqlite3.Row, key: str, default: Any = None) -> Any:
    try:
        return row[key]
    except (KeyError, IndexError):
        return default


def _row_to_lore(row: sqlite3.Row) -> LoreEntry:
    keys_raw = row["keys_json"]
    try:
        keys = json.loads(keys_raw) if keys_raw else []
    except json.JSONDecodeError:
        keys = []
    filt_raw = _row_get(row, "character_filter_json", "[]")
    try:
        filt = json.loads(filt_raw) if filt_raw else []
    except json.JSONDecodeError:
        filt = []
    sec_raw = _row_get(row, "keys_secondary_json", "[]")
    try:
        keys_sec = json.loads(sec_raw) if sec_raw else []
    except json.JSONDecodeError:
        keys_sec = []
    return LoreEntry(
        id=row["id"],
        scope=row["scope"],
        character_id=row["character_id"] or "",
        keys=[str(k) for k in keys] if isinstance(keys, list) else [],
        keys_secondary=[str(k) for k in keys_sec] if isinstance(keys_sec, list) else [],
        selective_logic=int(_row_get(row, "selective_logic", 0) or 0),
        match_whole_words=bool(_row_get(row, "match_whole_words", 0)),
        use_vector=bool(_row_get(row, "use_vector", 0)),
        vectorized=bool(_row_get(row, "vectorized", 0)),
        content=row["content"] or "",
        constant=bool(row["constant"]),
        selective=bool(row["selective"]),
        recursive=bool(row["recursive"]),
        priority=row["priority"] or 0,
        insertion_order=row["insertion_order"] or 0,
        position=row["position"] or "before_main",
        depth=row["depth"] or 4,
        enabled=bool(row["enabled"]),
        comment=row["comment"] or "",
        source=row["source"] or "manual",
        source_ref=row["source_ref"] or "",
        probability=float(_row_get(row, "probability", 1.0) or 1.0),
        lore_group=str(_row_get(row, "lore_group", "") or ""),
        group_override=bool(_row_get(row, "group_override", 0)),
        group_weight=int(_row_get(row, "group_weight", 100) or 100),
        cooldown=int(_row_get(row, "cooldown", 0) or 0),
        sticky=int(_row_get(row, "sticky", 0) or 0),
        character_filter=[str(x) for x in filt] if isinstance(filt, list) else [],
        filter_type=_row_get(row, "filter_type", "include") or "include",
        scan_depth=int(_row_get(row, "scan_depth", 0) or 0),
        use_group_scoring=bool(_row_get(row, "use_group_scoring", 0)),
        created_at=from_iso(row["created_at"]),
        updated_at=from_iso(row["updated_at"]),
    )


def new_lore_entry(**kwargs: Any) -> LoreEntry:
    now = utc_now()
    return LoreEntry(id=new_lore_entry_id(), created_at=now, updated_at=now, **kwargs)
