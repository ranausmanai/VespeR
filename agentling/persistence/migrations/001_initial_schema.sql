-- Agentling Visual UI Schema
-- Sessions, Runs, Events, Git Snapshots

-- Sessions: A working context (project directory + settings)
CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY,
    name TEXT,
    working_dir TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    config_json TEXT,
    status TEXT DEFAULT 'active'
);
CREATE INDEX IF NOT EXISTS idx_sessions_status ON sessions(status);
CREATE INDEX IF NOT EXISTS idx_sessions_updated ON sessions(updated_at);

-- Runs: A single execution within a session
CREATE TABLE IF NOT EXISTS runs (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    parent_run_id TEXT REFERENCES runs(id),
    branch_point_event_id TEXT,
    prompt TEXT NOT NULL,
    status TEXT DEFAULT 'pending',
    model TEXT,
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    tokens_in INTEGER DEFAULT 0,
    tokens_out INTEGER DEFAULT 0,
    cost_usd REAL DEFAULT 0.0,
    duration_ms INTEGER DEFAULT 0,
    final_output TEXT,
    error_message TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_runs_session ON runs(session_id);
CREATE INDEX IF NOT EXISTS idx_runs_status ON runs(status);
CREATE INDEX IF NOT EXISTS idx_runs_parent ON runs(parent_run_id);

-- Events: Immutable event log (event sourcing)
CREATE TABLE IF NOT EXISTS events (
    id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
    session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    type TEXT NOT NULL,
    sequence INTEGER NOT NULL,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    payload_json TEXT NOT NULL,
    parent_event_id TEXT REFERENCES events(id)
);
CREATE INDEX IF NOT EXISTS idx_events_run_seq ON events(run_id, sequence);
CREATE INDEX IF NOT EXISTS idx_events_type ON events(type);
CREATE INDEX IF NOT EXISTS idx_events_timestamp ON events(timestamp);

-- Git snapshots: Point-in-time git state
CREATE TABLE IF NOT EXISTS git_snapshots (
    id TEXT PRIMARY KEY,
    event_id TEXT NOT NULL REFERENCES events(id) ON DELETE CASCADE,
    run_id TEXT NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
    commit_hash TEXT,
    branch TEXT,
    dirty_files_json TEXT,
    staged_files_json TEXT,
    diff_stat TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_git_run ON git_snapshots(run_id);
CREATE INDEX IF NOT EXISTS idx_git_event ON git_snapshots(event_id);

-- File changes: Individual file modifications per snapshot
CREATE TABLE IF NOT EXISTS file_changes (
    id TEXT PRIMARY KEY,
    git_snapshot_id TEXT NOT NULL REFERENCES git_snapshots(id) ON DELETE CASCADE,
    file_path TEXT NOT NULL,
    change_type TEXT NOT NULL,
    lines_added INTEGER DEFAULT 0,
    lines_removed INTEGER DEFAULT 0,
    diff_patch TEXT
);
CREATE INDEX IF NOT EXISTS idx_file_changes_snapshot ON file_changes(git_snapshot_id);

-- Interventions: Human actions during runs
CREATE TABLE IF NOT EXISTS interventions (
    id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
    event_id TEXT NOT NULL REFERENCES events(id) ON DELETE CASCADE,
    type TEXT NOT NULL,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    input_json TEXT,
    result_json TEXT
);
CREATE INDEX IF NOT EXISTS idx_interventions_run ON interventions(run_id);

-- Schema version tracking
CREATE TABLE IF NOT EXISTS schema_migrations (
    version INTEGER PRIMARY KEY,
    applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

INSERT OR IGNORE INTO schema_migrations (version) VALUES (1);
