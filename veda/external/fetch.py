from __future__ import annotations

from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

import lxml.html

from veda._transport import _html_tier1, _html_tier2, _html_tier3
from veda._transport import fetch_html as transport_fetch_html
from veda.errors import Blocked
from veda.reddit.types import ExternalDoc

MIN_CHARS = 100
DEFAULT_MAX_CHARS = 20000

_TIER1_HOSTS = (
    "github.com",
    "medium.com",
    "substack.com",
    "hashnode.dev",
    "dev.to",
    "bearblog.dev",
    "micro.blog",
)
_TIER_ORDER = ("tier1", "tier2", "tier3")
_CONTENT_XPATHS = (
    "//article",
    "//main",
    "//*[@role='main']",
    "//*[contains(concat(' ', normalize-space(@class), ' '), ' post-content ')]",
    "//*[contains(concat(' ', normalize-space(@class), ' '), ' entry-content ')]",
    "//*[contains(concat(' ', normalize-space(@class), ' '), ' content ')]",
    "//*[@id='content']",
    "//*[contains(concat(' ', normalize-space(@class), ' '), ' prose ')]",
    "//*[contains(concat(' ', normalize-space(@class), ' '), ' markdown-body ')]",
)
_JUNK = ("cookie", "copyright", "all rights reserved", "subscribe to our newsletter")


def route_start_tier(url: str) -> str:
    host = (urlparse(url).hostname or "").lower()
    if host.endswith(".github.io"):
        return "tier1"
    if any(host_name in host for host_name in _TIER1_HOSTS):
        return "tier1"
    return "tier2"


def github_raw_readme_url(url: str) -> str | None:
    parsed = urlparse(url)
    if "github.com" not in (parsed.hostname or ""):
        return None
    parts = [part for part in parsed.path.split("/") if part]
    if len(parts) < 2:
        return None
    return f"https://raw.githubusercontent.com/{parts[0]}/{parts[1]}/main/README.md"


def _clean(text: str) -> str:
    return " ".join(text.split())


def extract_readable_text(html: str, *, max_chars: int = DEFAULT_MAX_CHARS) -> str:
    if not html:
        return ""
    doc = lxml.html.fromstring(html)
    for expression in _CONTENT_XPATHS:
        nodes = doc.xpath(expression)
        if nodes:
            text = _clean(nodes[0].text_content())
            if text:
                return text[:max_chars]
    lines = []
    for node in doc.xpath("//p | //h1 | //h2 | //h3"):
        text = _clean(node.text_content())
        if text and not any(junk in text.lower() for junk in _JUNK):
            lines.append(text)
    return "\n".join(lines)[:max_chars]


def robots_allowed(url: str, *, fetch_robots) -> bool:
    parsed = urlparse(url)
    robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
    text = fetch_robots(robots_url)
    if not text:
        return True
    parser = RobotFileParser()
    parser.parse(text.splitlines())
    return parser.can_fetch("*", url)


def _default_fetch_html(url: str, tier: str) -> str | None:
    return {"tier1": _html_tier1, "tier2": _html_tier2, "tier3": _html_tier3}[tier](url)


def fetch_url(
    url: str,
    *,
    max_chars: int = DEFAULT_MAX_CHARS,
    fetch_html=None,
    robots_check=None,
) -> ExternalDoc:
    if fetch_html is None:
        fetch_html = _default_fetch_html
    if robots_check is None:
        def robots_check(target: str) -> bool:
            return robots_allowed(target, fetch_robots=transport_fetch_html)
    if not robots_check(url):
        raise Blocked(f"robots.txt disallows {url}")

    start = route_start_tier(url)
    sequence = _TIER_ORDER[_TIER_ORDER.index(start) :]
    best_text = ""
    best_tier = sequence[0]
    for tier in sequence:
        try:
            html = fetch_html(url, tier)
        except Exception:
            html = None
        text = extract_readable_text(html or "", max_chars=max_chars)
        if len(text) > len(best_text):
            best_text = text
            best_tier = tier
        if len(text) >= MIN_CHARS:
            return {
                "url": url,
                "status": 200,
                "route": tier,
                "content_type": "text/html",
                "text": text,
            }

    if best_text:
        return {
            "url": url,
            "status": 200,
            "route": best_tier,
            "content_type": "text/html",
            "text": best_text,
        }
    raise Blocked(f"no readable text found at {url}")
