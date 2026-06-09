from __future__ import annotations

import pytest

from veda.errors import Blocked
from veda.external import fetch


def test_route_start_tier() -> None:
    assert fetch.route_start_tier("https://github.com/owner/repo") == "tier1"
    assert fetch.route_start_tier("https://owner.github.io/") == "tier1"
    assert fetch.route_start_tier("https://example.dev/") == "tier2"


def test_github_raw_readme_url() -> None:
    assert (
        fetch.github_raw_readme_url("https://github.com/owner/repo")
        == "https://raw.githubusercontent.com/owner/repo/main/README.md"
    )
    assert fetch.github_raw_readme_url("https://github.com/owner") is None


def test_extract_readable_text_prefers_article_and_caps() -> None:
    html = "<nav>menu</nav><article>" + ("real content " * 50) + "</article>"
    text = fetch.extract_readable_text(html, max_chars=80)

    assert text.startswith("real content")
    assert len(text) == 80


def test_robots_allowed_respects_disallow() -> None:
    robots = "User-agent: *\nDisallow: /private/"

    assert (
        fetch.robots_allowed("https://x.com/private/page", fetch_robots=lambda url: robots)
        is False
    )
    assert (
        fetch.robots_allowed("https://x.com/public/page", fetch_robots=lambda url: robots)
        is True
    )


def test_fetch_url_escalates_until_readable_text() -> None:
    pages = {
        "tier1": "<p>thin</p>",
        "tier2": "<article>" + ("good content " * 20) + "</article>",
    }

    doc = fetch.fetch_url(
        "https://github.com/owner/repo",
        fetch_html=lambda url, tier: pages[tier],
        robots_check=lambda url: True,
        security_check=lambda url: None,
    )

    assert doc["route"] == "tier2"
    assert "good content" in doc["text"]


def test_fetch_url_uses_github_raw_readme() -> None:
    doc = fetch.fetch_url(
        "https://github.com/owner/repo",
        raw_fetcher=lambda url: "README markdown",
        robots_check=lambda url: True,
        security_check=lambda url: None,
    )

    assert doc == {
        "url": "https://github.com/owner/repo",
        "status": 200,
        "route": "github_raw",
        "content_type": "text/markdown",
        "text": "README markdown",
    }


def test_fetch_url_blocks_when_robots_disallow() -> None:
    with pytest.raises(Blocked):
        fetch.fetch_url(
            "https://example.com/private",
            fetch_html=lambda url, tier: "<article>ok</article>",
            robots_check=lambda url: False,
            security_check=lambda url: None,
        )


def test_fetch_url_blocks_localhost_target() -> None:
    with pytest.raises(Blocked):
        fetch.fetch_url(
            "http://127.0.0.1:8080/private",
            fetch_html=lambda url, tier: "<article>ok</article>",
            robots_check=lambda url: True,
        )


def test_fetch_url_blocks_private_dns_target() -> None:
    def resolver(host, port, type):
        return [(None, None, None, "", ("192.168.1.20", port))]

    with pytest.raises(Blocked):
        fetch.fetch_url(
            "https://internal.example.test/private",
            fetch_html=lambda url, tier: "<article>ok</article>",
            robots_check=lambda url: True,
            security_check=lambda url: fetch.validate_public_http_url(url, resolver=resolver),
        )
