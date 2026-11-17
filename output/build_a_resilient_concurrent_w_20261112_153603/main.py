import threading
from config import Config
from cache import TTLCache
from scraper import Scraper, FetchError


class CacheVerifier:
    def __init__(self, cache: TTLCache) -> None:
        self.cache = cache

    def verify(self, key: str, expected_content: str) -> bool:
        cached_content = self.cache.get(key)
        if cached_content is None:
            return False
        return cached_content == expected_content


def fetch_with_cache(url: str, cache: TTLCache, config: Config) -> dict:
    cache_key = f"url_{url}"
    cached_content = cache.get(cache_key)
    if cached_content is not None:
        return {"url": url, "status": "cached"}

    scraper = Scraper(config)
    try:
        content = scraper.fetch_item(url)
    except FetchError as exc:
        return {"url": url, "status": "error", "msg": str(exc)}

    cache.set(cache_key, content)
    return {"url": url, "status": "ok", "content_length": len(content)}


def run_concurrent_fetches(urls: list[str], config: Config, cache: TTLCache) -> list[dict]:
    results: list[dict] = [None] * len(urls)
    lock = threading.Lock()

    def worker(index: int, url: str) -> None:
        result = fetch_with_cache(url, cache, config)
        with lock:
            results[index] = result

    threads = [threading.Thread(target=worker, args=(i, url)) for i, url in enumerate(urls)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    return results


def verify_cache_hits(urls: list[str], cache: TTLCache, config: Config) -> list[dict]:
    verifier = CacheVerifier(cache)
    verification_results: list[dict] = []
    for url in urls:
        cache_key = f"url_{url}"
        cached_content = cache.get(cache_key)
        if cached_content is None:
            verification_results.append({"url": url, "status": "no_cache"})
            continue
        scraper = Scraper(config)
        try:
            fresh_content = scraper.fetch_item(url)
        except FetchError as exc:
            verification_results.append({"url": url, "status": "error", "msg": str(exc)})
            continue
        verified = verifier.verify(cache_key, fresh_content)
        verification_results.append({
            "url": url,
            "status": "verified" if verified else "mismatch",
            "cached_length": len(cached_content),
            "fresh_length": len(fresh_content),
        })
    return verification_results


def main(urls: list[str], config: Config, cache: TTLCache) -> list[dict]:
    fetch_results = run_concurrent_fetches(urls, config, cache)
    verification_results = verify_cache_hits(urls, cache, config)
    return fetch_results + verification_results


if __name__ == "__main__":
    config = Config.load()
    cache = TTLCache(ttl=config.timeout)
    urls = [
        "https://example.com/item-1",
        "https://example.com/item-2",
        "https://example.com/item-3",
        "https://example.com/item-4",
        "https://example.com/item-5",
    ]
    results = main(urls, config, cache)
    for result in results:
        print(result)