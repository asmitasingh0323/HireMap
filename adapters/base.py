"""Base class for all job sources.

Every source (Adzuna, RemoteOK, ...) is one file in this folder
containing one class that inherits from SourceAdapter.
Subclasses are registered automatically - no central list to edit.
"""

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
        """Return a list of normalized job dicts (same shape as before)."""
        raise NotImplementedError


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
