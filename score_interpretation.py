"""Automatic interpretation quality score (phase 2).

Hand-judging is slow, so this measures three things without a human:

1. Skill grounding - what share of the skills the model listed actually
   appear in the description. Low grounding means the model is inventing
   skills, which is the failure that matters most.
2. Seniority agreement - compared against a plain keyword rule read from
   the description ("intern", "5+ years", "senior", "manager", ...).
3. Work arrangement agreement - same idea ("fully remote", "hybrid",
   "in office", ...).

The keyword rules are not perfect truth, so this is an agreement score,
not an accuracy score. Where the rule is confident and the model disagrees,
that is worth looking at. Use eval_interpretation.py on a small sample when
you want true hand-checked accuracy.

    python score_interpretation.py          # score everything interpreted
    python score_interpretation.py 100      # score a random 100
"""
import re
import sys

from db_utils import get_db_connection


def rule_seniority(text):
    """Guess seniority from the description. None when it doesn't say."""
    t = text.lower()
    if re.search(r"\b(intern|internship|co-op|student)\b", t):
        return "intern"
    if re.search(r"\b(manager|head of|director|vp of engineering)\b", t):
        return "lead"
    if re.search(r"\b(senior|staff|principal|sr\.)\b", t):
        return "senior"
    years = re.search(r"(\d+)\s*\+?\s*(?:-\s*\d+\s*)?years", t)
    if years:
        n = int(years.group(1))
        if n <= 2:
            return "junior"
        if n <= 4:
            return "mid"
        return "senior"
    if re.search(r"\b(entry[- ]level|new grad|graduate role)\b", t):
        return "junior"
    return None


def rule_arrangement(text):
    """Guess remote/hybrid/onsite from the description. None when unclear."""
    t = text.lower()
    if re.search(r"\bhybrid\b|days (?:per week )?in (?:the )?office|"
                 r"\d+\s*days a week onsite", t):
        return "hybrid"
    if re.search(r"\b(fully remote|100% remote|work from anywhere|"
                 r"remote[- ]first|distributed team)\b", t):
        return "remote"
    if re.search(r"\b(on-?site|in-?office|in person|based (?:out )?of our)\b", t):
        return "onsite"
    if re.search(r"\bremote\b", t):
        return "remote"
    return None


def main():
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else None

    conn = get_db_connection()
    cur = conn.cursor()
    sql = """
        SELECT source, title, extracted_skills, seniority, work_arrangement,
               description
        FROM jobs
        WHERE interpreted_at IS NOT NULL AND description IS NOT NULL
    """
    if limit:
        sql += " ORDER BY RANDOM() LIMIT %s"
        cur.execute(sql, (limit,))
    else:
        cur.execute(sql)
    rows = cur.fetchall()
    cur.close()
    conn.close()

    if not rows:
        print("Nothing interpreted yet.")
        return

    grounded = total_skills = 0
    jobs_with_skills = empty_skills = 0
    sen_agree = sen_judged = 0
    arr_agree = arr_judged = 0
    disagreements = []

    for source, title, skills, seniority, arrangement, description in rows:
        text = description.lower()

        skill_list = [s.strip() for s in (skills or "").split(",") if s.strip()]
        if skill_list:
            jobs_with_skills += 1
            for skill in skill_list:
                total_skills += 1
                # "ci/cd" also counts if the text says "ci / cd"
                if skill in text or skill.replace("/", " / ") in text:
                    grounded += 1
        else:
            empty_skills += 1

        expected = rule_seniority(text)
        if expected:
            sen_judged += 1
            if expected == seniority:
                sen_agree += 1
            elif len(disagreements) < 10:
                disagreements.append(
                    f"seniority  {source:<12} model={seniority:<8} "
                    f"rule={expected:<8} {title[:45]}")

        expected = rule_arrangement(text)
        if expected:
            arr_judged += 1
            if expected == arrangement:
                arr_agree += 1
            elif len(disagreements) < 10:
                disagreements.append(
                    f"arrangement {source:<12} model={arrangement:<8} "
                    f"rule={expected:<8} {title[:45]}")

    def pct(part, whole):
        return f"{100 * part / whole:.0f}%" if whole else "n/a"

    print(f"\nScored {len(rows)} interpreted jobs\n" + "=" * 60)
    print(f"Skill grounding      {grounded}/{total_skills} "
          f"({pct(grounded, total_skills)}) of listed skills appear in the text")
    print(f"Jobs with skills     {jobs_with_skills}/{len(rows)} "
          f"({pct(jobs_with_skills, len(rows))}), {empty_skills} returned none")
    print(f"Seniority agreement  {sen_agree}/{sen_judged} "
          f"({pct(sen_agree, sen_judged)}) where the text states a level")
    print(f"Arrangement agree.   {arr_agree}/{arr_judged} "
          f"({pct(arr_agree, arr_judged)}) where the text states one")

    if disagreements:
        print("\nExamples where model and keyword rule disagree:")
        for line in disagreements:
            print("  " + line)


if __name__ == "__main__":
    main()
