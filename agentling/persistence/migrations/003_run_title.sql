-- Add title column to runs for session summaries
ALTER TABLE runs ADD COLUMN title TEXT;

INSERT OR IGNORE INTO schema_migrations (version) VALUES (3);
