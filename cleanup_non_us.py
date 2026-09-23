"""Remove stored jobs that are not workable from the United States.

Uses the same is_us_location() rule the adapters now apply, so old rows
match what new crawls store. Shows what it would delete first.

    python cleanup_non_us.py            # preview only, deletes nothing
    python cleanup_non_us.py --delete   # actually delete
"""
import sys
from collections import Counter

from adapters.base import is_us_location
from db_utils import get_db_connection


def main():
    really_delete = "--delete" in sys.argv

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT fingerprint, source, location FROM jobs")
    rows = cur.fetchall()

    non_us = [(fingerprint, source, location) for fingerprint, source, location
              in rows if not is_us_location(location)]

    print(f"{len(rows)} jobs stored, {len(non_us)} look non-US.\n")
    if not non_us:
        cur.close()
        conn.close()
        return

    print("By source:")
    for source, count in Counter(s for _, s, _ in non_us).most_common():
        print(f"  {source:<16} {count}")

    print("\nMost common locations that would go:")
    for location, count in Counter(l for _, _, l in non_us).most_common(15):
        print(f"  {count:>4}  {location}")

    if not really_delete:
        print("\nPreview only. Re-run with --delete to remove these rows.")
        cur.close()
        conn.close()
        return

    cur.executemany("DELETE FROM jobs WHERE fingerprint = %s",
                    [(fingerprint,) for fingerprint, _, _ in non_us])
    conn.commit()
    print(f"\nDeleted {len(non_us)} non-US jobs.")
    cur.close()
    conn.close()


if __name__ == "__main__":
    main()
