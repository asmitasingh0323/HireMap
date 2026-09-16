"""Week 1-2 check: the new adapters must return the same jobs as the old fetchers.

For each source, run the old function (fetchers.py) and the new adapter
with the same keyword/location, then compare the job fingerprints.
Run this once, then fetchers.py can be removed.
"""
import sys
from fetchers import FETCHERS
from adapters import get_adapter

keyword = sys.argv[1] if len(sys.argv) > 1 else "python"
location = sys.argv[2] if len(sys.argv) > 2 else "Seattle"

# slow_test is a fake source (it sleeps 15s), so skip it here
SOURCES = ["adzuna", "remoteok", "weworkremotely"]

print(f"Comparing old vs new for keyword='{keyword}', location='{location}'\n")
all_match = True
for source in SOURCES:
    try:
        old_jobs = FETCHERS[source](keyword=keyword, location=location)
        new_jobs = get_adapter(source).fetch(keyword=keyword, location=location)
    except Exception as e:
        print(f"  {source:15} -> could not run: {str(e).split(' for url:')[0]}")
        all_match = False
        continue

    old_set = {j["fingerprint"] for j in old_jobs}
    new_set = {j["fingerprint"] for j in new_jobs}

    if old_set == new_set:
        print(f"  {source:15} -> SAME   (old={len(old_jobs)}, new={len(new_jobs)})")
    else:
        all_match = False
        print(f"  {source:15} -> DIFFERENT (old={len(old_jobs)}, new={len(new_jobs)}, "
              f"only in old={len(old_set - new_set)}, only in new={len(new_set - old_set)})")

print("\nResult:", "ALL SOURCES MATCH" if all_match else "SOME SOURCES DIFFER (see above)")
