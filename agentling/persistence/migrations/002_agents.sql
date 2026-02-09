-- Agents: Reusable agent templates/definitions
CREATE TABLE IF NOT EXISTS agents (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT,
    role TEXT,  -- e.g., 'generator', 'critic', 'expert', 'reviewer'
    personality TEXT,  -- behavioral traits
    system_prompt TEXT,
    model TEXT DEFAULT 'sonnet',
    tools_json TEXT,  -- allowed tools as JSON array
    constraints_json TEXT,  -- operational constraints as JSON
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_agents_name ON agents(name);
CREATE INDEX IF NOT EXISTS idx_agents_role ON agents(role);

-- Agent Runs: Links agents to runs for traceability in multi-agent patterns
CREATE TABLE IF NOT EXISTS agent_runs (
    id TEXT PRIMARY KEY,
    agent_id TEXT NOT NULL REFERENCES agents(id) ON DELETE CASCADE,
    run_id TEXT NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
    parent_agent_run_id TEXT REFERENCES agent_runs(id),  -- for chained agents
    pattern TEXT NOT NULL,  -- 'solo', 'loop', 'panel', 'debate'
    role_in_pattern TEXT,  -- e.g., 'generator', 'critic' in loop pattern
    sequence INTEGER DEFAULT 0,  -- order within pattern execution
    iteration INTEGER DEFAULT 0,  -- for loops: which iteration
    status TEXT DEFAULT 'pending',
    input_text TEXT,
    output_text TEXT,
    metadata_json TEXT,  -- additional context
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_agent_runs_agent ON agent_runs(agent_id);
CREATE INDEX IF NOT EXISTS idx_agent_runs_run ON agent_runs(run_id);
CREATE INDEX IF NOT EXISTS idx_agent_runs_parent ON agent_runs(parent_agent_run_id);
CREATE INDEX IF NOT EXISTS idx_agent_runs_pattern ON agent_runs(pattern);
CREATE INDEX IF NOT EXISTS idx_agent_runs_status ON agent_runs(status);

-- Agent Patterns: Saved multi-agent workflow configurations
CREATE TABLE IF NOT EXISTS agent_patterns (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT,
    pattern_type TEXT NOT NULL,  -- 'solo', 'loop', 'panel', 'debate'
    config_json TEXT NOT NULL,  -- pattern configuration (agents, order, rules)
    human_involvement TEXT DEFAULT 'checkpoints',  -- 'autonomous', 'checkpoints', 'on_demand'
    max_iterations INTEGER DEFAULT 3,  -- for loop patterns
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_agent_patterns_type ON agent_patterns(pattern_type);

INSERT OR IGNORE INTO schema_migrations (version) VALUES (2);
