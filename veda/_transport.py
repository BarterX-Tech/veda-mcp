from __future__ import annotations

import json
import re
import sys
import threading
import time
from collections import OrderedDict
from typing import Any

import requests

USER_AGENT = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 18_4 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.4 Mobile/15E148 Safari/604.1"
)

HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "application/json,text/html;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Cache-Control": "no-cache",
}

STEALTH_JSON = {
    "network_idle": True,
    "os_randomize": True,
    "block_webrtc": True,
    "disable_resources": True,
}
STEALTH_HTML = {
    "network_idle": True,
    "os_randomize": True,
    "block_webrtc": True,
    "block_images": True,
}
DYNAMIC_OPTS = {"network_idle": True, "stealth": True}

THREAD_DEFAULT_LIMIT = 500
THREAD_DEFAULT_SORT = "top"
THREAD_MAX_RETRIES = 3
THREAD_RETRY_DELAYS = (2, 4, 8)

JsonValue = dict[str, Any] | list[Any]


class MemoryCache:
    def __init__(self, max_entries: int = 256, ttl_seconds: float = 300.0) -> None:
        self.max_entries = max_entries
        self.ttl_seconds = ttl_seconds
        self._lock = threading.Lock()
        self._items: OrderedDict[str, tuple[float, Any]] = OrderedDict()

    def get(self, key: str) -> Any | None:
        with self._lock:
            item = self._items.get(key)
            if item is None:
                return None
            expires_at, value = item
            if expires_at < time.monotonic():
                self._items.pop(key, None)
                return None
            self._items.move_to_end(key)
            return value

    def set(self, key: str, value: Any) -> None:
        with self._lock:
            self._items[key] = (time.monotonic() + self.ttl_seconds, value)
            self._items.move_to_end(key)
            while len(self._items) > self.max_entries:
                self._items.popitem(last=False)

    def clear(self) -> None:
        with self._lock:
            self._items.clear()

    def snapshot(self) -> dict[str, int | float]:
        with self._lock:
            return {
                "size": len(self._items),
                "max_entries": self.max_entries,
                "ttl_seconds": self.ttl_seconds,
            }


class RateLimiter:
    def __init__(self, min_interval: float = 0.75) -> None:
        self.min_interval = min_interval
        self._lock = threading.Lock()
        self._last = 0.0

    def wait(self) -> None:
        with self._lock:
            now = time.monotonic()
            remaining = self.min_interval - (now - self._last)
            if remaining > 0:
                time.sleep(remaining)
            self._last = time.monotonic()


rate_limiter = RateLimiter()
cache = MemoryCache()

_tier_capabilities_cache: dict[str, dict[str, Any]] | None = None


def _probe_tier1() -> None:
    if not callable(requests.get):  # pragma: no cover - requests is a hard dependency
        raise RuntimeError("requests unavailable")


def _probe_tier2() -> None:
    from scrapling.fetchers import StealthyFetcher  # noqa: F401


def _probe_tier3() -> None:
    dynamic_fetcher()


def tier_capabilities(*, refresh: bool = False) -> dict[str, dict[str, Any]]:
    """Report which fetch tiers can run in this environment.

    Probes import-time dependencies only; it does not launch browsers.
    """
    global _tier_capabilities_cache
    if _tier_capabilities_cache is not None and not refresh:
        return _tier_capabilities_cache
    capabilities: dict[str, dict[str, Any]] = {}
    for tier, probe in (
        ("tier1", _probe_tier1),
        ("tier2", _probe_tier2),
        ("tier3", _probe_tier3),
    ):
        try:
            probe()
        except Exception as exc:
            capabilities[tier] = {"available": False, "detail": f"{type(exc).__name__}: {exc}"}
        else:
            capabilities[tier] = {"available": True, "detail": "ok"}
    _tier_capabilities_cache = capabilities
    return capabilities


def clear_cache() -> None:
    cache.clear()


def cache_snapshot() -> dict[str, int | float]:
    return cache.snapshot()


def parse_text(text: str | None) -> JsonValue | None:
    if not text:
        return None
    body = text.strip()
    if not body or body.startswith("<"):
        return None
    return json.loads(body)


def safe_fetch(fetcher: Any, url: str, **opts: Any) -> Any:
    rate_limiter.wait()
    try:
        return fetcher.fetch(url, headless=True, **opts)
    except TypeError:
        return fetcher.fetch(url, headless=True, network_idle=True)


def dynamic_fetcher() -> Any:
    from scrapling import fetchers

    name = "PlayWrightFetcher" if hasattr(fetchers, "PlayWrightFetcher") else "DynamicFetcher"
    return getattr(fetchers, name)


def page_body(page: Any) -> str:
    return page.body if hasattr(page, "body") else str(page)


def _thread_params(comment_limit: int, comment_sort: str) -> str:
    return f"?limit={comment_limit}&sort={comment_sort}&raw_json=1"


