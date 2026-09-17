import requests
from db_utils import make_fingerprint
from adapters.base import SourceAdapter, matches_keyword


class RemoteOKAdapter(SourceAdapter):
    name = "remoteok"
    requests_per_minute = 10   # single public feed; no need to hit it often

    def fetch(self, keyword=None, location=None):
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
            if not matches_keyword(keyword, title, " ".join(tags)):
                continue
            jobs.append({
                "title": title, "company": company, "location": loc, "skills": skills,
                "salary_min": item.get("salary_min"), "salary_max": item.get("salary_max"),
                "job_type": "remote", "experience_level": None,
                "posted_date": (item.get("date") or "")[:10] or None,
                "source": "remoteok", "fingerprint": make_fingerprint(title, company, loc),
                "url": item.get("url") or item.get("apply_url"),
            })
        return jobs
