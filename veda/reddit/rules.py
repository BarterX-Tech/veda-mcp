from __future__ import annotations

import lxml.html
import requests

from veda._transport import HEADERS, fetch_html
from veda.config import get_scraping_config
from veda.errors import Blocked
from veda.reddit.types import Rule


def _clean_subreddit(subreddit: str) -> str:
    sub = subreddit.strip().rstrip("/")
    return sub[2:] if sub.lower().startswith("r/") else sub


def _fetch_rules_json(subreddit: str) -> list[Rule]:
    response = requests.get(
        f"https://old.reddit.com/r/{subreddit}/about/rules.json",
        headers=HEADERS,
        timeout=15,
    )
    response.raise_for_status()
    payload = response.json()
    rules = payload.get("rules", []) if isinstance(payload, dict) else []
    return [dict(rule) for rule in rules]


def _parse_rules_html(html: str) -> list[Rule]:
    if not html:
        return []
    doc = lxml.html.fromstring(html)
    rules: list[Rule] = []
    seen: set[tuple[str, str]] = set()

    # Current old.reddit /about/rules/ markup: rule content lives in data
    # attributes on subreddit-rule-item divs.
    for node in doc.xpath(
        "//*[contains(concat(' ', normalize-space(@class), ' '), ' subreddit-rule-item ')]"
    ):
        short_name = " ".join((node.get("data-violation-reason") or "").split())
        description = " ".join((node.get("data-description") or "").split())
        key = (short_name, description)
        if (short_name or description) and key not in seen:
            seen.add(key)
            rules.append({"short_name": short_name, "description": description})
    if rules:
        return rules

    for node in doc.xpath(
        "//*[contains(concat(' ', normalize-space(@class), ' '), ' rule-item ')"
        " or contains(concat(' ', normalize-space(@class), ' '), ' rule ')]"
    ):
        title_nodes = node.xpath(
            ".//*[contains(concat(' ', normalize-space(@class), ' '), ' short-name ')"
            " or self::h2 or self::h3 or self::strong]"
        )
        desc_nodes = node.xpath(
            ".//*[contains(concat(' ', normalize-space(@class), ' '), ' description ')"
            " or contains(concat(' ', normalize-space(@class), ' '), ' md ')]"
        )
        short_name = " ".join(title_nodes[0].text_content().split()) if title_nodes else ""
        description = " ".join(desc_nodes[0].text_content().split()) if desc_nodes else ""
        key = (short_name, description)
        if (short_name or description) and key not in seen:
            seen.add(key)
            rules.append({"short_name": short_name, "description": description})
    return rules


def fetch_rules(
    subreddit: str,
    *,
    json_fetcher=_fetch_rules_json,
    html_fetcher=fetch_html,
) -> list[Rule]:
    config = get_scraping_config()
    sub = _clean_subreddit(subreddit)
    if config.reddit_json_enabled:
        try:
            rules = json_fetcher(sub)
            if rules:
                return rules
        except Exception:
            pass
    if not config.reddit_html_enabled:
        raise Blocked("Reddit HTML route is disabled")
    html = html_fetcher(f"https://old.reddit.com/r/{sub}/about/rules/")
    return _parse_rules_html(html or "")
