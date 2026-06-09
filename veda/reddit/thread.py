from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any

from veda._transport import (
    STEALTH_HTML,
    fetch_json_tier1,
    fetch_json_tier2,
    fetch_json_tier3,
    page_body,
    safe_fetch,
)
from veda.errors import Blocked, ParseError
from veda.reddit import _html_thread
from veda.reddit.rules import fetch_rules
from veda.reddit.types import Comment, Post, ThreadResult


def normalize_to_json_url(raw_url: str, *, resolver=None) -> str:
    url = raw_url.strip().split("?")[0]
    if not url.startswith("http"):
        url = "https://" + url
    if "/s/" in url:
        url = (resolver or _resolve_share_link)(url)
    if "/s/" not in url:
        url = re.sub(r"(?:www|old|m|amp|new)\.reddit\.com", "old.reddit.com", url)
        url = re.sub(r"^(https?://)reddit\.com", r"\1old.reddit.com", url)
    else:
        url = re.sub(r"(?:old|m|amp|new)\.reddit\.com", "www.reddit.com", url)
        url = re.sub(r"^(https?://)reddit\.com", r"\1www.reddit.com", url)
    url = url.rstrip("/")
    if not url.endswith(".json"):
        url += ".json"
    return url


def _page_url(page) -> str:
    for attr in ("url", "final_url", "current_url"):
        value = getattr(page, attr, None)
        if value:
            return str(value).split("?")[0]
    body = page_body(page)
    match = re.search(r'https?://(?:www|old)\.reddit\.com/r/[^"\']+/comments/[^"\']+', body)
    return match.group(0).split("?")[0] if match else ""


def _resolve_share_link(url: str, *, fetcher=None) -> str:
    resolve_url = re.sub(r"(?:old|m|amp|new)\.reddit\.com", "www.reddit.com", url)
    if "www.reddit.com" not in resolve_url:
        resolve_url = resolve_url.replace("reddit.com", "www.reddit.com")
    try:
        if fetcher is None:
            from scrapling.fetchers import StealthyFetcher

            fetcher = StealthyFetcher
        page = safe_fetch(fetcher, resolve_url, **STEALTH_HTML)
        final = _page_url(page)
        if "/comments/" in final:
            return final
    except Exception:
        pass
    return url


def extract_post(child: dict[str, Any]) -> Post:
    data = child.get("data", {})
    return {
        "title": data.get("title", ""),
        "author": data.get("author", "[deleted]"),
        "subreddit": data.get("subreddit", ""),
        "subreddit_prefixed": data.get("subreddit_name_prefixed", ""),
        "score": data.get("score", 0),
        "upvote_ratio": data.get("upvote_ratio", 0),
        "num_comments": data.get("num_comments", 0),
        "created_utc": data.get("created_utc", 0),
        "permalink": data.get("permalink", ""),
        "url": data.get("url", ""),
        "selftext": data.get("selftext", ""),
        "link_flair": data.get("link_flair_text", ""),
        "is_self": data.get("is_self", True),
        "over_18": data.get("over_18", False),
        "locked": data.get("locked", False),
        "archived": data.get("archived", False),
    }


def extract_comments(listing: dict[str, Any] | None, depth: int = 0) -> list[Comment]:
    results: list[Comment] = []
    children = listing.get("data", {}).get("children", []) if listing else []
    for child in children:
        kind = child.get("kind")
        data = child.get("data", {})
        if kind == "more":
            count = data.get("count", 0)
            ids = data.get("children", [])
            if count > 0 or ids:
                results.append(
                    {
                        "_type": "more",
                        "count": count,
                        "depth": depth,
                        "more_ids": ids[:20],
                        "_note": f"{count} more replies collapsed.",
                        "id": "",
                        "author": "",
                        "body": "",
                        "score": 0,
                        "created_utc": 0,
                        "parent_id": "",
                        "permalink": "",
                        "is_op": False,
                        "edited": False,
                        "gilded": 0,
                        "replies": [],
                    }
                )
            continue
        if kind != "t1":
            continue
        body = (data.get("body") or "").strip()
        if not body or body in ("[deleted]", "[removed]"):
            continue
        results.append(
            {
                "id": data.get("id", ""),
                "author": data.get("author", "[deleted]"),
                "body": body,
                "score": data.get("score", 0),
                "created_utc": data.get("created_utc", 0),
                "depth": depth,
                "parent_id": data.get("parent_id", ""),
                "permalink": data.get("permalink", ""),
                "is_op": data.get("is_submitter", False),
                "edited": bool(data.get("edited")),
                "gilded": data.get("gilded", 0),
                "replies": (
                    extract_comments(data.get("replies", {}), depth + 1)
                    if isinstance(data.get("replies"), dict)
                    else []
                ),
            }
        )
    return results


