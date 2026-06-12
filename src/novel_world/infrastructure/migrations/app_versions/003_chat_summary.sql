-- 对话滚动摘要：用于压缩较早历史，降低 token 消耗

ALTER TABLE chat_sessions ADD COLUMN summary_content TEXT NOT NULL DEFAULT '';
ALTER TABLE chat_sessions ADD COLUMN summary_until INTEGER NOT NULL DEFAULT 0;
