-- 聊天增强：思考过程、状态；文档与附件

ALTER TABLE chat_messages ADD COLUMN thinking_content TEXT NOT NULL DEFAULT '';
ALTER TABLE chat_messages ADD COLUMN status TEXT NOT NULL DEFAULT 'done';

CREATE TABLE IF NOT EXISTS world_documents (
    id TEXT PRIMARY KEY,
    world_id TEXT NOT NULL,
    filename TEXT NOT NULL,
    mime_type TEXT NOT NULL DEFAULT '',
    storage_path TEXT NOT NULL,
    extracted_text TEXT NOT NULL DEFAULT '',
    uploaded_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_world_documents_world ON world_documents(world_id);

CREATE TABLE IF NOT EXISTS chat_attachments (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    message_id TEXT,
    filename TEXT NOT NULL,
    mime_type TEXT NOT NULL DEFAULT '',
    storage_path TEXT NOT NULL,
    extracted_text TEXT NOT NULL DEFAULT '',
    uploaded_at TEXT NOT NULL,
    FOREIGN KEY (session_id) REFERENCES chat_sessions(id)
);

CREATE INDEX IF NOT EXISTS idx_chat_attachments_session ON chat_attachments(session_id);
