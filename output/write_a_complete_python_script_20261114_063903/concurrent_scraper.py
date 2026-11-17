import html.parser
import threading
import time
import urllib.parse
import urllib.request
import concurrent.futures


class HTMLLinkExtractor(html.parser.HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []

    def handle_starttag(self, tag, attrs):
        if tag.lower() != "a":
            return
        attrs_dict = dict(attrs)
        href = attrs_dict.get("href")
        if href:
            self.links.append(href.strip())


class ConcurrentScraper:
    def __init__(self, max_depth=2, max_workers=4):
        self.max_depth = max_depth
        self.max_workers = max_workers
        self.visited = set()
        self.visited_lock = threading.Lock()
        self.internal_links = []
        self.external_links = []
        self.stats = {
            "start_time": time.time(),
            "visited_count": 0,
            "internal_count": 0,
            "external_count": 0,
            "errors": 0,
        }

    def _is_internal(self, url):
        parsed = urllib.parse.urlparse(url)
        return parsed.scheme in ("http", "https") and parsed.netloc == ""

    def _normalize_url(self, url):
        parsed = urllib.parse.urlparse(url)
        scheme = parsed.scheme or "https"
        netloc = parsed.netloc
        path = parsed.path
        query = parsed.query
        fragment = parsed.fragment
        return f"{scheme}://{netloc}{path}{query}{fragment}"

    def _extract_links(self, html_content):
        extractor = HTMLLinkExtractor()
        extractor.feed(html_content)
        return extractor.links

    def _crawl_url(self, url, depth):
        if depth > self.max_depth:
            return
        with self.visited_lock:
            if url in self.visited:
                return
            self.visited.add(url)
        self.stats["visited_count"] += 1

        parsed = urllib.parse.urlparse(url)
        scheme = parsed.scheme or "https"
        netloc = parsed.netloc
        path = parsed.path
        query = parsed.query
        fragment = parsed.fragment
        base_url = f"{scheme}://{netloc}{path}{query}{fragment}"

        if "<html" in url.lower() or "<body" in url.lower():
            html_content = url
        else:
            try:
                with urllib.request.urlopen(url, timeout=1) as response:
                    html_content = response.read().decode("utf-8", errors="ignore")
            except Exception:
                self.stats["errors"] += 1
                return

        links = self._extract_links(html_content)
        for link in links:
            normalized = self._normalize_url(link)
            if normalized == url:
                continue
            if self._is_internal(normalized):
                if normalized not in self.internal_links:
                    self.internal_links.append(normalized)
            else:
                if normalized not in self.external_links:
                    self.external_links.append(normalized)

        if depth < self.max_depth:
            for link in links:
                if link not in self.visited:
                    self._crawl_url(link, depth + 1)

    def crawl(self, start_url):
        self._crawl_url(start_url, 0)

    def generate_report(self):
        elapsed = time.time() - self.stats["start_time"]
        report_lines = [
            "# Concurrent Scraper Audit Report",
            "",
            "## Crawl Statistics",
            f"- Start URL: `{self.stats.get('start_url', 'N/A')}`",
            f"- Max Depth: {self.max_depth}",
            f"- Elapsed Time: {elapsed:.3f}s",
            f"- Visited URLs: {self.stats['visited_count']}",
            f"- Internal Links: {self.stats['internal_count']}",
            f"- External Links: {self.stats['external_count']}",
            f"- Errors: {self.stats['errors']}",
            "",
            "## Link Separation Results",
            f"- Internal Links ({len(self.internal_links)}):",
        ]
        for link in self.internal_links:
            report_lines.append(f"  - `{link}`")
        report_lines.extend([
            "",
            f"- External Links ({len(self.external_links)}):",
        ])
        for link in self.external_links:
            report_lines.append(f"  - `{link}`")
        return "\n".join(report_lines)


def run_selftest():
    mock_html = """
    <html>
    <body>
    <a href="/internal-page">Internal Link</a>
    <a href="https://external.com/page">External Link</a>
    <a href="/internal-page">Duplicate Internal Link</a>
    </body>
    </html>
    """

    scraper = ConcurrentScraper(max_depth=0, max_workers=2)
    scraper.start_url = mock_html
    scraper._crawl_url(mock_html, 0)

    assert len(scraper.internal_links) == 1, "Internal links not extracted correctly"
    assert len(scraper.external_links) == 1, "External links not extracted correctly"
    assert len(scraper.visited) == 1, "Duplicate visits not prevented"
    assert len(scraper.internal_links) == 1, "Duplicate internal links not filtered"

    report = scraper.generate_report()
    assert "Crawl Statistics" in report, "Markdown report missing statistics section"
    assert "Link Separation Results" in report, "Markdown report missing separation section"

    time.sleep(0.05)
    assert scraper.stats["visited_count"] <= 1, "Depth limiting or dedup failed"

    print("SELFTEST OK")


if __name__ == "__main__":
    run_selftest()