"""Quick check that every registered adapter can fetch.
One source failing should not stop the others - same rule as the workers."""
from adapters import get_adapter, all_sources

print("Registered sources:", all_sources())
for s in all_sources():
    try:
        jobs = get_adapter(s).fetch(keyword="python")
        print(f"  {s} -> OK, {len(jobs)} jobs")
    except Exception as e:
        print(f"  {s} -> FAILED: {e}")
