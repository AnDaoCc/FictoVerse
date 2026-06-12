-- 群聊：会话类型、成员、发言者信息

ALTER TABLE chat_sessions ADD COLUMN session_type TEXT NOT NULL DEFAULT 'chat';
ALTER TABLE chat_sessions ADD COLUMN config_json TEXT NOT NULL DEFAULT '{}';

CREATE TABLE IF NOT EXISTS group_session_members (
    session_id TEXT NOT NULL,
    world_id TEXT NOT NULL,
    character_id TEXT NOT NULL,
    character_name TEXT NOT NULL,
    world_name TEXT NOT NULL,
    sort_order INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (session_id, world_id, character_id),
    FOREIGN KEY (session_id) REFERENCES chat_sessions(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_group_members_session ON group_session_members(session_id);

ALTER TABLE chat_messages ADD COLUMN speaker_json TEXT NOT NULL DEFAULT '';
