from __future__ import annotations

import time
from typing import Any

from veda._transport import fetch_json
from veda.config import get_scraping_config
from veda.errors import Blocked
from veda.reddit import _html_user
from veda.reddit.types import UserResult

_USER_URL = "https://old.reddit.com/user/{u}/{kind}.json?limit=100&raw_json=1"
_SKIP_BODIES = {"[deleted]", "[removed]"}


def _parse_history(post_children: list[dict], comment_children: list[dict]) -> UserResult:
    posts = []
    comments = []
    for child in post_children or []:
        data = child.get("data", {})
        posts.append(
            {
                "subreddit": data.get("subreddit", ""),
                "title": data.get("title", ""),
                "score": data.get("score", 0),
                "created_utc": data.get("created_utc", 0),
                "permalink": data.get("permalink", ""),
                "type": "post",
            }
        )
    for child in comment_children or []:
        data = child.get("data", {})
        body = (data.get("body") or "").strip()
        if not body or body in _SKIP_BODIES:
            continue
        comments.append(
            {
                "subreddit": data.get("subreddit", ""),
                "body": body,
                "score": data.get("score", 0),
                "created_utc": data.get("created_utc", 0),
                "permalink": data.get("permalink", ""),
                "type": "comment",
            }
        )
    return {"posts": posts, "comments": comments}


def _paginate(
    username: str,
    kind: str,
    pages: int,
    delay: float,
    *,
    json_fetcher=None,
) -> list[dict[str, Any]]:
    if json_fetcher is None:
        json_fetcher = fetch_json
    children: list[dict[str, Any]] = []
    after = None
    for index in range(pages):
        url = _USER_URL.format(u=username, kind=kind)
        if after:
            url += f"&after={after}"
        listing = json_fetcher(url)
        if not listing:
            break
        data = listing.get("data", {}) if isinstance(listing, dict) else {}
        children.extend(data.get("children", []))
        after = data.get("after")
        if not after:
            break
        if index < pages - 1 and delay:
            time.sleep(delay)
    return children


def fetch_user(
    username: str,
    *,
    kinds: tuple[str, ...] = ("submitted", "comments"),
    pages: int = 2,
    json_fetcher=None,
    html_history_fetcher=None,
) -> UserResult:
    config = get_scraping_config()
    if json_fetcher is None:
        json_fetcher = fetch_json
    if html_history_fetcher is None:
        html_history_fetcher = _html_user.fetch_user_history
    wants_posts = "submitted" in kinds
    wants_comments = "comments" in kinds
    posts = []
    comments = []
    if config.reddit_json_enabled:
        posts = (
            _paginate(username, "submitted", pages, 1.5, json_fetcher=json_fetcher)
            if wants_posts
            else []
        )
        comments = (
            _paginate(username, "comments", pages, 1.5, json_fetcher=json_fetcher)
            if wants_comments
            else []
        )
    result = _parse_history(posts, comments)
    if (wants_posts and not result["posts"]) or (wants_comments and not result["comments"]):
        if not config.reddit_html_enabled:
            raise Blocked("Reddit HTML route is disabled")
        html_result = html_history_fetcher(username, pages=pages)
        return {
            "posts": result["posts"] or (html_result["posts"] if wants_posts else []),
            "comments": result["comments"] or (html_result["comments"] if wants_comments else []),
        }
    return result
