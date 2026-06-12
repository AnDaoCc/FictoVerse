-- 会话级长期记忆

CREATE TABLE IF NOT EXISTS chat_memories (
    session_id TEXT NOT NULL,
    id TEXT PRIMARY KEY,
    content TEXT NOT NULL,
    keywords_json TEXT NOT NULL DEFAULT '[]',
    pinned INTEGER NOT NULL DEFAULT 0,
    source_message_id TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    FOREIGN KEY (session_id) REFERENCES chat_sessions(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_memories_session ON chat_memories(session_id);
