-- 005: Lore 向量与 ST 匹配字段
ALTER TABLE lore_entries ADD COLUMN keys_secondary_json TEXT NOT NULL DEFAULT '[]';
ALTER TABLE lore_entries ADD COLUMN selective_logic INTEGER NOT NULL DEFAULT 0;
ALTER TABLE lore_entries ADD COLUMN match_whole_words INTEGER NOT NULL DEFAULT 0;
ALTER TABLE lore_entries ADD COLUMN use_vector INTEGER NOT NULL DEFAULT 0;
ALTER TABLE lore_entries ADD COLUMN vectorized INTEGER NOT NULL DEFAULT 0;

CREATE TABLE IF NOT EXISTS data_bank_chunks (
    id TEXT PRIMARY KEY,
    scope TEXT NOT NULL DEFAULT 'world',
    world_id TEXT NOT NULL DEFAULT '',
    session_ref TEXT NOT NULL DEFAULT '',
    document_id TEXT NOT NULL DEFAULT '',
    title TEXT NOT NULL DEFAULT '',
    chunk_index INTEGER NOT NULL DEFAULT 0,
    content TEXT NOT NULL DEFAULT '',
    embedding_json TEXT NOT NULL DEFAULT '[]',
    enabled INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_data_bank_world ON data_bank_chunks(world_id);
