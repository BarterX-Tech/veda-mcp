from __future__ import annotations

from urllib.parse import parse_qs, urlparse

import lxml.html

_USER_URL = "https://old.reddit.com/user/{u}/{kind}/"
_SKIP_BODIES = {"[deleted]", "[removed]", ""}


def _clean(text: str) -> str:
    return " ".join((text or "").split())


def _has_class(node, class_name: str) -> bool:
    return class_name in (node.get("class") or "").split()


def _score(thing) -> int:
    nodes = thing.xpath(
        ".//*[contains(concat(' ', normalize-space(@class), ' '), ' score ') "
        "and contains(concat(' ', normalize-space(@class), ' '), ' unvoted ')]"
    )
    for node in nodes:
        title = node.get("title")
        if title and title.strip().lstrip("-").isdigit():
            return int(title)
        text = node.text_content().replace(",", "")
        for token in text.split():
            if token.lstrip("-").isdigit():
                return int(token)
    return 0


def _created(thing) -> float:
    timestamp = thing.get("data-timestamp")
    if timestamp and timestamp.isdigit():
        return int(timestamp) / 1000.0
    return 0.0


def parse_user_listing(html: str) -> dict:
    if not html:
        return {"items": [], "after": None}
    doc = lxml.html.fromstring(html)
    items: list[dict] = []
    for thing in doc.xpath("//div[contains(concat(' ', normalize-space(@class), ' '), ' thing ')]"):
        subreddit = thing.get("data-subreddit", "")
        created = _created(thing)
        score = _score(thing)
        permalink = thing.get("data-permalink") or ""
        if _has_class(thing, "comment"):
            body_nodes = thing.xpath(
                ".//*[contains(concat(' ', normalize-space(@class), ' '), ' usertext-body ')]"
                "//*[contains(concat(' ', normalize-space(@class), ' '), ' md ')]"
            )
            body = _clean(body_nodes[0].text_content()) if body_nodes else ""
            if body in _SKIP_BODIES:
                continue
            items.append(
                {
                    "type": "comment",
                    "subreddit": subreddit,
                    "body": body,
                    "score": score,
                    "created_utc": created,
                    "permalink": permalink,
                }
            )
        elif _has_class(thing, "link"):
            title_nodes = thing.xpath(
                ".//a[contains(concat(' ', normalize-space(@class), ' '), ' title ')]"
            )
            items.append(
                {
                    "type": "post",
                    "subreddit": subreddit,
                    "title": _clean(title_nodes[0].text_content()) if title_nodes else "",
                    "score": score,
                    "created_utc": created,
                    "permalink": permalink,
                }
            )

    after = None
    next_links = doc.xpath(
        "//span[contains(concat(' ', normalize-space(@class), ' '), ' next-button ')]//a"
    )
    if next_links:
        query = parse_qs(urlparse(next_links[0].get("href", "")).query)
        after = (query.get("after") or [None])[0]
    return {"items": items, "after": after}


def fetch_user_items(username: str, kind: str, *, pages: int = 2, fetch_html=None) -> list[dict]:
    if fetch_html is None:
        from veda._transport import fetch_html as default_fetch_html

        fetch_html = default_fetch_html

    items: list[dict] = []
    after = None
    for _ in range(pages):
        url = _USER_URL.format(u=username, kind=kind)
        if after:
            url += f"?count=25&after={after}"
        html = fetch_html(url)
        if not html:
            break
        parsed = parse_user_listing(html)
        items.extend(parsed["items"])
        after = parsed["after"]
        if not after:
            break
    return items


def fetch_user_history(username: str, *, pages: int = 2, fetch_html=None) -> dict:
    submitted = fetch_user_items(username, "submitted", pages=pages, fetch_html=fetch_html)
    comments = fetch_user_items(username, "comments", pages=pages, fetch_html=fetch_html)
    return {
        "posts": [item for item in submitted if item["type"] == "post"],
        "comments": [item for item in comments if item["type"] == "comment"],
    }
