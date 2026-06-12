-- 007: 向量分块索引（app 库，Lore/Data Bank 共用）
CREATE TABLE IF NOT EXISTS vector_chunks (
    id TEXT PRIMARY KEY,
    scope TEXT NOT NULL DEFAULT 'app',
    scope_id TEXT NOT NULL DEFAULT '',
    source_type TEXT NOT NULL DEFAULT 'document',
    source_id TEXT NOT NULL DEFAULT '',
    chunk_index INTEGER NOT NULL DEFAULT 0,
    content TEXT NOT NULL DEFAULT '',
    embedding_json TEXT NOT NULL DEFAULT '[]',
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_vector_chunks_scope ON vector_chunks(scope, scope_id);
CREATE INDEX IF NOT EXISTS idx_vector_chunks_source ON vector_chunks(source_type, source_id);