def _normalize_html_comments(comments: list[dict], depth: int = 0) -> list[Comment]:
    out: list[Comment] = []
    for comment in comments or []:
        if comment.get("_type") == "more":
            out.append(
                {
                    "_type": "more",
                    "count": comment.get("count", 0),
                    "depth": depth,
                    "more_ids": comment.get("more_ids", [])[:20],
                    "_note": f"{comment.get('count', 0)} more replies collapsed.",
                    "id": "",
                    "author": "",
                    "body": "",
                    "score": 0,
                    "created_utc": 0,
                    "parent_id": "",
                    "permalink": "",
                    "is_op": False,
                    "edited": False,
                    "gilded": 0,
                    "replies": [],
                }
            )
            continue
        out.append(
            {
                "id": comment.get("id", ""),
                "author": comment.get("author", "[deleted]"),
                "body": (comment.get("body") or "").strip(),
                "score": comment.get("score", 0),
                "created_utc": comment.get("created_utc", 0),
                "depth": depth,
                "parent_id": comment.get("parent_id", ""),
                "permalink": comment.get("permalink", ""),
                "is_op": comment.get("is_op", False),
                "edited": bool(comment.get("edited", False)),
                "gilded": comment.get("gilded", 0),
                "replies": _normalize_html_comments(comment.get("replies", []), depth + 1),
            }
        )
    return out


def count_stats(comments: list[dict]) -> dict[str, int]:
    fetched = 0
    collapsed = 0

    def walk(items: list[dict]) -> None:
        nonlocal collapsed, fetched
        for item in items:
            if item.get("_type") == "more":
                collapsed += item.get("count", 0)
            else:
                fetched += 1
                walk(item.get("replies", []))

    walk(comments)
    return {"fetched": fetched, "collapsed": collapsed}


def _html_url_from_json_url(json_url: str) -> str:
    html_url = json_url.split("?")[0]
    if html_url.endswith(".json"):
        html_url = html_url[: -len(".json")]
    return re.sub(r"(?:www|m|amp|new)\.reddit\.com", "old.reddit.com", html_url)


def _shape_html_result(
    html_result: dict,
    *,
    html_url: str,
    json_url: str,
    source_url: str,
    comment_sort: str,
    rules_fetcher=None,
) -> ThreadResult:
    post_in = html_result["post"]
    if rules_fetcher is None:
        rules_fetcher = fetch_rules
    html_comments = _normalize_html_comments(html_result.get("comments", []))
    stats = count_stats(html_comments)
    subreddit = post_in.get("subreddit", "")
    post: Post = {
        "title": post_in.get("title", ""),
        "author": post_in.get("author", "[deleted]"),
        "subreddit": subreddit,
        "subreddit_prefixed": f"r/{subreddit}" if subreddit else "",
        "score": post_in.get("score", 0),
        "upvote_ratio": post_in.get("upvote_ratio", 0),
        "num_comments": post_in.get("num_comments", stats["fetched"]),
        "created_utc": post_in.get("created_utc", 0),
        "permalink": post_in.get("permalink") or html_url,
        "url": post_in.get("url", html_url),
        "selftext": post_in.get("selftext", ""),
        "link_flair": post_in.get("link_flair"),
        "is_self": post_in.get("is_self", True),
        "over_18": post_in.get("over_18", False),
        "locked": post_in.get("locked", False),
        "archived": post_in.get("archived", False),
    }
    return {
        "post": post,
        "comments": html_comments,
        "subreddit_rules": rules_fetcher(subreddit) if subreddit else [],
        "meta": {
            "scraped_at": datetime.now(UTC).isoformat(),
            "json_url": json_url,
            "source_url": source_url,
            "comments_fetched": stats["fetched"],
            "comments_collapsed": stats["collapsed"],
            "sort": comment_sort,
            "route": "html",
        },
    }


def fetch_thread(
    url: str,
    *,
    comment_limit: int = 500,
    comment_sort: str = "top",
) -> ThreadResult:
    json_url = normalize_to_json_url(url)
    route = "json"
    raw = fetch_json_tier1(json_url, comment_limit=comment_limit, comment_sort=comment_sort)
    if not raw:
        route = "json"
        raw = fetch_json_tier2(
            json_url.split("?")[0].replace(".json", ""),
            comment_limit=comment_limit,
            comment_sort=comment_sort,
        )
    if not raw:
        route = "json"
        raw = fetch_json_tier3(
            json_url.split("?")[0].replace(".json", ""),
            comment_limit=comment_limit,
            comment_sort=comment_sort,
        )
    if not raw or not isinstance(raw, list) or len(raw) < 2:
        html_url = _html_url_from_json_url(json_url)
        html_result = _html_thread.fetch_thread(html_url)
        if html_result and html_result.get("post"):
            return _shape_html_result(
                html_result,
                html_url=html_url,
                json_url=json_url,
                source_url=url,
                comment_sort=comment_sort,
            )
        raise Blocked("All Reddit thread fetch routes failed")

    post_children = raw[0].get("data", {}).get("children", [])
    if not post_children:
        raise ParseError("No post data")
    post = extract_post(post_children[0])
    comments = extract_comments(raw[1])
    stats = count_stats(comments)
    result: ThreadResult = {
        "post": post,
        "comments": comments,
        "subreddit_rules": fetch_rules(post["subreddit"]),
        "meta": {
            "scraped_at": datetime.now(UTC).isoformat(),
            "json_url": json_url,
            "source_url": url,
            "comments_fetched": stats["fetched"],
            "comments_collapsed": stats["collapsed"],
            "sort": comment_sort,
            "route": route,
        },
    }
    if stats["collapsed"] > 0:
        result["meta"]["note"] = f"{stats['collapsed']} comments collapsed."
    return result
