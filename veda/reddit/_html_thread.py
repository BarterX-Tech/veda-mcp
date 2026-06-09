from __future__ import annotations

import re

import lxml.html

_COMMENT = "div[contains(@class,'thing') and contains(@class,'comment')]"


def _clean(text: str) -> str:
    return " ".join((text or "").split())


def _body_text(el) -> str:
    nodes = el.xpath(
        "./div[contains(@class,'entry')]"
        "//div[contains(@class,'usertext-body')]"
        "//div[contains(@class,'md')]"
    )
    return _clean(nodes[0].text_content()) if nodes else ""


def _parse_comment(el) -> dict:
    children = el.xpath(
        "./div[contains(@class,'child')]/div[contains(@class,'sitetable')]/" + _COMMENT
    )
    return {
        "author": el.get("data-author"),
        "body": _body_text(el),
        "replies": [_parse_comment(child) for child in children],
    }


def parse_thread_html(html: str) -> dict:
    if not html:
        return {"post": {}, "comments": [], "meta": {"source": "html"}}
    doc = lxml.html.fromstring(html)

    post: dict = {}
    links = doc.xpath("//div[contains(@class,'thing') and contains(@class,'link')]")
    if links:
        link = links[0]
        title_nodes = link.xpath(".//a[contains(@class,'title')]")
        post = {
            "author": link.get("data-author"),
            "subreddit": link.get("data-subreddit", ""),
            "title": _clean(title_nodes[0].text_content()) if title_nodes else "",
            "selftext": _body_text(link),
        }

    comments: list[dict] = []
    nested = doc.xpath(
        "//div[contains(@class,'commentarea')]//div[contains(@class,'nestedlisting')]"
    )
    if nested:
        comments = [_parse_comment(comment) for comment in nested[0].xpath("./" + _COMMENT)]

    return {"post": post, "comments": comments, "meta": {"source": "html"}}


def _normalize_html_url(raw_url: str) -> str:
    url = raw_url.strip().split("?")[0]
    if not url.startswith("http"):
        url = "https://" + url
    url = re.sub(r"(?:www|m|amp|new|old)\.reddit\.com", "old.reddit.com", url)
    url = re.sub(r"^(https?://)reddit\.com", r"\1old.reddit.com", url)
    if url.endswith(".json"):
        url = url[: -len(".json")]
    return url.rstrip("/") + "/"


def fetch_thread(raw_url: str, *, fetch=None) -> dict | None:
    if fetch is None:
        from veda._transport import fetch_html

        fetch = fetch_html
    html = fetch(_normalize_html_url(raw_url))
    if not html:
        return None
    result = parse_thread_html(html)
    return result if result.get("post") else None
