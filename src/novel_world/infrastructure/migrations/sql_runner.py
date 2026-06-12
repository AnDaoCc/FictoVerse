from __future__ import annotations

import re
import sqlite3

_BENIGN_OPERATIONAL = (
    "duplicate column name",
    "already exists",
)


def split_sql_statements(sql: str) -> list[str]:
    lines: list[str] = []
    for line in sql.splitlines():
        if line.strip().startswith("--"):
            continue
        lines.append(line)
    normalized = "\n".join(lines).strip()
    if not normalized:
        return []
    return [part.strip() for part in normalized.split(";") if part.strip()]


def _is_benign_operational_error(exc: sqlite3.OperationalError) -> bool:
    message = str(exc).lower()
    return any(token in message for token in _BENIGN_OPERATIONAL)


def execute_migration_script(conn: sqlite3.Connection, sql: str) -> None:
    for statement in split_sql_statements(sql):
        try:
            conn.execute(statement)
        except sqlite3.OperationalError as exc:
            if not _is_benign_operational_error(exc):
                raise


def run_versioned_migrations(
    conn: sqlite3.Connection,
    *,
    migrations_dir,
    get_applied_version,
    set_applied_version,
) -> int:
    applied = get_applied_version(conn)
    migration_files = sorted(migrations_dir.glob("*.sql"))
    for path in migration_files:
        match = re.match(r"^(\d+)_", path.stem)
        if not match:
            continue
        version = int(match.group(1))
        if version <= applied:
            continue
        execute_migration_script(conn, path.read_text(encoding="utf-8"))
        set_applied_version(conn, version)
        conn.commit()
        applied = version
    return applied
