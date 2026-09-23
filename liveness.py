"""Liveness checking (phase 2, weeks 7-8, rate-limit aware).

Freshness has two levels in HireMap:

1. Crawl-based (db_utils.expire_stale_jobs): a listing that stops appearing
   in crawls is retired. Costs no extra requests.
2. This file: for listings that carry a link, ask the site whether that page
   still exists. Catches a job that was taken down but is still listed in a
   feed, which the crawl-based rule cannot see.

Checks are spaced using each adapter's requests_per_minute, the same limit
the crawler respects, so verifying old listings never hammers a source.
"""
import time

import requests

from adapters.base import get_adapter

HEADERS = {"User-Agent": "Mozilla/5.0 (HireMap project)"}
TIMEOUT = 12

# A page that answers with one of these is gone for good.
GONE_CODES = {404, 410}


def seconds_between_checks(source):
    """Polite gap between two requests to this source, from its adapter."""
    adapter = get_adapter(source)
    rpm = getattr(adapter, "requests_per_minute", 30) or 30
    return 60.0 / rpm


def check_url(url):
    """Is this job page still there?

    Returns (verdict, status_code) where verdict is:
      "live"    - the page answers normally
      "gone"    - the page is a 404/410, so the listing was taken down
      "unknown" - blocked, redirected to a login, timed out, or refused
    A site that blocks automated requests must never look like a dead job,
    so anything unclear stays "unknown" and the listing is left alone.
    """
    if not url:
        return "unknown", None
    try:
        resp = requests.head(url, headers=HEADERS, timeout=TIMEOUT,
                             allow_redirects=True)
        # Some servers refuse HEAD; retry those with a normal request
        if resp.status_code in (403, 405, 501):
            resp = requests.get(url, headers=HEADERS, timeout=TIMEOUT,
                                allow_redirects=True, stream=True)
            resp.close()
    except requests.exceptions.RequestException:
        return "unknown", None

    if resp.status_code in GONE_CODES:
        return "gone", resp.status_code
    if resp.status_code < 400:
        return "live", resp.status_code
    return "unknown", resp.status_code


def check_jobs(jobs, source, on_result=None):
    """Check a batch of jobs for one source, spaced by its rate limit.

    Returns (live, gone, unknown). on_result(job, verdict, code) is called
    per job so the caller can store the outcome.
    """
    gap = seconds_between_checks(source)
    live = gone = unknown = 0

    for position, job in enumerate(jobs):
        if position:                      # no wait before the first request
            time.sleep(gap)
        verdict, code = check_url(job.get("url"))
        if verdict == "live":
            live += 1
        elif verdict == "gone":
            gone += 1
        else:
            unknown += 1
        if on_result:
            on_result(job, verdict, code)

    return live, gone, unknown
