from __future__ import annotations

import sys
import time
from typing import Any

from veda._transport import _html_tier2, fetch_html, fetch_json
from veda.config import get_scraping_config
from veda.errors import Blocked
from veda.reddit import _html_user
from veda.reddit._html_profile import extract_new_profile, extract_profile
from veda.reddit.types import UserResult

_USER_URL = "https://old.reddit.com/user/{u}/{kind}.json?limit=100&raw_json=1"
_PROFILE_URL = "https://old.reddit.com/user/{u}/"
_NEW_PROFILE_URL = "https://www.reddit.com/user/{u}/"
_SKIP_BODIES = {"[deleted]", "[removed]"}

_EMPTY_PROFILE = {
    "about_text": None,
    "external_urls": [],
    "post_karma": None,
    "comment_karma": None,
    "created_utc": None,
}


def _profile_from_page(username: str) -> dict:
    html = fetch_html(_PROFILE_URL.format(u=username))
    return extract_profile(html or "")


def _fetch_new_profile_html(url: str) -> str | None:
    html = _html_tier2(url)
    if isinstance(html, bytes):
        html = html.decode("utf-8", errors="replace")
    return html


def _augment_from_new_profile(username: str, profile: dict) -> dict:
    """Fill bio/links from the new-reddit profile page when old.reddit has none.

    New-style bios and social links never appear in old.reddit markup, so this
    costs one stealth fetch — only for users whose sidebar came back empty.
    """
    if profile.get("about_text") or profile.get("external_urls"):
        return profile
    try:
        html = _fetch_new_profile_html(_NEW_PROFILE_URL.format(u=username))
        new_profile = extract_new_profile(html or "")
    except Exception as exc:
        sys.stderr.write(f"[veda.reddit] new-profile fetch failed for {username}: {exc!r}\n")
        return profile
    return {
        **profile,
        "about_text": profile.get("about_text") or new_profile["about_text"],
        "external_urls": profile.get("external_urls") or new_profile["external_urls"],
    }


def _with_profile(username: str, posts: list, comments: list, profile: dict) -> UserResult:
    profile = _augment_from_new_profile(username, profile)
    return {
        "username": username,
        "bio": profile.get("about_text"),
        "links": profile.get("external_urls", []),
        "post_karma": profile.get("post_karma"),
        "comment_karma": profile.get("comment_karma"),
        "created_utc": profile.get("created_utc"),
        "posts": posts,
        "comments": comments,
    }


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
        return _with_profile(
            username,
            result["posts"] or (html_result["posts"] if wants_posts else []),
            result["comments"] or (html_result["comments"] if wants_comments else []),
            html_result.get("profile") or _EMPTY_PROFILE,
        )
    # JSON route satisfied the listings; the sidebar needs one profile-page read.
    return _with_profile(
        username, result["posts"], result["comments"], _profile_from_page(username)
    )
