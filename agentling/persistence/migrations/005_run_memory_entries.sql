-- Structured run memory entries for smart context assembly
CREATE TABLE IF NOT EXISTS run_memory_entries (
    id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL UNIQUE REFERENCES runs(id) ON DELETE CASCADE,
    session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    objective TEXT,
    short_summary TEXT NOT NULL,
    memory_json TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_run_memory_entries_session_created
ON run_memory_entries(session_id, created_at DESC);

INSERT OR IGNORE INTO schema_migrations (version) VALUES (5);
