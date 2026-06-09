from __future__ import annotations

import re

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


def extract_profile(html: str) -> dict:
    if not html:
        return {"about_text": None, "external_urls": []}
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

    return {"about_text": about_text, "external_urls": deduped}
