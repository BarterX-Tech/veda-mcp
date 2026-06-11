from __future__ import annotations

import sys
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

import lxml.html
import requests
import trafilatura

from veda._transport import HEADERS, _html_tier1, _html_tier2, _html_tier3, rate_limiter
from veda.config import get_scraping_config
from veda.errors import Blocked
from veda.reddit.types import ExternalDoc
from veda.security import validate_public_http_url

MIN_CHARS = 100
DEFAULT_MAX_CHARS = 20000
ROBOTS_TIMEOUT = 10

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


def github_raw_readme_url(url: str) -> str | None:
    parsed = urlparse(url)
    if (parsed.hostname or "").lower() not in ("github.com", "www.github.com"):
        return None
    parts = [part for part in parsed.path.split("/") if part]
    if len(parts) != 2:
        return None
    return f"https://raw.githubusercontent.com/{parts[0]}/{parts[1]}/HEAD/README.md"


def _clean(text: str) -> str:
    return " ".join(text.split())


def extract_readable_text(html: str, *, max_chars: int = DEFAULT_MAX_CHARS) -> str:
    """Legacy xpath extraction; fallback when trafilatura finds nothing."""
    if not html:
        return ""
    doc = lxml.html.fromstring(html)
    for expression in _CONTENT_XPATHS:
        nodes = doc.xpath(expression)
        if nodes:
            blocks = [
                _clean(node.text_content())
                for node in nodes[0].xpath(".//p | .//h1 | .//h2 | .//h3 | .//li")
            ]
            text = "\n".join(block for block in blocks if block)
            if not text:
                text = _clean(nodes[0].text_content())
            if text:
                return text[:max_chars]
    lines = []
    for node in doc.xpath("//p | //h1 | //h2 | //h3"):
        text = _clean(node.text_content())
        if text and not any(junk in text.lower() for junk in _JUNK):
            lines.append(text)
    return "\n".join(lines)[:max_chars]


_HEADING_TAGS = ("h1", "h2", "h3", "h4", "h5", "h6")
_BLOCK_TAGS = _HEADING_TAGS + ("p", "li", "blockquote")
_CHROME_TAGS = ("nav", "header", "footer", "aside", "script", "style")
HEADING_REPAIR_THRESHOLD = 0.5


def _normalize_for_match(text: str) -> str:
    for marker in ("*", "_", "`", "#", ">"):
        text = text.replace(marker, " ")
    return " ".join(text.split()).lower()


def _inside_chrome(node) -> bool:
    parent = node.getparent()
    while parent is not None:
        if parent.tag in _CHROME_TAGS:
            return True
        parent = parent.getparent()
    return False


def _content_blocks(html: str) -> list[tuple[str, str]]:
    """Block-level (tag, text) pairs in document order, skipping page chrome."""
    try:
        doc = lxml.html.fromstring(html)
    except Exception:
        return []
    blocks = []
    for node in doc.iter():
        if not isinstance(node.tag, str) or node.tag not in _BLOCK_TAGS:
            continue
        if _inside_chrome(node):
            continue
        text = _clean(node.text_content())
        if text:
            blocks.append((node.tag, text))
    return blocks


def missing_heading_ratio(html: str, extracted_text: str) -> float:
    """Fraction of in-content headings absent from the extracted text."""
    headings = [text for tag, text in _content_blocks(html) if tag in _HEADING_TAGS]
    if not headings:
        return 0.0
    normalized_output = _normalize_for_match(extracted_text)
    missing = sum(
        1 for text in headings if _normalize_for_match(text) not in normalized_output
    )
    return missing / len(headings)


def rebuild_with_headings(html: str, extracted_text: str) -> str:
    """Rebuild document-order text, re-inserting headings the extractor dropped.

    Content blocks are kept only when the extractor's output vouches for them,
    so chrome/junk stays out; headings attach to the next kept block, and
    headings of sections with no kept content are dropped.
    """
    normalized_output = _normalize_for_match(extracted_text)
    lines: list[str] = []
    pending_headings: list[tuple[str, str]] = []
    for tag, text in _content_blocks(html):
        if tag in _HEADING_TAGS:
            pending_headings.append((tag, text))
            continue
        anchor = _normalize_for_match(text)[:60]
        if not anchor or anchor not in normalized_output:
            continue
        for heading_tag, heading_text in pending_headings:
            level = int(heading_tag[1])
            lines.append(f"{'#' * level} {heading_text}")
        pending_headings = []
        if tag == "li":
            lines.append(f"- {text}")
        elif tag == "blockquote":
            lines.append(f"> {text}")
        else:
            lines.append(text)
    return "\n\n".join(lines)


def _html_title(html: str) -> str | None:
    try:
        doc = lxml.html.fromstring(html)
    except Exception:
        return None
    nodes = doc.xpath("//title")
    if not nodes:
        return None
    return _clean(nodes[0].text_content()) or None


