from __future__ import annotations

from veda._transport import fetch_html
from veda.config import get_scraping_config
from veda.errors import Blocked
from veda.reddit._html_profile import extract_profile
from veda.reddit.types import ProfileResult

_PROFILE_URL = "https://old.reddit.com/user/{u}/"


def fetch_profile(username: str) -> ProfileResult:
    if not get_scraping_config().reddit_html_enabled:
        raise Blocked("Reddit HTML route is disabled")
    html = fetch_html(_PROFILE_URL.format(u=username))
    parsed = extract_profile(html or "")
    return {
        "username": username,
        "bio": parsed["about_text"],
        "links": parsed["external_urls"],
    }
