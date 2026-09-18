import os
import hashlib
from dotenv import load_dotenv
from connections import get_db_connection

load_dotenv()


# Columns added after the tables were first created. Every database
# (local Docker or online) gets them automatically when a service starts,
# so the code and the database can't drift apart.
SCHEMA_UPDATES = [
    "ALTER TABLE jobs ADD COLUMN IF NOT EXISTS url TEXT",
    "ALTER TABLE task_status ADD COLUMN IF NOT EXISTS error TEXT",
    # Lifecycle tracking (phase 2, weeks 7-8). Existing rows get the
    # defaults, so the whole dataset is covered without a separate backfill.
    "ALTER TABLE jobs ADD COLUMN IF NOT EXISTS first_seen TIMESTAMP DEFAULT NOW()",
    "ALTER TABLE jobs ADD COLUMN IF NOT EXISTS last_seen TIMESTAMP DEFAULT NOW()",
    "ALTER TABLE jobs ADD COLUMN IF NOT EXISTS status TEXT DEFAULT 'active'",
    "CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status)",
    "CREATE INDEX IF NOT EXISTS idx_jobs_last_seen ON jobs(last_seen)",
]


# SQL files that create the tables (they use CREATE TABLE IF NOT EXISTS)
SCHEMA_FILES = ["schema.sql", "schema_status.sql"]


def ensure_schema():
    """Create any missing tables, then apply SCHEMA_UPDATES.
    Safe to run every time (IF NOT EXISTS), so a brand-new empty
    database is set up automatically."""
    base_dir = os.path.dirname(os.path.abspath(__file__))
    conn = get_db_connection()
    cur = conn.cursor()
    for filename in SCHEMA_FILES:
        with open(os.path.join(base_dir, filename), encoding="utf-8") as f:
            cur.execute(f.read())
    for statement in SCHEMA_UPDATES:
        cur.execute(statement)
    conn.commit()
    cur.close()
    conn.close()
    print("[db] schema is up to date", flush=True)


def make_fingerprint(title, company, location):
    """Deterministic dedup key from title + company + location."""
    raw = f"{(title or '').strip().lower()}|{(company or '').strip().lower()}|{(location or '').strip().lower()}"
    return hashlib.sha256(raw.encode()).hexdigest()


def save_jobs(jobs, search_id):
    """Insert jobs into Postgres.

    A job we have seen before is not re-inserted: its last_seen is refreshed
    and it is marked active again, which is how "this listing is still up"
    is recorded. Returns (inserted_count, skipped_count)."""
    conn = get_db_connection()
    cur = conn.cursor()
    inserted = 0
    for j in jobs:
        cur.execute("""
            INSERT INTO jobs (title, company, location, skills, salary_min, salary_max,
                              job_type, experience_level, posted_date, source, fingerprint, search_id, url)
            VALUES (%(title)s, %(company)s, %(location)s, %(skills)s, %(salary_min)s, %(salary_max)s,
                    %(job_type)s, %(experience_level)s, %(posted_date)s, %(source)s, %(fingerprint)s, %(search_id)s, %(url)s)
            ON CONFLICT (fingerprint) DO UPDATE
                SET search_id = EXCLUDED.search_id,
                    url = COALESCE(EXCLUDED.url, jobs.url),
                    last_seen = NOW(),
                    status = 'active'    -- it showed up again, so it is live
            RETURNING (xmax = 0) AS is_new
        """, {**j, "search_id": search_id})
        row = cur.fetchone()
        if row and row[0]:
            inserted += 1
    conn.commit()
    cur.close()
    conn.close()
    skipped = len(jobs) - inserted
    return inserted, skipped


def record_task_status(search_id, source, worker_id, fetched, inserted, error=None):
    """Record that a worker finished a (search_id, source) task, even if it failed.
    error is None on success, or a short message on failure. Idempotent."""
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO task_status (search_id, source, worker_id, fetched, inserted, error)
        VALUES (%s, %s, %s, %s, %s, %s)
        ON CONFLICT (search_id, source) DO UPDATE
        SET worker_id = EXCLUDED.worker_id,
            fetched = EXCLUDED.fetched,
            inserted = EXCLUDED.inserted,
            error = EXCLUDED.error,
            finished_at = NOW()
    """, (search_id, source, worker_id, fetched, inserted, error))
    conn.commit()
    cur.close()
    conn.close()


# ---------------------------------------------------------------------------
# Freshness (phase 2, weeks 7-8)
# ---------------------------------------------------------------------------

# A job that has not appeared in any crawl for this long is treated as gone.
EXPIRE_AFTER_MINUTES = int(os.getenv("EXPIRE_AFTER_MINUTES", str(48 * 60)))


def expire_stale_jobs(source=None, older_than_minutes=None):
    """Mark active jobs that stopped showing up in crawls as expired.

    Crawls refresh last_seen for every listing they still find, so a listing
    whose last_seen has fallen behind is one the source no longer lists.
    Returns how many jobs were expired.
    """
    minutes = older_than_minutes or EXPIRE_AFTER_MINUTES
    conn = get_db_connection()
    cur = conn.cursor()
    sql = """
        UPDATE jobs
        SET status = 'expired'
        WHERE status = 'active'
          AND last_seen < NOW() - (%s * INTERVAL '1 minute')
    """
    params = [minutes]
    if source:
        sql += " AND source = %s"
        params.append(source)
    cur.execute(sql, params)
    expired = cur.rowcount
    conn.commit()
    cur.close()
    conn.close()
    return expired


def freshness_summary():
    """Counts per source and status, for checking how fresh the data is."""
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT source, status, COUNT(*),
               MIN(first_seen)::date, MAX(last_seen)
        FROM jobs GROUP BY source, status ORDER BY source, status
    """)
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return rows
