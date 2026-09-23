"""Interpretation quality check (phase 2, weeks 9-10).

Shows a random sample of interpreted jobs next to their descriptions and
asks you to judge each field. Your answers are saved to a CSV, and the
accuracy is printed at the end. That number is the quality baseline the
later weeks try to improve.

    python eval_interpretation.py 20     # judge 20 jobs (default 10)

For each job answer y (correct), n (wrong) or s (skip / unclear).
"""
import csv
import os
import sys
import datetime

from db_utils import get_db_connection

RESULTS_FILE = "interpretation_eval.csv"
DESCRIPTION_PREVIEW = 1200


def sample_interpreted_jobs(limit):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT fingerprint, source, title, company, location,
               extracted_skills, seniority, work_arrangement,
               interpretation_model, description
        FROM jobs
        WHERE interpreted_at IS NOT NULL AND description IS NOT NULL
        ORDER BY RANDOM() LIMIT %s
    """, (limit,))
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return rows


def ask(question):
    while True:
        answer = input(f"    {question} [y/n/s]: ").strip().lower()
        if answer in ("y", "n", "s"):
            return answer
        print("    please type y, n or s")


def main():
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else 10
    jobs = sample_interpreted_jobs(limit)
    if not jobs:
        print("No interpreted jobs yet. Run the interpretation first.")
        return

    judged = []
    print(f"\nJudging {len(jobs)} jobs. Read the description, then answer.\n")

    for number, job in enumerate(jobs, start=1):
        (fingerprint, source, title, company, location,
         skills, seniority, arrangement, model, description) = job

        print("=" * 70)
        print(f"[{number}/{len(jobs)}] {title} @ {company} ({source})")
        print(f"Location as listed: {location}")
        print("-" * 70)
        print(description[:DESCRIPTION_PREVIEW])
        if len(description) > DESCRIPTION_PREVIEW:
            print("... (description truncated)")
        print("-" * 70)
        print(f"MODEL SAID  skills     : {skills or '(none)'}")
        print(f"            seniority  : {seniority}")
        print(f"            arrangement: {arrangement}")
        print()

        judged.append({
            "fingerprint": fingerprint,
            "source": source,
            "title": title,
            "model": model,
            "skills_ok": ask("Are the skills right?"),
            "seniority_ok": ask("Is the seniority right?"),
            "arrangement_ok": ask("Is remote/hybrid/onsite right?"),
        })
        print()

    # Save, appending so several sessions build one record
    write_header = not os.path.exists(RESULTS_FILE)
    with open(RESULTS_FILE, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "checked_at", "fingerprint", "source", "title", "model",
            "skills_ok", "seniority_ok", "arrangement_ok"])
        if write_header:
            writer.writeheader()
        now = datetime.datetime.now().isoformat(timespec="seconds")
        for row in judged:
            writer.writerow({"checked_at": now, **row})

    print("=" * 70)
    print(f"Results for this session ({len(judged)} jobs):")
    for field, label in (("skills_ok", "skills"),
                         ("seniority_ok", "seniority"),
                         ("arrangement_ok", "work arrangement")):
        yes = sum(1 for r in judged if r[field] == "y")
        no = sum(1 for r in judged if r[field] == "n")
        skipped = sum(1 for r in judged if r[field] == "s")
        total = yes + no
        rate = f"{100 * yes / total:.0f}%" if total else "n/a"
        print(f"  {label:<18} correct {yes}/{total} ({rate})"
              f"{f', {skipped} skipped' if skipped else ''}")
    print(f"\nSaved to {RESULTS_FILE}")


if __name__ == "__main__":
    main()
