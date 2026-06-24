import os
import hashlib
import requests
import psycopg2
from bs4 import BeautifulSoup
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


def fetch_wwr(keyword="python"):
    """Scrape WeWorkRemotely programming jobs and normalize into our schema."""
    url = f"https://weworkremotely.com/remote-jobs/search?term={keyword}"
    headers = {"User-Agent": "Mozilla/5.0 (HireMap project)"}
    resp = requests.get(url, headers=headers, timeout=15)
    print(f"  [debug] WWR status code: {resp.status_code}")
    resp.raise_for_status()

    soup = BeautifulSoup(resp.text, "html.parser")
    jobs = []

    # WWR job listings: each is an <li class="new-listing-container">
    for li in soup.select("li.new-listing-container"):
        title_el = li.select_one("span.new-listing__header__title__text")
        company_el = li.select_one("p.new-listing__company-name")
        region_el = li.select_one("p.new-listing__company-headquarters")
        if not title_el:
            continue
        title = title_el.get_text(strip=True)
        company = company_el.get_text(strip=True) if company_el else None
        loc = region_el.get_text(strip=True) if region_el else "Remote"
        jobs.append({
            "title": title,
            "company": company,
            "location": loc,
            "skills": None,
            "salary_min": None,
            "salary_max": None,
            "job_type": "remote",
            "experience_level": None,
            "posted_date": None,
            "source": "weworkremotely",
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
    print(f"Scraping WeWorkRemotely for '{keyword}'...")
    jobs = fetch_wwr(keyword)
    print(f"Scraped {len(jobs)} jobs from WeWorkRemotely.")
    inserted = save_jobs(jobs)
    print(f"Inserted {inserted} new jobs (duplicates skipped by ON CONFLICT).")
