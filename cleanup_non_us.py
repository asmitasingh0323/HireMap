"""Remove stored jobs that don't belong in a US, English-language dataset.

Uses the same rules the adapters apply to new jobs (is_us_location and
looks_english), so old rows match what new crawls store.

    python cleanup_non_us.py            # preview only, deletes nothing
    python cleanup_non_us.py --delete   # actually delete
"""
import sys
from collections import Counter

from adapters.base import is_us_location, looks_english
from db_utils import get_db_connection


def main():
    really_delete = "--delete" in sys.argv

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT fingerprint, source, title, location, description "
                "FROM jobs")
    rows = cur.fetchall()

    doomed = []
    for fingerprint, source, title, location, description in rows:
        if not is_us_location(location):
            doomed.append((fingerprint, source, title, location, "not US"))
        elif not looks_english(title, description):
            doomed.append((fingerprint, source, title, location, "not English"))

    print(f"{len(rows)} jobs stored, {len(doomed)} would be removed.\n")
    if not doomed:
        cur.close()
        conn.close()
        return

    print("Why:")
    for reason, count in Counter(d[4] for d in doomed).most_common():
        print(f"  {reason:<12} {count}")

    print("\nBy source:")
    for source, count in Counter(d[1] for d in doomed).most_common():
        print(f"  {source:<16} {count}")

    print("\nExamples:")
    for _, source, title, location, reason in doomed[:12]:
        print(f"  [{reason:<11}] {source:<12} {title[:45]:<45} | {location}")

    if not really_delete:
        print("\nPreview only. Re-run with --delete to remove these rows.")
        cur.close()
        conn.close()
        return

    cur.executemany("DELETE FROM jobs WHERE fingerprint = %s",
                    [(d[0],) for d in doomed])
    conn.commit()
    print(f"\nDeleted {len(doomed)} jobs.")
    cur.close()
    conn.close()


if __name__ == "__main__":
    main()
