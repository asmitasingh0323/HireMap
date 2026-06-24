import os
import hashlib
import requests
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
    raw = f"{(title or '').strip().lower()}|{(company or '').strip().lower()}|{(location or '').strip().lower()}"
    return hashlib.sha256(raw.encode()).hexdigest()


def fetch_remoteok(keyword=None):
    """Fetch the RemoteOK public JSON feed and normalize into our schema."""
    url = "https://remoteok.com/api"
    headers = {"User-Agent": "Mozilla/5.0 (HireMap project)"}
    resp = requests.get(url, headers=headers, timeout=15)
    print(f"  [debug] RemoteOK status code: {resp.status_code}")
    resp.raise_for_status()
    data = resp.json()

    # First element is metadata/legal notice, skip it
    listings = data[1:] if data and isinstance(
        data[0], dict) and "legal" in data[0] else data

    jobs = []
    for item in listings:
        title = item.get("position") or item.get("title")
        company = item.get("company")
        loc = item.get("location") or "Remote"
        tags = item.get("tags", []) or []
        skills = ", ".join(tags) if tags else None
        # Match keyword against title OR tags (skills), since RemoteOK stores skills in tags
        if keyword:
            haystack = (title or "").lower() + " " + " ".join(tags).lower()
            if keyword.lower() not in haystack:
                continue
        jobs.append({
            "title": title,
            "company": company,
            "location": loc,
            "skills": skills,
            "salary_min": item.get("salary_min"),
            "salary_max": item.get("salary_max"),
            "job_type": "remote",
            "experience_level": None,
            "posted_date": (item.get("date") or "")[:10] or None,
            "source": "remoteok",
            "fingerprint": make_fingerprint(title, company, loc),
        })
    return jobs


def save_jobs(jobs, search_id="manual_test"):
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
    keyword = "python"
    print(f"Fetching RemoteOK jobs matching '{keyword}'...")
    jobs = fetch_remoteok(keyword)
    print(f"Fetched {len(jobs)} jobs from RemoteOK.")
    inserted = save_jobs(jobs)
    print(f"Inserted {inserted} new jobs (duplicates skipped by ON CONFLICT).")
