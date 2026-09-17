"""Continuous crawling (Phase 2, weeks 3-4).

Instead of waiting for someone to search, this publishes crawl tasks into
the same task_queue the workers already read. Nothing about the workers,
the adapters or the database changes: they see ordinary tasks.

Each source is scheduled on its own, so a slow/fragile source can be
crawled less often than a fast API. How often a source may be called comes
from its adapter's requests_per_minute, which is already defined in
adapters/base.py and in each adapter file.

Run it:
    python scheduler.py          # keep crawling on a schedule
    python scheduler.py --once   # publish one round now and exit (for testing)
"""
import os
import sys
import json
import time
import uuid
from datetime import datetime, timedelta

import pika
from dotenv import load_dotenv
from apscheduler.schedulers.background import BackgroundScheduler

from connections import get_rabbit_connection
from adapters import all_sources, get_adapter

load_dotenv()

TASK_QUEUE = "task_queue"

# The searches to keep up to date. Add or remove lines as you like.
CRAWLS = [
    {"keyword": "python developer", "location": "Seattle"},
    {"keyword": "data engineer", "location": "New York"},
]

# How often we would LIKE to crawl each source (minutes).
# A source's own rate limit can stretch this, never shrink it.
CRAWL_INTERVAL_MINUTES = int(os.getenv("CRAWL_INTERVAL_MINUTES", "15"))


def seconds_between_crawls(source):
    """Smallest safe gap between two crawls of this source, in seconds.

    One crawl of a source costs len(CRAWLS) requests to that site. If the
    adapter allows requests_per_minute requests a minute, those requests
    need at least len(CRAWLS) * 60 / requests_per_minute seconds. We take
    whichever is longer: our preferred interval, or the safe minimum.
    """
    adapter = get_adapter(source)
    rpm = getattr(adapter, "requests_per_minute", 30) or 30
    rate_limit_seconds = len(CRAWLS) * 60.0 / rpm
    preferred_seconds = CRAWL_INTERVAL_MINUTES * 60
    return max(preferred_seconds, rate_limit_seconds)


def publish_crawl(source):
    """Publish one task per search for this source. Called by the scheduler."""
    search_id = f"crawl-{uuid.uuid4().hex[:8]}"
    conn = get_rabbit_connection()
    ch = conn.channel()
    ch.queue_declare(queue=TASK_QUEUE, durable=True)
    for crawl in CRAWLS:
        task = {
            "source": source,
            "keyword": crawl["keyword"],
            "location": crawl["location"],
            "search_id": search_id,
            "crawl": True,
        }
        ch.basic_publish(
            exchange="", routing_key=TASK_QUEUE, body=json.dumps(task),
            properties=pika.BasicProperties(delivery_mode=2),
        )
    conn.close()
    print(f"[scheduler] published {len(CRAWLS)} task(s) for {source} "
          f"(search_id={search_id})", flush=True)


def main():
    sources = all_sources()
    if not sources:
        print("[scheduler] no sources registered, nothing to crawl.")
        return

    run_once = "--once" in sys.argv

    if run_once:
        for source in sources:
            publish_crawl(source)
        print("[scheduler] one round published, exiting.")
        return

    # Background (not blocking) so the main thread can sleep in short steps.
    # On Windows a blocking scheduler swallows Ctrl+C; this way it stops.
    scheduler = BackgroundScheduler()
    for position, source in enumerate(sources):
        gap = seconds_between_crawls(source)
        # Stagger the first run so the sources don't all fire at once
        first_run = datetime.now() + timedelta(seconds=10 * position)
        scheduler.add_job(
            publish_crawl, "interval", seconds=gap, args=[source],
            id=f"crawl-{source}", next_run_time=first_run, max_instances=1,
            coalesce=True,
        )
        print(f"[scheduler] {source}: every {gap / 60:.1f} min "
              f"({len(CRAWLS)} search(es) per crawl), first run at "
              f"{first_run.strftime('%H:%M:%S')}")

    print("[scheduler] started. Press CTRL+C to stop.", flush=True)
    scheduler.start()
    try:
        while True:
            time.sleep(1)
    except (KeyboardInterrupt, SystemExit):
        print("\n[scheduler] stopping...")
    finally:
        scheduler.shutdown(wait=False)
        print("[scheduler] stopped.")


if __name__ == "__main__":
    main()
