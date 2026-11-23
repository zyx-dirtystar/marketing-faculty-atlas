"""Bounded public requests and resumable local cache for research scripts."""

from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from html import unescape
import json
import re
import threading
import time
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlsplit
from urllib.request import Request, urlopen

USER_AGENT = "MarketingFacultyAtlas/2.0 (+https://github.com/zyx-dirtystar/marketing-faculty-atlas)"


class Network:
    def __init__(self):
        self.lock = threading.Lock()
        self.ready_at = defaultdict(float)

    def get(self, url, accept="", limit=2_000_000):
        host = urlsplit(url).hostname
        if urlsplit(url).scheme not in {"http", "https"} or not host:
            return {"status": "invalid_url", "url": url}, b""
        spacing = .25 if host == "api.crossref.org" else .5
        with self.lock:
            now = time.monotonic()
            start = max(self.ready_at[host], now)
            self.ready_at[host] = start + spacing
        if start > now:
            time.sleep(start - now)
        request = Request(url, headers={"User-Agent": USER_AGENT, "Accept": accept or "*/*"})
        try:
            with urlopen(request, timeout=9) as response:
                body = response.read(limit + 1)
                result = {"status": "read", "url": response.geturl(),
                          "content_type": response.headers.get("Content-Type", ""),
                          "charset": response.headers.get_content_charset() or "utf-8"}
                if len(body) > limit:
                    return {**result, "status": "size_limit"}, b""
                return result, body
        except HTTPError as error:
            if error.code == 429:
                retry = error.headers.get("Retry-After", "")
                with self.lock:
                    self.ready_at[host] = time.monotonic() + (min(int(retry), 60) if retry.isdigit() else 20)
            return {"status": f"http_{error.code}", "url": error.geturl()}, b""
        except (URLError, ValueError, TimeoutError, OSError):
            return {"status": "connection_error", "url": url}, b""

    def crossref(self, doi):
        result, body = self.get("https://api.crossref.org/works/" + quote(doi, safe="/"),
                                "application/json")
        if result["status"] != "read":
            return result
        try:
            row = json.loads(body)["message"]
        except (ValueError, KeyError):
            return {**result, "status": "unreadable_metadata"}
        return {**result, "work": {
            key: row[key] for key in ("DOI", "title", "author", "abstract", "published",
                                     "container-title", "type", "URL", "relation", "update-to")
            if key in row}}


def plain_markup(value):
    return " ".join(unescape(re.sub(r"<[^>]*>", " ", value or "")).split())


def cache_rows(path):
    if not path.exists():
        return {}
    with path.open(encoding="utf-8") as stream:
        return dict(json.loads(line) for line in stream if line.strip())


def collect(keys, fetch, path, workers=12, retry=False):
    path.parent.mkdir(parents=True, exist_ok=True)
    previous = cache_rows(path)
    remaining = [key for key in keys if key not in previous or
                 retry and previous[key]["status"] in ("http_429", "connection_error", "http_503")]
    print(f"{len(remaining)} pending / {len(keys)} total", flush=True)
    with path.open("a", encoding="utf-8") as out, ThreadPoolExecutor(max_workers=workers) as pool:
        pending = {pool.submit(fetch, key): key for key in remaining}
        for done, promise in enumerate(as_completed(pending), 1):
            key = pending[promise]
            result = promise.result()
            print(json.dumps([key, result], ensure_ascii=False), file=out, flush=True)
            if done % 50 == 0 or done == len(remaining):
                print(f"{done}/{len(remaining)} completed", flush=True)
