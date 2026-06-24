import os
import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from db_utils import make_fingerprint
import time
load_dotenv()

ADZUNA_APP_ID = os.getenv("ADZUNA_APP_ID")
ADZUNA_APP_KEY = os.getenv("ADZUNA_APP_KEY")


def fetch_adzuna(keyword, location, max_results=20):
    url = "https://api.adzuna.com/v1/api/jobs/us/search/1"
    params = {
        "app_id": ADZUNA_APP_ID, "app_key": ADZUNA_APP_KEY,
        "what": keyword, "where": location,
        "results_per_page": max_results, "max_days_old": 7,
        "content-type": "application/json",
    }
    resp = requests.get(url, params=params, timeout=15)
    resp.raise_for_status()
    jobs = []
    for item in resp.json().get("results", []):
        title = item.get("title")
        company = (item.get("company") or {}).get("display_name")
        loc = (item.get("location") or {}).get("display_name")
        jobs.append({
            "title": title, "company": company, "location": loc, "skills": None,
            "salary_min": item.get("salary_min"), "salary_max": item.get("salary_max"),
            "job_type": item.get("contract_time"), "experience_level": None,
            "posted_date": (item.get("created") or "")[:10] or None,
            "source": "adzuna", "fingerprint": make_fingerprint(title, company, loc),
        })
    return jobs


def fetch_remoteok(keyword=None, location=None):
    url = "https://remoteok.com/api"
    headers = {"User-Agent": "Mozilla/5.0 (HireMap project)"}
    resp = requests.get(url, headers=headers, timeout=15)
    resp.raise_for_status()
    data = resp.json()
    listings = data[1:] if data and isinstance(
        data[0], dict) and "legal" in data[0] else data
    jobs = []
    for item in listings:
        title = item.get("position") or item.get("title")
        company = item.get("company")
        loc = item.get("location") or "Remote"
        tags = item.get("tags", []) or []
        skills = ", ".join(tags) if tags else None
        if keyword:
            haystack = (title or "").lower() + " " + " ".join(tags).lower()
            if keyword.lower() not in haystack:
                continue
        jobs.append({
            "title": title, "company": company, "location": loc, "skills": skills,
            "salary_min": item.get("salary_min"), "salary_max": item.get("salary_max"),
            "job_type": "remote", "experience_level": None,
            "posted_date": (item.get("date") or "")[:10] or None,
            "source": "remoteok", "fingerprint": make_fingerprint(title, company, loc),
        })
    return jobs


def fetch_wwr(keyword="python", location=None):
    url = f"https://weworkremotely.com/remote-jobs/search?term={keyword}"
    headers = {"User-Agent": "Mozilla/5.0 (HireMap project)"}
    resp = requests.get(url, headers=headers, timeout=15)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")
    jobs = []
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
            "title": title, "company": company, "location": loc, "skills": None,
            "salary_min": None, "salary_max": None, "job_type": "remote",
            "experience_level": None, "posted_date": None,
            "source": "weworkremotely", "fingerprint": make_fingerprint(title, company, loc),
        })
    return jobs


def fetch_slow_test(keyword=None, location=None):
    """A deliberately slow fake source for testing fault recovery.
    Sleeps long enough that you can kill the worker mid-task."""
    print("  [slow_test] sleeping 15s to simulate a long fetch...")
    time.sleep(15)
    return [{
        "title": f"Test Job for {keyword}", "company": "TestCorp",
        "location": location or "Nowhere", "skills": None,
        "salary_min": None, "salary_max": None, "job_type": "test",
        "experience_level": None, "posted_date": None,
        "source": "slow_test",
        "fingerprint": make_fingerprint(f"Test Job for {keyword}", "TestCorp", location or "Nowhere"),
    }]


# Maps a source name to its fetch function — workers use this to know what to run
FETCHERS = {
    "adzuna": fetch_adzuna,
    "remoteok": fetch_remoteok,
    "weworkremotely": fetch_wwr,
    "slow_test": fetch_slow_test,
}
