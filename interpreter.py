"""Interpretation layer (phase 2, weeks 9-10).

Reads a job description with a small language model and returns a few
structured fields: required skills, seniority, and remote/hybrid/onsite.

The model call sits behind one function, ask_model(), so the rest of the
system does not care which model is used. The default backend is Ollama,
which runs locally: no account, no API key, no per-request cost.

Test it on its own:
    python interpreter.py            # interpret 3 stored jobs and print
    python interpreter.py 10         # interpret 10
"""
import os
import re
import sys
import json

import requests
from dotenv import load_dotenv

load_dotenv()

# Which local model to use, and where Ollama is listening.
MODEL_BACKEND = os.getenv("MODEL_BACKEND", "ollama")
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.2:3b")

# Descriptions are trimmed before the prompt: the first part of a posting
# holds the role and requirements; the rest is usually boilerplate.
MAX_PROMPT_CHARS = int(os.getenv("MAX_PROMPT_CHARS", "8000"))

SENIORITY_VALUES = {"intern", "junior", "mid", "senior", "lead", "unknown"}
ARRANGEMENT_VALUES = {"remote", "hybrid", "onsite", "unknown"}

PROMPT_TEMPLATE = """You read job postings and return facts about them.

Job title: {title}
Company: {company}
Location: {location}

Job description:
\"\"\"
{description}
\"\"\"

Return ONLY a JSON object with exactly these keys:
  "required_skills": at most 8 skills the posting REQUIRES (must-have,
            "you have", "required"), lowercase, 1-3 words each. [] if unclear.
  "preferred_skills": at most 6 skills described as nice-to-have, "bonus",
            "preferred", "a plus". [] if none.
  "seniority": one of "intern", "junior", "mid", "senior", "lead", "unknown".
            Decide from the experience asked for, not only the title:
              internship or student role     -> "intern"
              0-2 years, "entry level", "new grad" -> "junior"
              3-5 years, no "senior" in title      -> "mid"
              5+ years, or "senior"/"staff"/"principal" in the title -> "senior"
              manages engineers, "manager", "head of", "director" -> "lead"
            Use "unknown" only when the description says nothing about
            experience level at all.
  "work_arrangement": one of "remote", "hybrid", "onsite", "unknown".
            This is HOW the work is done, not where the company hires.
            A city in the location field does NOT make a job remote.
              says remote / work from anywhere / distributed -> "remote"
              says N days in office, or "hybrid"             -> "hybrid"
              says on-site, in-office, or names an office the
                person must work from                        -> "onsite"
            Use "unknown" when the description does not say.
  "salary_min": yearly US dollars as a plain number, or null.
  "salary_max": yearly US dollars as a plain number, or null.
  "salary_basis": "stated" if the posting gives pay, "estimated" if you
            inferred a typical US range for this role and seniority,
            "unknown" if you cannot say. If the posting gives an hourly
            rate, convert it to a year using 2080 hours.

No explanation, no extra keys."""


class ModelError(Exception):
    """The model could not be reached or gave nothing usable."""


def ask_model(prompt):
    """Send a prompt to the model and return its raw text answer."""
    if MODEL_BACKEND != "ollama":
        raise ModelError(f"unknown MODEL_BACKEND '{MODEL_BACKEND}'")
    try:
        resp = requests.post(
            f"{OLLAMA_URL}/api/generate",
            json={
                "model": OLLAMA_MODEL,
                "prompt": prompt,
                "stream": False,
                "format": "json",          # ask Ollama for JSON output
                "options": {"temperature": 0},
            },
            timeout=180,
        )
        resp.raise_for_status()
    except requests.exceptions.RequestException as e:
        raise ModelError(f"model call failed: {str(e).split(' for url:')[0]}")
    return resp.json().get("response", "")


