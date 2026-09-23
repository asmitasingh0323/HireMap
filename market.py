"""Market summary (phase 2, weeks 13-14).

Turns everything the crawlers and the model have collected into a few
numbers about the job market itself: which skills are asked for most, how
the roles split by seniority and work arrangement, how many new listings
appear each day, and what the pay looks like per level.

Pandas does the counting, as planned in the proposal. Only active
(still-live) jobs are counted, so the picture reflects open roles.
"""
import pandas as pd

from db_utils import get_db_connection

TOP_SKILLS = 12
ACTIVITY_DAYS = 14
SENIORITY_ORDER = ["intern", "junior", "mid", "senior", "lead"]
ARRANGEMENT_ORDER = ["remote", "hybrid", "onsite"]


COLUMNS = ["source", "company", "first_seen", "seniority", "work_arrangement",
           "extracted_skills", "preferred_skills", "salary_min_ai",
           "salary_max_ai", "salary_basis", "interpreted_at"]


def _load_active_jobs():
    """Every active job, as a DataFrame.

    Rows are read with the project's own connection helper and handed to
    pandas directly; pandas.read_sql expects SQLAlchemy and warns otherwise.
    """
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(f"""
        SELECT {", ".join(COLUMNS)}
        FROM jobs
        WHERE status = 'active'
    """)
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return pd.DataFrame(rows, columns=COLUMNS)


def _skill_counts(frame, column, top=TOP_SKILLS):
    """Count how many jobs ask for each skill in a comma-separated column."""
    exploded = (frame[column].dropna()
                .str.split(",")
                .explode()
                .str.strip()
                .str.lower())
    exploded = exploded[exploded != ""]
    if exploded.empty:
        return []
    counts = exploded.value_counts().head(top)
    return [{"skill": skill, "jobs": int(count)}
            for skill, count in counts.items()]


def _ordered_counts(frame, column, order):
    """Counts for a column with a fixed, meaningful order (intern -> lead)."""
    counts = frame[column].dropna().str.lower().value_counts()
    return [{"name": value, "jobs": int(counts.get(value, 0))}
            for value in order if counts.get(value, 0) > 0]


def _hiring_activity(frame, days=ACTIVITY_DAYS):
    """New listings first seen per day, over the last N days."""
    seen = pd.to_datetime(frame["first_seen"].dropna())
    if seen.empty:
        return []
    daily = seen.dt.date.value_counts().sort_index()
    recent = daily.tail(days)
    return [{"day": str(day), "jobs": int(count)}
            for day, count in recent.items()]


def _average(series):
    """Mean as a whole number, or None when there is nothing to average."""
    value = series.mean(skipna=True)
    return None if pd.isna(value) else int(round(value))


def _salary_by_seniority(frame):
    """Average pay per level, using whatever figures we have."""
    paid = frame.dropna(subset=["seniority"]).copy()
    paid = paid[paid["salary_min_ai"].notna() | paid["salary_max_ai"].notna()]
    if paid.empty:
        return []
    paid["low"] = pd.to_numeric(paid["salary_min_ai"], errors="coerce")
    paid["high"] = pd.to_numeric(paid["salary_max_ai"], errors="coerce")
    paid["seniority"] = paid["seniority"].str.lower()

    rows = []
    for level in SENIORITY_ORDER:
        group = paid[paid["seniority"] == level]
        if group.empty:
            continue
        low = _average(group["low"])
        high = _average(group["high"])
        if low is None and high is None:
            continue
        rows.append({
            "name": level,
            "low": low if low is not None else high,
            "high": high if high is not None else low,
            "jobs": int(len(group)),
        })
    return rows


def market_summary():
    """Everything the market view needs, in one dictionary."""
    frame = _load_active_jobs()
    if frame.empty:
        return {"total_jobs": 0, "interpreted_jobs": 0, "top_skills": [],
                "preferred_skills": [], "seniority": [], "arrangement": [],
                "hiring_activity": [], "salary_by_seniority": [],
                "top_companies": [], "sources": []}

    companies = frame["company"].dropna().value_counts().head(8)

    return {
        "total_jobs": int(len(frame)),
        "interpreted_jobs": int(frame["interpreted_at"].notna().sum()),
        "top_skills": _skill_counts(frame, "extracted_skills"),
        "preferred_skills": _skill_counts(frame, "preferred_skills", top=8),
        "seniority": _ordered_counts(frame, "seniority", SENIORITY_ORDER),
        "arrangement": _ordered_counts(frame, "work_arrangement",
                                       ARRANGEMENT_ORDER),
        "hiring_activity": _hiring_activity(frame),
        "salary_by_seniority": _salary_by_seniority(frame),
        "top_companies": [{"name": name, "jobs": int(count)}
                          for name, count in companies.items()],
        "sources": [{"name": name, "jobs": int(count)} for name, count
                    in frame["source"].value_counts().items()],
    }


if __name__ == "__main__":
    import json
    print(json.dumps(market_summary(), indent=2, default=str))
