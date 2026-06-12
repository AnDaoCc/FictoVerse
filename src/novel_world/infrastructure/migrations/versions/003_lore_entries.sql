-- Lorebook 条目（世界库）

CREATE TABLE IF NOT EXISTS lore_entries (
    id TEXT PRIMARY KEY,
    scope TEXT NOT NULL DEFAULT 'world',
    character_id TEXT NOT NULL DEFAULT '',
    keys_json TEXT NOT NULL DEFAULT '[]',
    content TEXT NOT NULL DEFAULT '',
    constant INTEGER NOT NULL DEFAULT 0,
    selective INTEGER NOT NULL DEFAULT 1,
    recursive INTEGER NOT NULL DEFAULT 0,
    priority INTEGER NOT NULL DEFAULT 0,
    insertion_order INTEGER NOT NULL DEFAULT 0,
    position TEXT NOT NULL DEFAULT 'before_main',
    depth INTEGER NOT NULL DEFAULT 4,
    enabled INTEGER NOT NULL DEFAULT 1,
    comment TEXT NOT NULL DEFAULT '',
    source TEXT NOT NULL DEFAULT 'manual',
    source_ref TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_lore_scope ON lore_entries(scope, character_id);
