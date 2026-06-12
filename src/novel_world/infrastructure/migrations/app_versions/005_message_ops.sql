-- 消息操作：分支、swipe 候选

ALTER TABLE chat_messages ADD COLUMN parent_id TEXT NOT NULL DEFAULT '';
ALTER TABLE chat_messages ADD COLUMN variants_json TEXT NOT NULL DEFAULT '[]';
ALTER TABLE chat_messages ADD COLUMN active_variant INTEGER NOT NULL DEFAULT 0;
