"""In-memory TTL cache, token-bucket rate limiter, resilient HTTP wrapper, and self-test."""

import time
from typing import Any, Dict, Optional, Tuple


class TTLCache:
    """In-memory TTL cache with max_size eviction and expiration cleanup."""

    def __init__(self, max_size: int = 100, default_ttl: float = 60.0) -> None:
        self._max_size = max(1, int(max_size))
        self._default_ttl = float(default_ttl)
        self._store: Dict[str, Tuple[float, Any]] = {}

    def get(self, key: str) -> Optional[Any]:
        entry = self._store.get(key)
        if entry is None:
            return None
        expires_at, value = entry
        if expires_at <= time.monotonic():
            self.invalidate(key)
            return None
        return value

    def set(self, key: str, value: Any, ttl: Optional[float] = None) -> None:
        ttl = self._default_ttl if ttl is None else float(ttl)
        if ttl <= 0:
            raise ValueError("ttl must be positive")
        self._store[key] = (time.monotonic() + ttl, value)
        self._evict_if_needed()

    def invalidate(self, key: str) -> None:
        self._store.pop(key, None)

    def cleanup_expired(self) -> int:
        now = time.monotonic()
        expired = [k for k, (exp, _) in self._store.items() if exp <= now]
        for key in expired:
            del self._store[key]
        return len(expired)

    def _evict_if_needed(self) -> None:
        while len(self._store) > self._max_size:
            now = time.monotonic()
            expired = [k for k, (exp, _) in self._store.items() if exp <= now]
            if expired:
                for key in expired:
                    del self._store[key]
            else:
                oldest = min(self._store.items(), key=lambda item: item[1][0])[0]
                del self._store[oldest]


class TokenBucket:
    """Token-bucket rate limiter with capacity and refill_rate."""

    def __init__(self, capacity: float = 10.0, refill_rate: float = 1.0) -> None:
        if capacity <= 0:
            raise ValueError("capacity must be positive")
        if refill_rate <= 0:
            raise ValueError("refill_rate must be positive")
        self._capacity = float(capacity)
        self._refill_rate = float(refill_rate)
        self._tokens = float(self._capacity)
        self._last_refill = time.monotonic()

    def acquire(self, tokens: float = 1.0, timeout: Optional[float] = None) -> bool:
        """Acquire tokens, sleeping if necessary. Returns True on success."""
        if tokens <= 0:
            return True
        while True:
            now = time.monotonic()
            elapsed = now - self._last_refill
            self._tokens = min(self._capacity, self._tokens + elapsed * self._refill_rate)
            self._last_refill = now
            if self._tokens >= tokens:
                self._tokens -= tokens
                return True
            if timeout is not None:
                remaining = timeout - (now - self._last_refill)
                if remaining <= 0:
                    return False
                time.sleep(remaining)
            time.sleep(0.001)


class ResilientHTTP:
    """Resilient HTTP request wrapper with mock transport and exponential backoff."""

    def __init__(self, transport: Optional[Any] = None, max_retries: int = 3,
                 base_backoff: float = 0.1, retry_on_status: Tuple[int, ...] = (429, 500)) -> None:
        self._transport = transport
        self._max_retries = max(0, int(max_retries))
        self._base_backoff = float(base_backoff)
        self._retry_on_status = set(retry_on_status)

    def _request(self, method: str, url: str, body: Any = None) -> Tuple[int, str, str]:
        if self._transport is not None:
            return self._transport(method, url, body)
        raise RuntimeError("No transport configured; use a mock transport for deterministic testing")

    def request(self, method: str, url: str, body: Any = None,
                 max_retries: Optional[int] = None) -> Tuple[int, str, str]:
        retries = self._max_retries if max_retries is None else max(0, int(max_retries))
        backoff = self._base_backoff
        last_status = 0
        last_body = ""
        for attempt in range(retries + 1):
            status, text, _ = self._request(method, url, body)
            last_status = status
            last_body = text
            if status not in self._retry_on_status:
                return status, text, _
            if attempt >= retries:
                break
            time.sleep(backoff)
            backoff *= 2
        return last_status, last_body, ""


class MockTransport:
    """Deterministic mock transport for testing without network calls."""

    def __init__(self, responses: Optional[list] = None) -> None:
        self._responses = list(responses) if responses is not None else []
        self.calls: list = []

    def __call__(self, method: str, url: str, body: Any = None) -> Tuple[int, str, str]:
        self.calls.append((method, url, body))
        if self._responses:
            return self._responses.pop(0)
        return 200, "ok", ""


def run_selftest() -> None:
    """Run self-tests for cache, rate limiter, and HTTP retry behavior."""
    # TTL cache expiration
    cache = TTLCache(max_size=2, default_ttl=0.05)
    cache.set("a", 1)
    time.sleep(0.06)
    cache.set("b", 2)
    cache.cleanup_expired()
    assert cache.get("a") is None, "TTL cache should expire entries"
    assert cache.get("b") == 2, "TTL cache should keep non-expired entries"
    cache.set("c", 3, ttl=0.01)
    time.sleep(0.02)
    cache.cleanup_expired()
    assert cache.get("c") is None, "TTL cache should expire newly set entries"

    # TTL cache max_size eviction
    cache = TTLCache(max_size=2, default_ttl=100.0)
    cache.set("a", 1)
    cache.set("b", 2)
    cache.set("c", 3)
    assert len(cache._store) <= 2, "TTL cache should enforce max_size"

    # Rate limiter capacity and refill_rate
    bucket = TokenBucket(capacity=1.0, refill_rate=10.0)
    assert bucket.acquire(1.0), "Rate limiter should acquire first token"
    assert not bucket.acquire(1.0, timeout=0), "Rate limiter should reject second token without delay"
    start = time.monotonic()
    bucket.acquire(1.0)
    elapsed = time.monotonic() - start
    assert elapsed >= 0.05, "Rate limiter should enforce refill_rate delay"

    # HTTP wrapper retry behavior with mock transport
    transport = MockTransport(responses=[(429, "too many", ""), (500, "error", ""), (200, "ok", "")])
    http = ResilientHTTP(transport=transport, max_retries=3, base_backoff=0.01)
    status, text, _ = http.request("GET", "http://mock/path")
    assert status == 200, "HTTP wrapper should retry and succeed"
    assert len(transport.calls) == 3, "HTTP wrapper should make three attempts"

    print("SELFTEST OK")


if __name__ == "__main__":
    run_selftest()