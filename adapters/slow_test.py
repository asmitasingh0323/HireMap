import time
from db_utils import make_fingerprint
from adapters.base import SourceAdapter


class SlowTestAdapter(SourceAdapter):
    name = "slow_test"
    enabled = False   # never used by real searches; only for fault-recovery tests

    def fetch(self, keyword=None, location=None):
        print("  [slow_test] sleeping 15s to simulate a long fetch...")
        time.sleep(15)
        return [{
            "title": f"Test Job for {keyword}", "company": "TestCorp",
            "location": location or "Nowhere", "skills": None,
            "salary_min": None, "salary_max": None, "job_type": "test",
            "experience_level": None, "posted_date": None,
            "source": "slow_test",
            "url": None,
            "fingerprint": make_fingerprint(f"Test Job for {keyword}", "TestCorp", location or "Nowhere"),
        }]
