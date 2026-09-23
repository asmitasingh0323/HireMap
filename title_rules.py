"""Seniority read from the job title.

Measuring the interpretation layer (see score_interpretation.py) showed the
small local model reads the description and calls a "Director of
Engineering" a senior engineer, because the description is full of hands-on
engineering work. Two prompt rewrites did not fix it.

A job title that says "Director" needs no judgement, so it is decided here
in code and the model is only asked when the title is silent. Rules where
rules are reliable, the model where they are not.

This lives in its own module so the pipeline (interpreter.py), the backfill
(backfill_seniority.py) and the scorer (score_interpretation.py) all share
one definition of the rule.
"""
import re

# Checked in order: the first match decides.
TITLE_RULES = [
    ("intern", (r"\bintern(ship)?\b", r"\bco-?op\b")),
    ("lead",   (r"\bmanager\b", r"\bhead of\b", r"\bdirector\b", r"\bvp\b",
                r"\bvice president\b", r"\bchief\b")),
    ("senior", (r"\bsenior\b", r"\bsr\.?\b", r"\bstaff\b", r"\bprincipal\b",
                r"\blead\b", r"\barchitect\b", r"\bdistinguished\b")),
    ("junior", (r"\bjunior\b", r"\bjr\.?\b", r"\bassociate\b",
                r"\bentry[- ]level\b", r"\bnew grad(uate)?\b",
                r"\bgraduate\b", r"\bapprentice\b")),
]

# "Product manager" and friends manage a product, not people, so they are
# not leads. They are skipped before the "lead" rule is applied.
NOT_PEOPLE_MANAGER = re.compile(
    r"\b(product|program|project|account|community|partner|marketing|"
    r"social media|content)\s+manager\b", re.I)


def seniority_from_title(title):
    """The level a job title states outright, or None if it states none.

    Used by the pipeline to overrule the model, and by the scorer to know
    which jobs the model actually decided.
    """
    text = (title or "").lower()
    if not text.strip():
        return None
    for level, patterns in TITLE_RULES:
        if level == "lead" and NOT_PEOPLE_MANAGER.search(text):
            continue                      # "product manager" is not a lead
        for pattern in patterns:
            if re.search(pattern, text, re.I):
                return level
    return None


if __name__ == "__main__":
    # Quick check that the rule does what the comments claim.
    examples = [
        ("Data Engineer Intern (2027)", "intern"),
        ("Engineering Manager, Machine Learning", "lead"),
        ("Director of Engineering, Safety", "lead"),
        ("Head of Security", "lead"),
        ("Senior .NET Software Engineer", "senior"),
        ("Staff Backend Engineer", "senior"),
        ("Junior Data Analyst", "junior"),
        ("Product Manager, Payments", None),
        ("Software Engineer", None),
    ]
    for title, expected in examples:
        got = seniority_from_title(title)
        mark = "ok " if got == expected else "FAIL"
        print(f"  {mark} {str(got):<8} {title}")
