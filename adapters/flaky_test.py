import os
import requests
from adapters.base import SourceAdapter


class FlakyTestAdapter(SourceAdapter):
    """A source that always fails, for testing source isolation.

    It is switched off unless you set FAULT_TEST=1, so normal crawls never
    see it. With it on, the scheduler treats it like any other source, and
    you can watch the other sources keep working while this one fails.
    """
    name = "flaky_test"
    requests_per_minute = 60
    enabled = os.getenv("FAULT_TEST") == "1"

    def fetch(self, keyword=None, location=None):
        raise requests.exceptions.ConnectionError(
            "flaky_test: pretending this source is down")
