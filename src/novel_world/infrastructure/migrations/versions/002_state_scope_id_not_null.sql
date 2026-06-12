-- 002_state_scope_id_not_null.sql
-- 统一 state_entries.scope_id：将 NULL 归一化为 ''，避免 UNIQUE 约束在 NULL 上失效

UPDATE state_entries
SET scope_id = ''
WHERE scope_id IS NULL;

