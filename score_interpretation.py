"""Automatic interpretation quality score (phase 2).

Hand-judging is slow, so this measures three things without a human:

1. Skill grounding - what share of the skills the model listed actually
   appear in the description. Low grounding means the model is inventing
   skills, which is the failure that matters most.
2. Seniority. Jobs whose title names a level ("Senior", "Intern",
   "Director") are decided in the pipeline by a title rule, so they are
   reported separately as a check that the stored value matches the rule.
   The remaining jobs are the ones the model actually judged, and those
   are compared against the years of experience the description asks for.
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
from title_rules import seniority_from_title


def rule_seniority(text):
    """Guess seniority from years of experience alone. None when unclear.

    The title is deliberately NOT read here. Titles that name a level are
    decided in the pipeline itself, by interpreter.seniority_from_title(),
    so scoring them would only compare that rule against itself. This
    function judges the jobs the model actually had to decide.
    """
    t = (text or "").lower()
    years = re.search(r"(\d+)\s*\+?\s*(?:-\s*\d+\s*)?years?(?:\s+of)?"
                      r"(?:\s+\w+){0,3}\s+experience", t)
    if years:
        n = int(years.group(1))
        if n <= 2:
            return "junior"
        if n <= 4:
            return "mid"
        return "senior"
    if re.search(r"\b(entry[- ]level|new grad|recent graduate)\b", t):
        return "junior"
    return None


def rule_arrangement(text):
    """Guess remote/hybrid/onsite from the description. None when unclear.

    Only clear statements count. Vague phrases like "in person" appear in
    benefits and culture boilerplate, so they are not enough on their own.
    """
    t = (text or "").lower()
    if re.search(r"\bhybrid\b|\d+\s*days?\s*(?:per week\s*)?in\s*(?:the\s*)?"
                 r"office|\d+\s*days a week (?:onsite|on-site|in office)", t):
        return "hybrid"
    if re.search(r"\b(fully remote|100% remote|work from anywhere|"
                 r"remote[- ]first|fully distributed|remote \(us\)|"
                 r"this (?:role|position) is remote)\b", t):
        return "remote"
    if re.search(r"\b(on-?site (?:role|position|daily)|"
                 r"required to (?:work )?(?:in|from) (?:the )?office|"
                 r"in-?office (?:role|position)|"
                 r"work from our .{0,20}office)\b", t):
        return "onsite"
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
    by_title = title_ok = 0
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

        # Jobs whose title names a level are set by the rule, not the model.
        # They are reported separately: counting them as "agreement" would
        # be the rule agreeing with itself.
        stated = seniority_from_title(title)
        if stated:
            by_title += 1
            if stated == seniority:
                title_ok += 1
            elif len(disagreements) < 10:
                disagreements.append(
                    f"seniority  {source:<12} stored={seniority:<8} "
                    f"title={stated:<8} {title[:45]}  (needs re-interpret)")
        else:
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
    print(f"Seniority by title   {title_ok}/{by_title} "
          f"({pct(title_ok, by_title)}) set by the title rule, not the model")
    print(f"Seniority agreement  {sen_agree}/{sen_judged} "
          f"({pct(sen_agree, sen_judged)}) on the rest, vs years of experience")
    print(f"Arrangement agree.   {arr_agree}/{arr_judged} "
          f"({pct(arr_agree, arr_judged)}) where the text states one")

    if disagreements:
        print("\nExamples where model and keyword rule disagree:")
        for line in disagreements:
            print("  " + line)


if __name__ == "__main__":
    main()
