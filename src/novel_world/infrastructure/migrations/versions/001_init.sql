-- 001_init.sql — 世界数据库初始表结构

CREATE TABLE IF NOT EXISTS meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS worlds (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    genre TEXT NOT NULL DEFAULT '',
    rules_json TEXT NOT NULL DEFAULT '{}',
    settings_json TEXT NOT NULL DEFAULT '{}',
    schema_version INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS characters (
    id TEXT PRIMARY KEY,
    world_id TEXT NOT NULL,
    name TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'npc',
    profile_json TEXT NOT NULL DEFAULT '{}',
    attributes_json TEXT NOT NULL DEFAULT '{}',
    metadata_json TEXT NOT NULL DEFAULT '{}',
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (world_id) REFERENCES worlds(id)
);

CREATE INDEX IF NOT EXISTS idx_characters_world ON characters(world_id);
CREATE UNIQUE INDEX IF NOT EXISTS idx_characters_world_name ON characters(world_id, name);

CREATE TABLE IF NOT EXISTS state_entries (
    id TEXT PRIMARY KEY,
    world_id TEXT NOT NULL,
    scope TEXT NOT NULL,
    scope_id TEXT NOT NULL DEFAULT '',
    key TEXT NOT NULL,
    value_json TEXT NOT NULL,
    value_type TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (world_id) REFERENCES worlds(id),
    UNIQUE (world_id, scope, scope_id, key)
);

CREATE INDEX IF NOT EXISTS idx_state_world ON state_entries(world_id);

CREATE TABLE IF NOT EXISTS events (
    id TEXT PRIMARY KEY,
    world_id TEXT NOT NULL,
    seq INTEGER NOT NULL,
    event_type TEXT NOT NULL,
    world_time TEXT,
    real_time TEXT NOT NULL,
    actor_id TEXT,
    payload_json TEXT NOT NULL DEFAULT '{}',
    causation_id TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY (world_id) REFERENCES worlds(id),
    FOREIGN KEY (actor_id) REFERENCES characters(id),
    FOREIGN KEY (causation_id) REFERENCES events(id)
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_events_world_seq ON events(world_id, seq);
CREATE INDEX IF NOT EXISTS idx_events_world_type ON events(world_id, event_type);

CREATE TABLE IF NOT EXISTS save_slots (
    id TEXT PRIMARY KEY,
    world_id TEXT NOT NULL,
    slot_index INTEGER NOT NULL,
    label TEXT NOT NULL DEFAULT '',
    snapshot_path TEXT NOT NULL,
    snapshot_version INTEGER NOT NULL,
    world_time_at_save TEXT,
    checksum TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (world_id) REFERENCES worlds(id),
    UNIQUE (world_id, slot_index)
);
