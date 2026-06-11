from __future__ import annotations

import json
import re
from datetime import datetime

import lxml.html

_INLINE_URL_RE = re.compile(r"https?://[^\s\)\"'<>]+")
_MAX_URLS = 5


def _is_reddit(url: str) -> bool:
    low = url.lower()
    return "reddit.com" in low or "redd.it" in low


def _first_xpath_text(doc, expressions: tuple[str, ...]) -> str | None:
    for expression in expressions:
        nodes = doc.xpath(expression)
        if nodes:
            text = " ".join(nodes[0].text_content().split())
            if text:
                return text
    return None


def _karma_value(doc, expression: str) -> int | None:
    for node in doc.xpath(expression):
        text = node.text_content().replace(",", "").strip()
        if text.lstrip("-").isdigit():
            return int(text)
    return None


def _created_utc(doc) -> float | None:
    for value in doc.xpath(
        "//*[contains(concat(' ', normalize-space(@class), ' '), ' titlebox ')]//time/@datetime"
    ):
        try:
            return datetime.fromisoformat(value).timestamp()
        except ValueError:
            continue
    return None


def extract_new_profile(html: str) -> dict:
    """Extract bio + social links from the rendered new-reddit profile page.

    New-style profile data (bio text, social links) is not rendered on
    old.reddit at all, so it can only come from www.reddit markup.
    """
    if not html:
        return {"about_text": None, "external_urls": []}
    try:
        doc = lxml.html.fromstring(html)
    except Exception:
        return {"about_text": None, "external_urls": []}

    about_text = None
    nodes = doc.xpath("//*[@data-testid='profile-description']")
    if nodes:
        about_text = " ".join(nodes[0].text_content().split()) or None

    urls: list[str] = []
    for context in doc.xpath(
        "//faceplate-tracker[@noun='social_link']/@data-faceplate-tracking-context"
    ):
        try:
            url = json.loads(context).get("social_link", {}).get("url", "")
        except (ValueError, AttributeError):
            continue
        if url.startswith("http") and not _is_reddit(url):
            urls.append(url)

    seen: set[str] = set()
    deduped = []
    for url in urls:
        if url not in seen:
            seen.add(url)
            deduped.append(url)
        if len(deduped) >= _MAX_URLS:
            break
    return {"about_text": about_text, "external_urls": deduped}


_EMPTY_PROFILE = {
    "about_text": None,
    "external_urls": [],
    "post_karma": None,
    "comment_karma": None,
    "created_utc": None,
}


def extract_profile(html: str) -> dict:
    if not html:
        return dict(_EMPTY_PROFILE)
    doc = lxml.html.fromstring(html)

    about_text = _first_xpath_text(
        doc,
        (
            "//*[contains(concat(' ', normalize-space(@class), ' '), ' titlebox ')]"
            "//*[contains(concat(' ', normalize-space(@class), ' '), ' usertext-body ')]",
            "//*[contains(concat(' ', normalize-space(@class), ' '), ' profileDescription ')]",
        ),
    )

    urls: list[str] = []
    scopes = doc.xpath(
        "//*[contains(concat(' ', normalize-space(@class), ' '), ' titlebox ')]"
    ) or [doc]
    for scope in scopes:
        for anchor in scope.xpath(".//a[@href]"):
            href = anchor.get("href", "").strip()
            if href.startswith("http") and not _is_reddit(href):
                urls.append(href)

    if about_text:
        for match in _INLINE_URL_RE.findall(about_text):
            if not _is_reddit(match):
                urls.append(match.rstrip(".,);"))

    seen: set[str] = set()
    deduped: list[str] = []
    for url in urls:
        if url not in seen:
            seen.add(url)
            deduped.append(url)
        if len(deduped) >= _MAX_URLS:
            break

    comment_karma = _karma_value(
        doc,
        "//span[contains(concat(' ', normalize-space(@class), ' '), ' comment-karma ')]",
    )
    post_karma = _karma_value(
        doc,
        "//span[contains(concat(' ', normalize-space(@class), ' '), ' karma ') and "
        "not(contains(concat(' ', normalize-space(@class), ' '), ' comment-karma '))]",
    )
    return {
        "about_text": about_text,
        "external_urls": deduped,
        "post_karma": post_karma,
        "comment_karma": comment_karma,
        "created_utc": _created_utc(doc),
    }
