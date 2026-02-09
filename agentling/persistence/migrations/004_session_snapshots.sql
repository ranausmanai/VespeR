-- Session snapshots for resumable interactive sessions
CREATE TABLE IF NOT EXISTS session_snapshots (
    id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL UNIQUE REFERENCES runs(id) ON DELETE CASCADE,
    session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    goal TEXT,
    summary_json TEXT NOT NULL,
    resume_prompt TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_session_snapshots_session_created
ON session_snapshots(session_id, created_at DESC);

INSERT OR IGNORE INTO schema_migrations (version) VALUES (4);
