"""Base class for all job sources.

Every source (Adzuna, RemoteOK, ...) is one file in this folder
containing one class that inherits from SourceAdapter.
Subclasses are registered automatically - no central list to edit.
"""
import html
import os
import re
import unicodedata


REGISTRY = {}  # source name -> adapter instance


class SourceAdapter:
    # Subclasses must set these
    name = None            # e.g. "adzuna"
    requests_per_minute = 30   # polite default; used by the scheduler later
    enabled = True   # disabled adapters can still be run manually, but the API won't use them

    def __init_subclass__(cls, **kwargs):
        """Runs automatically whenever a subclass is defined - registers it."""
        super().__init_subclass__(**kwargs)
        if cls.name is None:
            raise ValueError(f"{cls.__name__} must set a 'name'")
        REGISTRY[cls.name] = cls()

    def fetch(self, keyword=None, location=None):
        """Return a list of job dicts. Written per source; never called directly
        by the workers, which call collect() so normalization always happens."""
        raise NotImplementedError

    def collect(self, keyword=None, location=None):
        """What the rest of the system calls: fetch, then normalize.

        Jobs without a title are dropped, because a job with no title cannot
        be deduplicated or shown.
        """
        jobs = self.fetch(keyword=keyword, location=location)
        cleaned = []
        for job in jobs:
            normalized = normalize_job(job, self.name)
            if not normalized["title"]:
                continue
            # This project is about US jobs written in English, so foreign
            # and non-English postings are dropped before they are stored.
            if US_ONLY and not is_us_location(normalized["location"]):
                continue
            if US_ONLY and not looks_english(normalized["title"],
                                             normalized["description"]):
                continue
            cleaned.append(normalized)
        return cleaned


def get_adapter(name):
    return REGISTRY.get(name)


def all_sources():
    return [name for name, a in REGISTRY.items() if a.enabled]


def matches_keyword(keyword, *texts):
    """True if EVERY word of the keyword appears somewhere in texts.

    Feeds that return one global list (RemoteOK, Remotive) have to be
    filtered here. Matching every word instead of the exact phrase means a
    search for "python developer" also finds "Senior Python Engineer"
    tagged "developer". An empty keyword matches everything.
    """
    if not keyword:
        return True
    haystack = " ".join(t for t in texts if t).lower()
    return all(word in haystack for word in keyword.lower().split())


# ---------------------------------------------------------------------------
# Normalization: sources disagree about fields, so everything they return is
# cleaned here before it reaches the database. One place, all sources.
# ---------------------------------------------------------------------------

# Every job saved must have exactly these keys.
JOB_FIELDS = [
    "title", "company", "location", "skills", "salary_min", "salary_max",
    "job_type", "experience_level", "posted_date", "source", "url",
    "description", "fingerprint",
]

# Longest description we keep. Enough for a model to read, small enough
# that the database and the prompts stay manageable.
MAX_DESCRIPTION_CHARS = 12000

# Keep only jobs that can be worked from the United States.
# Turn it off with:  $env:US_ONLY="false"
US_ONLY = os.getenv("US_ONLY", "true").lower() == "true"

# Different words for "this job is remote"
REMOTE_WORDS = {
    "", "anywhere", "worldwide", "remote", "fully remote", "100% remote",
    "anywhere in the world", "remote worldwide", "global",
}


def clean_text(value):
    """Tidy a text field: fix odd characters, collapse spaces, blank -> None."""
    if value is None:
        return None
    text = unicodedata.normalize("NFKC", str(value))
    # Mojibake from feeds that were encoded twice
    for bad, good in (("\u00e2\u20ac\u2122", "'"), ("\u00e2\u20ac\u0153", '"'),
                      ("\u00e2\u20ac\u009d", '"'), ("\u00e2\u20ac\u201c", "-"),
                      ("\u00c2\u00a0", " ")):
        text = text.replace(bad, good)
    text = re.sub(r"\s+", " ", text).strip()
    return text or None


