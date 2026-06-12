from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from novel_world.infrastructure.migrations.sql_runner import run_versioned_migrations

APP_MIGRATIONS_DIR = (
    Path(__file__).resolve().parent.parent / "migrations" / "app_versions"
)


def _get_applied_version(conn: sqlite3.Connection) -> int:
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


def _set_applied_version(conn: sqlite3.Connection, version: int) -> None:
    conn.execute(
        """
        INSERT INTO meta (key, value) VALUES ('db_schema_version', ?)
        ON CONFLICT(key) DO UPDATE SET value = excluded.value
        """,
        (str(version),),
    )


def run_app_migrations(conn: sqlite3.Connection) -> int:
    return run_versioned_migrations(
        conn,
        migrations_dir=APP_MIGRATIONS_DIR,
        get_applied_version=_get_applied_version,
        set_applied_version=_set_applied_version,
    )


class AppDatabaseSession:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self._conn: sqlite3.Connection | None = None

    @property
    def connection(self) -> sqlite3.Connection:
        if self._conn is None:
            raise RuntimeError("App session is not open.")
        return self._conn

    def open(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.db_path)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys = ON")
        self._conn.execute("PRAGMA journal_mode = WAL")
        run_app_migrations(self._conn)

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    def commit(self) -> None:
        self.connection.commit()

    def rollback(self) -> None:
        self.connection.rollback()


@contextmanager
def open_app_session(db_path: Path) -> Iterator[AppDatabaseSession]:
    session = AppDatabaseSession(db_path)
    session.open()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
