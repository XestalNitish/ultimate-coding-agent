import time


class TTLCache:
    """In-memory TTL cache with expiration logic.

    Stores key-value pairs together with the timestamp at which they were
    set. Values are considered expired when the elapsed time since the
    timestamp exceeds the configured TTL.
    """

    def __init__(self, ttl: int = 300) -> None:
        self.ttl = ttl
        self._store: dict[str, tuple[float, str]] = {}

    def get(self, key: str) -> str | None:
        """Return the cached value for *key* if it exists and has not expired.

        Expired entries are removed from the store before returning None.
        """
        entry = self._store.get(key)
        if entry is None:
            return None
        expiry, value = entry
        if time.time() - expiry > self.ttl:
            del self._store[key]
            return None
        return value

    def set(self, key: str, value: str) -> None:
        """Store *value* under *key* with a timestamp for TTL expiration."""
        self._store[key] = (time.time(), value)

    def __len__(self) -> int:
        """Return the number of live (non-expired) entries in the cache."""
        return sum(
            1
            for expiry, _ in self._store.values()
            if time.time() - expiry <= self.ttl
        )