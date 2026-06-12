from __future__ import annotations

import sqlite3
from pathlib import Path

from novel_world.infrastructure.migrations.sql_runner import run_versioned_migrations
MIGRATIONS_DIR = Path(__file__).resolve().parent / "versions"


def get_applied_version(conn: sqlite3.Connection) -> int:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS meta (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
        """
    )
    row = conn.execute(
        "SELECT value FROM meta WHERE key = 'db_schema_version'"
    ).fetchone()
    if row is None:
        return 0
    return int(row[0])


def set_applied_version(conn: sqlite3.Connection, version: int) -> None:
    conn.execute(
        """
        INSERT INTO meta (key, value) VALUES ('db_schema_version', ?)
        ON CONFLICT(key) DO UPDATE SET value = excluded.value
        """,
        (str(version),),
    )


def run_migrations(conn: sqlite3.Connection) -> int:
    return run_versioned_migrations(
        conn,
        migrations_dir=MIGRATIONS_DIR,
        get_applied_version=get_applied_version,
        set_applied_version=set_applied_version,
    )
