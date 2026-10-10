-- 0017_agent_runtime
-- Codex-style outer harness: durable turns and action/observation items.
-- Messages remain user-facing conversation; items are bounded execution trace.

CREATE TABLE IF NOT EXISTS agent_turn (
    id              TEXT PRIMARY KEY,
    session_id      TEXT NOT NULL,
    status          TEXT NOT NULL DEFAULT 'RUNNING',
    input_text      TEXT NOT NULL DEFAULT '',
    route_json      TEXT NOT NULL DEFAULT '{}',
    max_steps       INTEGER NOT NULL DEFAULT 4,
    steps_used      INTEGER NOT NULL DEFAULT 0,
    stop_reason     TEXT NOT NULL DEFAULT '',
    started_at      TEXT NOT NULL,
    finished_at     TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_agent_turn_session ON agent_turn(session_id, started_at);

CREATE TABLE IF NOT EXISTS agent_item (
    id          TEXT PRIMARY KEY,
    turn_id     TEXT NOT NULL,
    session_id  TEXT NOT NULL,
    seq         INTEGER NOT NULL,
    item_type   TEXT NOT NULL,
    name        TEXT NOT NULL DEFAULT '',
    status      TEXT NOT NULL DEFAULT 'ok',
    payload_json TEXT NOT NULL DEFAULT '{}',
    created_at  TEXT NOT NULL,
    UNIQUE(turn_id, seq)
);
CREATE INDEX IF NOT EXISTS idx_agent_item_turn ON agent_item(turn_id, seq);