def extract_document(html: str | None, *, max_chars: int = DEFAULT_MAX_CHARS) -> dict:
    """Extract readable text plus title; trafilatura first, xpath chain fallback."""
    if not html:
        return {"text": "", "title": None, "truncated": False}
    text = ""
    title = None
    try:
        text = (
            trafilatura.extract(
                html,
                include_comments=False,
                favor_recall=True,
                output_format="markdown",
            )
            or ""
        )
        metadata = trafilatura.extract_metadata(html)
        if metadata is not None and getattr(metadata, "title", None):
            title = metadata.title
    except Exception as exc:
        sys.stderr.write(f"[veda.external] trafilatura failed: {exc!r}\n")
        text = ""
    if text and missing_heading_ratio(html, text) > HEADING_REPAIR_THRESHOLD:
        rebuilt = rebuild_with_headings(html, text)
        if len(rebuilt) >= len(text):
            text = rebuilt
    if not text:
        text = extract_readable_text(html, max_chars=max_chars + 1)
    if title is None:
        title = _html_title(html)
    truncated = len(text) > max_chars
    return {"text": text[:max_chars], "title": title, "truncated": truncated}


def fetch_robots_text(robots_url: str) -> str | None:
    """Fetch robots.txt with a cheap plain request; never the browser ladder."""
    try:
        rate_limiter.wait()
        response = requests.get(robots_url, headers=HEADERS, timeout=ROBOTS_TIMEOUT)
    except Exception:
        return None
    if response.status_code != 200 or not response.text:
        return None
    return response.text


def robots_allowed(url: str, *, fetch_robots) -> bool:
    parsed = urlparse(url)
    robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
    text = fetch_robots(robots_url)
    if not text:
        return True
    parser = RobotFileParser()
    parser.parse(text.splitlines())
    return parser.can_fetch("*", url)


MAX_REDIRECTS = 5


def validated_tier1_fetch(
    url: str,
    *,
    security_check=validate_public_http_url,
    max_redirects: int = MAX_REDIRECTS,
) -> str | None:
    """Plain-request fetch that re-validates every redirect hop.

    requests' automatic redirect following would let a public URL bounce
    into private/metadata address space after the initial SSRF check.
    """
    from urllib.parse import urljoin

    current = url
    for _ in range(max_redirects + 1):
        security_check(current)
        rate_limiter.wait()
        response = requests.get(
            current, headers=HEADERS, timeout=20, allow_redirects=False
        )
        if response.is_redirect:
            location = response.headers.get("location")
            if not location:
                return None
            current = urljoin(current, location)
            continue
        if response.status_code == 200 and response.text:
            return response.text
        return None
    raise Blocked(f"too many redirects for {url}")


def _default_fetch_html(url: str, tier: str) -> str | None:
    if tier == "tier1":
        return validated_tier1_fetch(url)
    return {"tier2": _html_tier2, "tier3": _html_tier3}[tier](url)


def fetch_url(
    url: str,
    *,
    max_chars: int = DEFAULT_MAX_CHARS,
    fetch_html=None,
    robots_check=None,
    raw_fetcher=None,
    security_check=validate_public_http_url,
) -> ExternalDoc:
    config = get_scraping_config()
    security_check(url)
    if fetch_html is None:
        fetch_html = _default_fetch_html
    if robots_check is None:
        def robots_check(target: str) -> bool:
            return robots_allowed(target, fetch_robots=fetch_robots_text)
    if not robots_check(url):
        raise Blocked(f"robots.txt disallows {url}")

    raw_url = github_raw_readme_url(url)
    if raw_url and config.external_github_raw_enabled:
        security_check(raw_url)
        if raw_fetcher is None:
            raw_fetcher = _html_tier1
        text = raw_fetcher(raw_url) or ""
        if text.strip():
            return {
                "url": url,
                "status": 200,
                "route": "github_raw",
                "content_type": "text/markdown",
                "text": text[:max_chars],
                "title": None,
                "truncated": len(text) > max_chars,
            }

    sequence = [tier for tier in _TIER_ORDER if config.external_tier_enabled(tier)]
    if not sequence:
        raise Blocked(f"no enabled external fetch routes for {url}")
    best_doc: dict | None = None
    best_tier = sequence[0]
    for tier in sequence:
        try:
            html = fetch_html(url, tier)
        except Exception as exc:
            sys.stderr.write(f"[veda.external] {tier} failed for {url}: {exc!r}\n")
            html = None
        doc = extract_document(html, max_chars=max_chars)
        if best_doc is None or len(doc["text"]) > len(best_doc["text"]):
            best_doc = doc
            best_tier = tier
        if len(doc["text"]) >= MIN_CHARS:
            best_tier = tier
            best_doc = doc
            break

    if best_doc and best_doc["text"]:
        return {
            "url": url,
            "status": 200,
            "route": best_tier,
            "content_type": "text/html",
            "text": best_doc["text"],
            "title": best_doc["title"],
            "truncated": best_doc["truncated"],
        }
    raise Blocked(f"no readable text found at {url}")
