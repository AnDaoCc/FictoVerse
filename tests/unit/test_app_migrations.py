from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from novel_world.infrastructure.db.app_session import AppDatabaseSession, run_app_migrations


def test_app_migration_rerun_after_partial_ddl(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    init_sql = (
        Path(__file__).resolve().parents[2]
        / "src/novel_world/infrastructure/migrations/app_versions/001_init.sql"
    ).read_text(encoding="utf-8")

    conn = sqlite3.connect(db_path)
    conn.executescript(init_sql)
    conn.execute(
        "INSERT INTO meta (key, value) VALUES ('db_schema_version', '1') ON CONFLICT(key) DO UPDATE SET value = excluded.value"
    )
    conn.execute("ALTER TABLE chat_messages ADD COLUMN thinking_content TEXT NOT NULL DEFAULT ''")
    conn.execute("ALTER TABLE chat_messages ADD COLUMN status TEXT NOT NULL DEFAULT 'done'")
    conn.commit()
    conn.close()

    session = AppDatabaseSession(db_path)
    session.open()
    version = session.connection.execute(
        "SELECT value FROM meta WHERE key = 'db_schema_version'"
    ).fetchone()[0]
    cols = {
        row[1]
        for row in session.connection.execute("PRAGMA table_info(chat_sessions)").fetchall()
    }
    session.close()

    # 002 部分执行后重跑应幂等推进到最新版本，且 003 的摘要列已就绪
    assert int(version) >= 2
    assert "summary_content" in cols
    assert "summary_until" in cols


def test_app_migration_version_persists_without_runtime_commit(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    session = AppDatabaseSession(db_path)
    session.open()
    session.close()

    conn = sqlite3.connect(db_path)
    version = conn.execute(
        "SELECT value FROM meta WHERE key = 'db_schema_version'"
    ).fetchone()[0]
    conn.close()

    assert int(version) >= 2

    session = AppDatabaseSession(db_path)
    session.open()
    session.close()
