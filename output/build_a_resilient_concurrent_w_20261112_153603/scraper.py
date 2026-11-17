import time
import urllib.error
import urllib.request
import threading


class FetchError(Exception):
    """Raised when a URL fetch fails after all retry attempts are exhausted."""


class Scraper:
    """Concurrent-safe URL fetcher with exponential backoff and timeout handling.

    Uses only the standard library. Each instance owns its own retry state and
    is safe to share across threads because all shared state is guarded by a
    lock.
    """

    def __init__(self, config):
        self.config = config
        self._lock = threading.Lock()
        self._in_flight: dict[str, threading.Event] = {}

    def _backoff_delay(self, attempt: int) -> float:
        """Compute exponential backoff delay for a given retry attempt."""
        return 2 ** attempt

    def _is_retryable_status(self, code: int) -> bool:
        """Return True for status codes that warrant exponential backoff."""
        return code in (429, 500)

    def fetch_item(self, url: str) -> str:
        """Fetch the content of ``url`` with exponential backoff and timeouts.

        Returns the decoded response body on success. Raises FetchError when
        all retry attempts have been exhausted or the request cannot be
        completed within the configured timeout.
        """
        last_error = None
        for attempt in range(self.config.max_retries + 1):
            with self._lock:
                if url in self._in_flight:
                    self._in_flight[url].wait(timeout=self.config.timeout)
                else:
                    event = threading.Event()
                    self._in_flight[url] = event
            try:
                request = urllib.request.Request(
                    url,
                    headers={"User-Agent": self.config.user_agent},
                )
                with urllib.request.urlopen(request, timeout=self.config.timeout) as response:
                    return response.read().decode("utf-8")
            except urllib.error.HTTPError as exc:
                last_error = FetchError(f"HTTP {exc.code}")
                if self._is_retryable_status(exc.code) and attempt < self.config.max_retries:
                    delay = self._backoff_delay(attempt)
                    with self._lock:
                        self._in_flight[url].set()
                    time.sleep(delay)
                    continue
                raise last_error
            except (urllib.error.URLError, TimeoutError, OSError) as exc:
                last_error = FetchError(str(exc))
                if attempt < self.config.max_retries:
                    delay = self._backoff_delay(attempt)
                    with self._lock:
                        self._in_flight[url].set()
                    time.sleep(delay)
                    continue
                raise last_error
        raise last_error