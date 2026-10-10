-- 0016_conversation_journal
-- Conversation-first：保存用户原话和轻量日记，不把它们冒充 Research / Decision 事实。

CREATE TABLE IF NOT EXISTS agent_journal_entry (
    id                TEXT PRIMARY KEY,
    session_id        TEXT NOT NULL DEFAULT '',
    source_message_id TEXT NOT NULL DEFAULT '',
    entry_date        TEXT NOT NULL,
    entry_type        TEXT NOT NULL DEFAULT 'GENERAL',
    raw_text          TEXT NOT NULL,
    summary           TEXT NOT NULL DEFAULT '',
    entity_refs_json  TEXT NOT NULL DEFAULT '[]',
    created_at        TEXT NOT NULL,
    CHECK (entry_type IN ('FEELING','THOUGHT','TRADE_NOTE','REVIEW_NOTE','GENERAL'))
);

CREATE INDEX IF NOT EXISTS idx_agent_journal_date
    ON agent_journal_entry(entry_date, created_at);
CREATE INDEX IF NOT EXISTS idx_agent_journal_session
    ON agent_journal_entry(session_id, created_at);