def parse_answer(text):
    """Turn the model's answer into clean fields we can store.

    Models sometimes wrap JSON in prose or code fences, so the JSON object is
    located first. Anything missing or out of range becomes "unknown" or [],
    which is why a bad answer can never break the worker.
    """
    if not text:
        raise ModelError("empty answer")
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        raise ModelError("no JSON object in answer")
    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError as e:
        raise ModelError(f"invalid JSON: {e}")
    if not isinstance(data, dict):
        raise ModelError("answer was not an object")

    def clean_skill_list(raw, cap):
        if isinstance(raw, str):                     # "python, sql"
            raw = re.split(r"[,;]", raw)
        out = []
        for skill in raw or []:
            if not isinstance(skill, (str, int, float)):
                continue
            cleaned = re.sub(r"\s+", " ", str(skill)).strip().lower()
            if cleaned and len(cleaned) <= 30 and cleaned not in out:
                out.append(cleaned)
        return out[:cap]

    # "skills" is still accepted so older prompts keep working
    skills = clean_skill_list(
        data.get("required_skills") or data.get("skills"), 8)
    preferred = [s for s in clean_skill_list(data.get("preferred_skills"), 6)
                 if s not in skills]

    def clean_money(value):
        """A yearly dollar figure, or None. Hourly rates are scaled to a year."""
        if value in (None, "", "null"):
            return None
        try:
            amount = float(re.sub(r"[^\d.]", "", str(value)) or 0)
        except ValueError:
            return None
        if amount <= 0:
            return None
        if amount < 500:            # looks like an hourly rate
            amount *= 2080
        if amount < 10000 or amount > 2000000:
            return None             # outside anything believable
        return round(amount)

    salary_min = clean_money(data.get("salary_min"))
    salary_max = clean_money(data.get("salary_max"))
    if salary_min and salary_max and salary_min > salary_max:
        salary_min, salary_max = salary_max, salary_min

    basis = str(data.get("salary_basis", "unknown")).strip().lower()
    if basis not in {"stated", "estimated", "unknown"}:
        basis = "unknown"
    if not (salary_min or salary_max):
        basis = "unknown"

    seniority = str(data.get("seniority", "unknown")).strip().lower()
    if seniority not in SENIORITY_VALUES:
        seniority = "unknown"

    arrangement = str(data.get("work_arrangement", "unknown")).strip().lower()
    if arrangement not in ARRANGEMENT_VALUES:
        arrangement = "unknown"

    return {
        "skills": skills,
        "preferred_skills": preferred,
        "seniority": seniority,
        "work_arrangement": arrangement,
        "salary_min": salary_min,
        "salary_max": salary_max,
        "salary_basis": basis,
    }


def interpret_job(job):
    """Interpret one job dict (needs title, company, location, description)."""
    description = (job.get("description") or "")[:MAX_PROMPT_CHARS]
    if not description.strip():
        raise ModelError("job has no description")
    prompt = PROMPT_TEMPLATE.format(
        title=job.get("title") or "unknown",
        company=job.get("company") or "unknown",
        location=job.get("location") or "unknown",
        description=description,
    )
    result = parse_answer(ask_model(prompt))
    result["model"] = f"{MODEL_BACKEND}:{OLLAMA_MODEL}"
    return result


def model_is_available():
    """True if the model backend answers. Used before queuing work."""
    try:
        resp = requests.get(f"{OLLAMA_URL}/api/tags", timeout=5)
        return resp.status_code == 200
    except requests.exceptions.RequestException:
        return False


if __name__ == "__main__":
    # Small manual test: interpret a few stored jobs and print the results.
    from db_utils import jobs_needing_interpretation

    limit = int(sys.argv[1]) if len(sys.argv) > 1 else 3
    if not model_is_available():
        print(f"Model not reachable at {OLLAMA_URL}. Is Ollama running?")
        sys.exit(1)

    jobs = jobs_needing_interpretation(limit=limit)
    if not jobs:
        print("No jobs with a description are waiting to be interpreted.")
        sys.exit(0)

    for job in jobs:
        print(f"\n--- {job['title']} @ {job['company']} ({job['source']})")
        try:
            result = interpret_job(job)
            print(f"    required   : {', '.join(result['skills']) or '(none)'}")
            print(f"    preferred  : "
                  f"{', '.join(result['preferred_skills']) or '(none)'}")
            print(f"    seniority  : {result['seniority']}")
            print(f"    arrangement: {result['work_arrangement']}")
            if result["salary_min"] or result["salary_max"]:
                print(f"    salary     : {result['salary_min']} - "
                      f"{result['salary_max']} ({result['salary_basis']})")
        except ModelError as e:
            print(f"    FAILED: {e}")
