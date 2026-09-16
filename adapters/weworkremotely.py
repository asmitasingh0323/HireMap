import requests
from bs4 import BeautifulSoup
from db_utils import make_fingerprint
from adapters.base import SourceAdapter


class WeWorkRemotelyAdapter(SourceAdapter):
    name = "weworkremotely"
    requests_per_minute = 6    # we scrape their HTML, so be extra polite

    def fetch(self, keyword="python", location=None):
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
            link_el = li.select_one(
                "a.listing-link--unlocked") or li.find("a", href=True)
            job_url = ("https://weworkremotely.com" +
                       link_el["href"]) if link_el and link_el.get("href") else None
            jobs.append({
                "title": title, "company": company, "location": loc, "skills": None,
                "salary_min": None, "salary_max": None, "job_type": "remote",
                "experience_level": None, "posted_date": None,
                "source": "weworkremotely", "fingerprint": make_fingerprint(title, company, loc),
                "url": job_url,
            })
        return jobs