def clean_location(value):
    """Tidy a location and use one word, 'Remote', for all the remote spellings."""
    text = clean_text(value)
    if text is None or text.lower().strip(" .") in REMOTE_WORDS:
        return "Remote"
    # "Remote - Seattle, WA" / "Remote, US" -> "Seattle, WA" / "US"
    text = re.sub(r"^remote\s*[-,:]\s*", "", text, flags=re.IGNORECASE)
    return text or "Remote"


def clean_salary(value):
    """Turn whatever a source sends (number, '$120,000', '120k') into a number."""
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        return float(value) if value > 0 else None
    text = str(value).lower().replace(",", "").strip()
    match = re.search(r"(\d+(?:\.\d+)?)\s*(k?)", text)
    if not match:
        return None
    number = float(match.group(1))
    if match.group(2) == "k":
        number *= 1000
    return number if number > 0 else None


def normalize_job(job, source):
    """Clean one job dict and guarantee every field in JOB_FIELDS exists.

    The fingerprint is recomputed from the CLEANED title/company/location, so
    the same role from two sources still produces the same fingerprint and
    deduplication keeps working.
    """
    from db_utils import make_fingerprint   # imported here to avoid a cycle

    clean = {field: job.get(field) for field in JOB_FIELDS}
    clean["title"] = clean_text(clean["title"])
    clean["company"] = clean_text(clean["company"])
    clean["location"] = clean_location(clean["location"])
    clean["skills"] = clean_text(clean["skills"])
    clean["job_type"] = (clean_text(clean["job_type"]) or "").lower() or None
    clean["experience_level"] = clean_text(clean["experience_level"])
    clean["url"] = clean_text(clean["url"])
    clean["description"] = clean_description(clean["description"])
    clean["source"] = source

    clean["salary_min"] = clean_salary(clean["salary_min"])
    clean["salary_max"] = clean_salary(clean["salary_max"])
    if (clean["salary_min"] and clean["salary_max"]
            and clean["salary_min"] > clean["salary_max"]):
        clean["salary_min"], clean["salary_max"] = (
            clean["salary_max"], clean["salary_min"])

    clean["fingerprint"] = make_fingerprint(
        clean["title"], clean["company"], clean["location"])
    return clean