def fetch_json_tier1(
    json_url: str,
    *,
    comment_limit: int = THREAD_DEFAULT_LIMIT,
    comment_sort: str = THREAD_DEFAULT_SORT,
) -> JsonValue | None:
    full_url = json_url + _thread_params(comment_limit, comment_sort)
    for attempt in range(THREAD_MAX_RETRIES):
        try:
            rate_limiter.wait()
            response = requests.get(full_url, headers=HEADERS, timeout=20)
            text = response.text.strip()
            if not text:
                raise ValueError("Empty response")
            if text.startswith("<"):
                title = re.search(r"<title[^>]*>([^<]+)</title>", text, re.I)
                label = title.group(1) if title else "unknown"
                raise ValueError(f"HTML returned ({label})")
            data = json.loads(text)
            if isinstance(data, dict) and data.get("error"):
                raise ValueError(f"Reddit error {data['error']}: {data.get('message', '')}")
            return data
        except Exception as exc:
            sys.stderr.write(f"[tier1] attempt {attempt + 1}/{THREAD_MAX_RETRIES}: {exc}\n")
            if attempt < THREAD_MAX_RETRIES - 1:
                time.sleep(THREAD_RETRY_DELAYS[attempt])
    if "old.reddit.com" in json_url:
        return fetch_json_tier1(
            json_url.replace("old.reddit.com", "www.reddit.com"),
            comment_limit=comment_limit,
            comment_sort=comment_sort,
        )
    return None


def fetch_json_tier2(
    permalink: str,
    *,
    comment_limit: int = THREAD_DEFAULT_LIMIT,
    comment_sort: str = THREAD_DEFAULT_SORT,
) -> JsonValue | None:
    try:
        from scrapling.fetchers import StealthyFetcher

        json_url = permalink.rstrip("/") + ".json"
        page = safe_fetch(
            StealthyFetcher,
            json_url + _thread_params(comment_limit, comment_sort),
            **STEALTH_JSON,
        )
        text = page_body(page).strip()
        if text and not text.startswith("<"):
            return json.loads(text)
    except Exception as exc:
        sys.stderr.write(f"[tier2] failed: {exc}\n")
    return None


def fetch_json_tier3(
    permalink: str,
    *,
    comment_limit: int = THREAD_DEFAULT_LIMIT,
    comment_sort: str = THREAD_DEFAULT_SORT,
) -> JsonValue | None:
    try:
        json_url = permalink.rstrip("/") + ".json"
        page = safe_fetch(
            dynamic_fetcher(),
            json_url + _thread_params(comment_limit, comment_sort),
            **DYNAMIC_OPTS,
        )
        text = page_body(page).strip()
        if text and not text.startswith("<"):
            return json.loads(text)
    except Exception as exc:
        sys.stderr.write(f"[tier3] failed: {exc}\n")
    return None


def _json_tier1(url: str) -> JsonValue | None:
    rate_limiter.wait()
    response = requests.get(url, headers=HEADERS, timeout=20)
    return parse_text(response.text)


def _json_tier2(url: str) -> JsonValue | None:
    from scrapling.fetchers import StealthyFetcher

    page = safe_fetch(StealthyFetcher, url, **STEALTH_JSON)
    return parse_text(page_body(page))


def _json_tier3(url: str) -> JsonValue | None:
    page = safe_fetch(dynamic_fetcher(), url, **DYNAMIC_OPTS)
    return parse_text(page_body(page))


def fetch_json(url: str) -> JsonValue | None:
    cache_key = f"json:{url}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached
    for tier in (_json_tier1, _json_tier2, _json_tier3):
        try:
            data = tier(url)
            if data is not None:
                cache.set(cache_key, data)
                return data
        except Exception as exc:
            sys.stderr.write(f"[veda.transport] {tier.__name__} failed: {exc!r}\n")
    return None


def _html_tier1(url: str) -> str | None:
    rate_limiter.wait()
    response = requests.get(url, headers=HEADERS, timeout=20)
    return response.text if response.status_code == 200 and response.text else None


def _html_tier2(url: str) -> str | None:
    from scrapling.fetchers import StealthyFetcher

    page = safe_fetch(StealthyFetcher, url, **STEALTH_HTML)
    return page_body(page)


def _html_tier3(url: str) -> str | None:
    page = safe_fetch(dynamic_fetcher(), url, **DYNAMIC_OPTS)
    return page_body(page)


def fetch_html(url: str) -> str | None:
    cache_key = f"html:{url}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached
    for tier in (_html_tier1, _html_tier2, _html_tier3):
        try:
            html = tier(url)
            if html:
                cache.set(cache_key, html)
                return html
        except Exception as exc:
            sys.stderr.write(f"[veda.transport] {tier.__name__} failed: {exc!r}\n")
    return None
