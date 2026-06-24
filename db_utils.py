import os
import hashlib
import psycopg2
from dotenv import load_dotenv

load_dotenv()

DB_CONFIG = {
    "host": os.getenv("DB_HOST"),
    "port": os.getenv("DB_PORT"),
    "dbname": os.getenv("DB_NAME"),
    "user": os.getenv("DB_USER"),
    "password": os.getenv("DB_PASSWORD"),
}


def make_fingerprint(title, company, location):
    """Deterministic dedup key from title + company + location."""
    raw = f"{(title or '').strip().lower()}|{(company or '').strip().lower()}|{(location or '').strip().lower()}"
    return hashlib.sha256(raw.encode()).hexdigest()


def save_jobs(jobs, search_id):
    """Insert jobs into Postgres. ON CONFLICT updates search_id so the latest
    search that matched a job can find it. Returns (inserted_count, skipped_count)."""
    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor()
    inserted = 0
    for j in jobs:
        cur.execute("""
            INSERT INTO jobs (title, company, location, skills, salary_min, salary_max,
                              job_type, experience_level, posted_date, source, fingerprint, search_id)
            VALUES (%(title)s, %(company)s, %(location)s, %(skills)s, %(salary_min)s, %(salary_max)s,
                    %(job_type)s, %(experience_level)s, %(posted_date)s, %(source)s, %(fingerprint)s, %(search_id)s)
            ON CONFLICT (fingerprint) DO UPDATE SET search_id = EXCLUDED.search_id
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


def record_task_status(search_id, source, worker_id, fetched, inserted):
    """Record that a worker finished a (search_id, source) task. Idempotent."""
    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO task_status (search_id, source, worker_id, fetched, inserted)
        VALUES (%s, %s, %s, %s, %s)
        ON CONFLICT (search_id, source) DO UPDATE
        SET worker_id = EXCLUDED.worker_id,
            fetched = EXCLUDED.fetched,
            inserted = EXCLUDED.inserted,
            finished_at = NOW()
    """, (search_id, source, worker_id, fetched, inserted))
    conn.commit()
    cur.close()
    conn.close()
