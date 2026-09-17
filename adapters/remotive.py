import requests
from db_utils import make_fingerprint
from adapters.base import SourceAdapter, matches_keyword


class RemotiveAdapter(SourceAdapter):
    """Remotive: a free JSON feed of remote jobs, no API key needed.
    Docs: https://remotive.com/api/remote-jobs
    """
    name = "remotive"
    requests_per_minute = 10   # public feed, be polite

    def fetch(self, keyword=None, location=None, max_results=20):
        url = "https://remotive.com/api/remote-jobs"
        params = {"limit": max_results}
        if keyword:
            params["search"] = keyword
        headers = {"User-Agent": "Mozilla/5.0 (HireMap project)"}
        resp = requests.get(url, params=params, headers=headers, timeout=15)
        resp.raise_for_status()

        jobs = []
        for item in resp.json().get("jobs", []):
            title = item.get("title")
            company = item.get("company_name")
            loc = item.get("candidate_required_location") or "Remote"
            tags = item.get("tags") or []
            skills = ", ".join(tags) if tags else None

            # Remotive's own search is loose, so apply the same word rule
            # the other feed-style sources use.
            if not matches_keyword(keyword, title, " ".join(tags)):
                continue

            jobs.append({
                "title": title, "company": company, "location": loc,
                "skills": skills, "salary_min": None, "salary_max": None,
                "job_type": item.get("job_type") or "remote",
                "experience_level": None,
                "posted_date": (item.get("publication_date") or "")[:10] or None,
                "source": "remotive",
                "fingerprint": make_fingerprint(title, company, loc),
                "url": item.get("url"),
            })
        return jobs
