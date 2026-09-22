import os
import requests
from dotenv import load_dotenv
from db_utils import make_fingerprint
from adapters.base import SourceAdapter

load_dotenv()


class AdzunaAdapter(SourceAdapter):
    name = "adzuna"
    requests_per_minute = 25   # Adzuna free tier is limited; stay polite

    def fetch(self, keyword=None, location=None, max_results=20):
        url = "https://api.adzuna.com/v1/api/jobs/us/search/1"
        params = {
            "app_id": os.getenv("ADZUNA_APP_ID"),
            "app_key": os.getenv("ADZUNA_APP_KEY"),
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
                "url": item.get("redirect_url"),
                # Adzuna returns a short teaser, not the full posting
                "description": item.get("description"),
            })
        return jobs
