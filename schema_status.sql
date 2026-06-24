CREATE TABLE IF NOT EXISTS task_status (
    id          SERIAL PRIMARY KEY,
    search_id   TEXT NOT NULL,
    source      TEXT NOT NULL,
    worker_id   TEXT,
    fetched     INTEGER DEFAULT 0,
    inserted    INTEGER DEFAULT 0,
    finished_at TIMESTAMP DEFAULT NOW(),
    UNIQUE (search_id, source)
);

CREATE INDEX IF NOT EXISTS idx_task_status_search ON task_status(search_id);