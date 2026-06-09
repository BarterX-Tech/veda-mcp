from __future__ import annotations

import re
from datetime import datetime

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


def _class_contains(name: str) -> str:
    return f"contains(concat(' ', normalize-space(@class), ' '), ' {name} ')"


def _int_from_text(text: str | None) -> int:
    if not text:
        return 0
    match = re.search(r"-?\d+", text.replace(",", ""))
    return int(match.group(0)) if match else 0


def _score(el) -> int:
    for class_name in ("unvoted", "likes", "dislikes"):
        nodes = el.xpath(f".//*[{_class_contains('score')} and {_class_contains(class_name)}]")
        for node in nodes:
            title = node.get("title")
            if title:
                return _int_from_text(title)
            text = _clean(node.text_content())
            if text and text not in {"•", "score hidden"}:
                return _int_from_text(text)
    return 0


def _created_utc(el) -> float:
    timestamp = el.get("data-timestamp")
    if timestamp and timestamp.isdigit():
        value = int(timestamp)
        return value / 1000.0 if value > 10_000_000_000 else float(value)
    time_nodes = el.xpath(".//time[@datetime]")
    if time_nodes:
        raw = time_nodes[0].get("datetime", "")
        try:
            return datetime.fromisoformat(raw.replace("Z", "+00:00")).timestamp()
        except ValueError:
            return 0.0
    return 0.0


def _fullname_id(el, prefix: str) -> str:
    fullname = el.get("data-fullname", "")
    return fullname.removeprefix(prefix)


def _own_entry(el):
    nodes = el.xpath("./div[contains(@class,'entry')]")
    return nodes[0] if nodes else el


def _is_op(el) -> bool:
    entry = _own_entry(el)
    return bool(entry.xpath(".//a[contains(@class,'author') and contains(@class,'submitter')]"))


def _edited(el) -> bool:
    entry = _own_entry(el)
    return bool(entry.xpath(".//*[contains(@class,'edited-timestamp')]"))


def _gilded(el) -> int:
    entry = _own_entry(el)
    nodes = entry.xpath(".//*[contains(@class,'gilded')]")
    if not nodes:
        return 0
    return max((_int_from_text(node.text_content()) for node in nodes), default=0)


def _num_comments(el) -> int:
    candidates = []
    for attr in ("data-comments-count", "data-num-comments"):
        value = el.get(attr)
        if value:
            candidates.append(value)
    nodes = el.xpath(".//a[contains(@class,'comments')]")
    candidates.extend(node.text_content() for node in nodes)
    for candidate in candidates:
        number = _int_from_text(candidate)
        if number:
            return number
    return 0


def _parse_comment(el) -> dict:
    children = el.xpath(
        "./div[contains(@class,'child')]/div[contains(@class,'sitetable')]/" + _COMMENT
    )
    return {
        "id": _fullname_id(el, "t1_"),
        "author": el.get("data-author"),
        "body": _body_text(el),
        "score": _score(el),
        "created_utc": _created_utc(el),
        "parent_id": el.get("data-parent", ""),
        "permalink": el.get("data-permalink", ""),
        "is_op": _is_op(el),
        "edited": _edited(el),
        "gilded": _gilded(el),
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
            "score": _score(link),
            "created_utc": _created_utc(link),
            "num_comments": _num_comments(link),
            "permalink": link.get("data-permalink", ""),
            "url": title_nodes[0].get("href", "") if title_nodes else "",
            "selftext": _body_text(link),
            "is_self": "self" in (link.get("class") or "").split(),
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
