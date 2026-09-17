import datetime
import requests
from db_utils import make_fingerprint
from adapters.base import SourceAdapter, matches_keyword


class ArbeitnowAdapter(SourceAdapter):
    """Arbeitnow: a free job-board feed, no API key needed.
    Docs: https://documenter.getpostman.com/view/18545278/UVJbJdKh
    The feed has no search parameter, so it returns one page of recent jobs
    and we filter locally with the shared keyword rule.
    """
    name = "arbeitnow"
    requests_per_minute = 10   # public feed, be polite

    def fetch(self, keyword=None, location=None, max_results=20):
        url = "https://www.arbeitnow.com/api/job-board-api"
        headers = {"User-Agent": "Mozilla/5.0 (HireMap project)"}
        resp = requests.get(url, headers=headers, timeout=15)
        resp.raise_for_status()

        jobs = []
        for item in resp.json().get("data", []):
            title = item.get("title")
            company = item.get("company_name")
            loc = item.get("location") or ("Remote" if item.get("remote") else None)
            tags = item.get("tags") or []
            job_types = item.get("job_types") or []
            skills = ", ".join(tags) if tags else None

            if not matches_keyword(keyword, title, " ".join(tags)):
                continue

            # created_at is a unix timestamp (seconds)
            posted_date = None
            created_at = item.get("created_at")
            if created_at:
                try:
                    posted_date = datetime.date.fromtimestamp(
                        int(created_at)).isoformat()
                except (ValueError, OSError, TypeError):
                    posted_date = None

            jobs.append({
                "title": title, "company": company, "location": loc,
                "skills": skills, "salary_min": None, "salary_max": None,
                "job_type": (job_types[0] if job_types
                             else ("remote" if item.get("remote") else None)),
                "experience_level": None,
                "posted_date": posted_date,
                "source": "arbeitnow",
                "fingerprint": make_fingerprint(title, company, loc),
                "url": item.get("url"),
            })
            if len(jobs) >= max_results:
                break
        return jobs
