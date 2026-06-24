import os
import hashlib
import requests
import psycopg2
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

ADZUNA_APP_ID = os.getenv("ADZUNA_APP_ID")
ADZUNA_APP_KEY = os.getenv("ADZUNA_APP_KEY")

DB_CONFIG = {
    "host": os.getenv("DB_HOST"),
    "port": os.getenv("DB_PORT"),
    "dbname": os.getenv("DB_NAME"),
    "user": os.getenv("DB_USER"),
    "password": os.getenv("DB_PASSWORD"),
}


def make_fingerprint(title, company, location):
    """Deterministic fingerprint from title + company + location (your dedup key)."""
    raw = f"{(title or '').strip().lower()}|{(company or '').strip().lower()}|{(location or '').strip().lower()}"
    return hashlib.sha256(raw.encode()).hexdigest()


def fetch_adzuna(keyword, location, max_results=20):
    """Call the Adzuna REST API and return a list of normalized job dicts."""
    url = "https://api.adzuna.com/v1/api/jobs/us/search/1"
    params = {
        "app_id": ADZUNA_APP_ID,
        "app_key": ADZUNA_APP_KEY,
        "what": keyword,
        "where": location,
        "results_per_page": max_results,
        "max_days_old": 7,
        "content-type": "application/json",
    }
    resp = requests.get(url, params=params, timeout=15)
    print(f"  [debug] Adzuna status code: {resp.status_code}")
    if resp.status_code != 200:
        print(f"  [debug] Adzuna response: {resp.text[:500]}")
        resp.raise_for_status()
    data = resp.json()
    print(
        f"  [debug] Adzuna returned {len(data.get('results', []))} raw results, total count: {data.get('count')}")

    jobs = []
    for item in data.get("results", []):
        title = item.get("title")
        company = (item.get("company") or {}).get("display_name")
        loc = (item.get("location") or {}).get("display_name")
        jobs.append({
            "title": title,
            "company": company,
            "location": loc,
            "skills": None,
            "salary_min": item.get("salary_min"),
            "salary_max": item.get("salary_max"),
            "job_type": item.get("contract_time"),
            "experience_level": None,
            "posted_date": (item.get("created") or "")[:10] or None,
            "source": "adzuna",
            "fingerprint": make_fingerprint(title, company, loc),
        })
    return jobs


def save_jobs(jobs, search_id="manual_test"):
    """Insert jobs into Postgres. ON CONFLICT DO NOTHING handles deduplication."""
    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor()
    inserted = 0
    for j in jobs:
        cur.execute("""
            INSERT INTO jobs (title, company, location, skills, salary_min, salary_max,
                              job_type, experience_level, posted_date, source, fingerprint, search_id)
            VALUES (%(title)s, %(company)s, %(location)s, %(skills)s, %(salary_min)s, %(salary_max)s,
                    %(job_type)s, %(experience_level)s, %(posted_date)s, %(source)s, %(fingerprint)s, %(search_id)s)
            ON CONFLICT (fingerprint) DO NOTHING
        """, {**j, "search_id": search_id})
        inserted += cur.rowcount
    conn.commit()
    cur.close()
    conn.close()
    return inserted


if __name__ == "__main__":
    keyword = "software developer"
    location = "Bellevue"
    print(f"Fetching Adzuna jobs for '{keyword}' in '{location}'...")
    jobs = fetch_adzuna(keyword, location)
    print(f"Fetched {len(jobs)} jobs from Adzuna.")
    inserted = save_jobs(jobs)
    print(f"Inserted {inserted} new jobs (duplicates skipped by ON CONFLICT).")
