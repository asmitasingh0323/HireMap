"""One-off backfill: apply the title rule to jobs already interpreted.

Seniority used to come from the model. It now comes from the job title
(see interpreter.seniority_from_title), so rows interpreted before that
change still hold the model's answer. Re-running the model on all of them
would take an hour and would only change this one field, so this script
recomputes seniority directly instead. Skills and salary are untouched.

    python backfill_seniority.py            # show what would change
    python backfill_seniority.py --apply    # write the changes
"""
import sys

from db_utils import get_db_connection
from title_rules import seniority_from_title

APPLY = "--apply" in sys.argv


def main():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT fingerprint, title, seniority
        FROM jobs
        WHERE interpreted_at IS NOT NULL
    """)
    rows = cur.fetchall()

    changes = []
    for fingerprint, title, stored in rows:
        stated = seniority_from_title(title)
        if stated and stated != stored:
            changes.append((fingerprint, title, stored, stated))

    print(f"\n{len(rows)} interpreted jobs, {len(changes)} need correcting")
    print("=" * 70)
    for _, title, stored, stated in changes[:25]:
        print(f"  {stored:<8} -> {stated:<8} {title[:50]}")
    if len(changes) > 25:
        print(f"  ... and {len(changes) - 25} more")

    if not changes:
        cur.close()
        conn.close()
        return

    if not APPLY:
        print("\nPreview only. Run with --apply to write these changes.")
        cur.close()
        conn.close()
        return

    for fingerprint, _, _, stated in changes:
        cur.execute(
            "UPDATE jobs SET seniority = %s WHERE fingerprint = %s",
            (stated, fingerprint))
    conn.commit()
    print(f"\nUpdated {len(changes)} jobs.")
    cur.close()
    conn.close()


if __name__ == "__main__":
    main()
