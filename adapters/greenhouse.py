import os
import requests
from adapters.base import SourceAdapter, matches_keyword

# Greenhouse has no global feed: each company has its own board, named by a
# "board token" (the name in its careers URL, e.g. job-boards.greenhouse.io/figma).
# Add or remove companies here, or set GREENHOUSE_COMPANIES="figma,stripe" to
# override without editing the file.
DEFAULT_COMPANIES = [
    "figma",
    "stripe",
    "discord",
    "airtable",
    "databricks",
]


class GreenhouseAdapter(SourceAdapter):
    """Greenhouse job boards: one request per company, not one per source.

    This is the first source of a different shape, so it is the real test of
    the adapter design. Everything company-specific stays in this file; the
    workers and the scheduler treat it like any other source.
    """
    name = "greenhouse"
    # One crawl makes one request PER COMPANY, so keep this modest.
    requests_per_minute = 5

    @property
    def companies(self):
        configured = os.getenv("GREENHOUSE_COMPANIES")
        if configured:
            return [c.strip() for c in configured.split(",") if c.strip()]
        return DEFAULT_COMPANIES

    def fetch(self, keyword=None, location=None, max_results=50):
        headers = {"User-Agent": "Mozilla/5.0 (HireMap project)"}
        jobs = []
        # Share the limit out, so a company with hundreds of openings cannot
        # use up the whole budget and hide the other companies.
        per_company = max(1, max_results // max(1, len(self.companies)))

        for company in self.companies:
            taken_here = 0
            url = f"https://boards-api.greenhouse.io/v1/boards/{company}/jobs"
            try:
                resp = requests.get(url, headers=headers, timeout=15)
                resp.raise_for_status()
                board = resp.json()
            except Exception as e:
                # One company being unreachable must not lose the others:
                # the same isolation rule the sources follow.
                print(f"  [greenhouse] skipped '{company}': "
                      f"{str(e).split(' for url:')[0]}")
                continue

            for item in board.get("jobs", []):
                if taken_here >= per_company:
                    break
                title = item.get("title")
                loc = (item.get("location") or {}).get("name")

                if not matches_keyword(keyword, title):
                    continue

                jobs.append({
                    "title": title,
                    "company": company,
                    "location": loc,
                    "skills": None,
                    "salary_min": None, "salary_max": None,
                    "job_type": None, "experience_level": None,
                    "posted_date": (item.get("updated_at") or "")[:10] or None,
                    "source": "greenhouse",
                    "url": item.get("absolute_url"),
                })
                taken_here += 1
                if len(jobs) >= max_results:
                    return jobs
        return jobs