def clean_description(value):
    """Turn a job description (often HTML) into plain readable text.

    Sources send HTML, escaped HTML or plain text. The interpretation worker
    reads this text, so tags and entities are stripped and the result is
    capped at MAX_DESCRIPTION_CHARS.
    """
    if not value:
        return None
    text = html.unescape(str(value))
    text = re.sub(r"<br\s*/?>|</p>|</li>|</div>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)          # drop remaining tags
    text = html.unescape(text)                     # entities inside tags
    text = re.sub(r"[ \t\u00a0]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n\n", text).strip()
    if not text:
        return None
    return text[:MAX_DESCRIPTION_CHARS]


# ---------------------------------------------------------------------------
# Country filtering: this project is about jobs a person in the US can take.
# ---------------------------------------------------------------------------

US_STATES = {
    "alabama", "alaska", "arizona", "arkansas", "california", "colorado",
    "connecticut", "delaware", "florida", "georgia", "hawaii", "idaho",
    "illinois", "indiana", "iowa", "kansas", "kentucky", "louisiana", "maine",
    "maryland", "massachusetts", "michigan", "minnesota", "mississippi",
    "missouri", "montana", "nebraska", "nevada", "new hampshire", "new jersey",
    "new mexico", "new york", "north carolina", "north dakota", "ohio",
    "oklahoma", "oregon", "pennsylvania", "rhode island", "south carolina",
    "south dakota", "tennessee", "texas", "utah", "vermont", "virginia",
    "washington", "west virginia", "wisconsin", "wyoming",
    "district of columbia",
}

US_STATE_CODES = {
    "al", "ak", "az", "ar", "ca", "co", "ct", "de", "fl", "ga", "hi", "id",
    "il", "in", "ia", "ks", "ky", "la", "me", "md", "ma", "mi", "mn", "ms",
    "mo", "mt", "ne", "nv", "nh", "nj", "nm", "ny", "nc", "nd", "oh", "ok",
    "or", "pa", "ri", "sc", "sd", "tn", "tx", "ut", "vt", "va", "wa", "wv",
    "wi", "wy", "dc",
}

US_WORDS = {"united states", "usa", "u.s.", "u.s", "us-based", "nationwide",
            "anywhere in the us", "remote us", "us remote"}

# Countries and cities that show up often in these feeds and are not the US
NON_US_WORDS = {
    "india", "bengaluru", "bangalore", "hyderabad", "pune", "mumbai", "delhi",
    "germany", "deutschland", "berlin", "munich", "münchen", "hamburg",
    "frankfurt", "cologne", "köln", "stuttgart", "potsdam", "kassel",
    "united kingdom", "england", "london", "manchester", "derby", "frome",
    "scotland", "ireland", "dublin", "france", "paris", "spain", "madrid",
    "barcelona", "portugal", "lisbon", "italy", "milan", "rome",
    "netherlands", "amsterdam", "belgium", "brussels", "poland", "warsaw",
    "krakow", "kraków", "romania", "bucharest", "ukraine", "kyiv", "kiev",
    "sweden", "stockholm", "norway", "oslo", "denmark", "copenhagen",
    "finland", "helsinki", "switzerland", "zurich", "zürich", "austria",
    "vienna", "czech", "prague", "greece", "athens", "turkey", "istanbul",
    "canada", "toronto", "vancouver", "montreal", "ottawa",
    "mexico", "brazil", "sao paulo", "são paulo", "argentina", "colombia",
    "chile", "peru", "latam", "australia", "sydney", "melbourne",
    "new zealand", "singapore", "japan", "tokyo", "china", "shanghai",
    "beijing", "hong kong", "korea", "seoul", "israel", "tel aviv",
    "south africa", "nigeria", "kenya", "egypt", "dubai", "uae",
    "philippines", "manila", "indonesia", "jakarta", "vietnam", "thailand",
    "pakistan", "bangladesh", "emea", "apac", "europe", "european",
}


def is_us_location(location):
    """Best guess at whether a job can be worked from the United States.

    Feeds write location freely ("Bengaluru, India", "San Francisco, CA",
    "Remote"), so this is a judgement, not a lookup. Unknown or plain
    "Remote" counts as US, because dropping a genuine US remote job is
    worse here than keeping an occasional foreign one.
    """
    if not location:
        return True
    text = location.lower()

    if any(word in text for word in US_WORDS):
        return True
    if any(word in text for word in NON_US_WORDS):
        return False

    # "Seattle, WA" / "Austin, TX • New York, NY"
    for piece in re.split(r"[,/|•·]| - ", text):
        piece = piece.strip().strip(".")
        if piece in US_STATES or piece in US_STATE_CODES:
            return True

    # Nothing recognisable: keep it (e.g. "Remote", "Anywhere")
    return True


# Words that appear constantly in these languages but almost never in an
# English job posting. Two or more hits means the posting is not in English.
NON_ENGLISH_MARKERS = [
    # German
    " und ", " oder ", " mit ", " für ", " wir ", " unsere ", " du ", " dich ",
    "erfahrung", "kenntnisse", "aufgaben", "mitarbeiter",
    # French
    " et ", " ou ", " avec ", " pour ", " nous ", " vous ", " votre ", " des ",
    "équipe", "compétences", "entreprise", "stage",
    # Spanish / Portuguese / Italian / Dutch
    " y ", " para ", " con ", " nosotros ", " experiencia ", " empresa ",
    " e ", " com ", " nossa ", " wij ", " onze ", " ervaring ",
]


def looks_english(*texts):
    """Rough language check: True unless the text is clearly another language.

    A tiny keyword test, not a language model. It only has to be good enough
    to keep German and French postings out of an English-only dataset.
    """
    blob = " ".join(t for t in texts if t).lower()
    if not blob.strip():
        return True
    hits = sum(1 for marker in NON_ENGLISH_MARKERS if marker in f" {blob} ")
    return hits < 3
