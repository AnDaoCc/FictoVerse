from __future__ import annotations

import sqlite3

from novel_world.core.domain.timestamps import from_iso, to_iso, utc_now
from novel_world.modules.ai.domain.entities import ProviderConfig, ProviderId, ProviderType
from novel_world.shared.json_codec import dumps_json, loads_json


class SqliteProviderRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def list_all(self) -> list[ProviderConfig]:
        rows = self._conn.execute(
            "SELECT * FROM llm_providers ORDER BY created_at DESC"
        ).fetchall()
        return [_row_to_provider(row) for row in rows]

    def list_enabled(self) -> list[ProviderConfig]:
        rows = self._conn.execute(
            "SELECT * FROM llm_providers WHERE enabled = 1 ORDER BY name"
        ).fetchall()
        return [_row_to_provider(row) for row in rows]

    def get(self, provider_id: ProviderId) -> ProviderConfig | None:
        row = self._conn.execute(
            "SELECT * FROM llm_providers WHERE id = ?", (provider_id,)
        ).fetchone()
        return _row_to_provider(row) if row else None

    def save(self, provider: ProviderConfig) -> None:
        now = utc_now()
        created = provider.created_at or now
        updated = provider.updated_at or now
        self._conn.execute(
            """
            INSERT INTO llm_providers (
                id, name, type, config_json, enabled, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                name = excluded.name,
                type = excluded.type,
                config_json = excluded.config_json,
                enabled = excluded.enabled,
                updated_at = excluded.updated_at
            """,
            (
                provider.id,
                provider.name,
                provider.type,
                dumps_json(provider.config),
                1 if provider.enabled else 0,
                to_iso(created),
                to_iso(updated),
            ),
        )

    def delete(self, provider_id: ProviderId) -> None:
        self._conn.execute("DELETE FROM llm_providers WHERE id = ?", (provider_id,))


def _row_to_provider(row: sqlite3.Row) -> ProviderConfig:
    ptype: ProviderType = row["type"]
    return ProviderConfig(
        id=row["id"],
        name=row["name"],
        type=ptype,
        config=loads_json(row["config_json"]),
        enabled=bool(row["enabled"]),
        created_at=from_iso(row["created_at"]),
        updated_at=from_iso(row["updated_at"]),
    )
