from __future__ import annotations

import pytest

from veda.errors import Blocked
from veda.external import fetch


def test_fetch_url_tries_tier1_first_for_unknown_hosts() -> None:
    attempted: list[str] = []

    def fake_fetch(url: str, tier: str) -> str:
        attempted.append(tier)
        return "<article>" + ("tier one wins " * 20) + "</article>"

    doc = fetch.fetch_url(
        "https://example.dev/post",
        fetch_html=fake_fetch,
        robots_check=lambda url: True,
        security_check=lambda url: None,
    )

    assert attempted == ["tier1"]
    assert doc["route"] == "tier1"


def test_fetch_robots_text_requires_status_200(monkeypatch) -> None:
    class FakeResponse:
        def __init__(self, status_code: int, text: str) -> None:
            self.status_code = status_code
            self.text = text

    responses = {"https://x.com/robots.txt": FakeResponse(404, "<html>missing</html>")}

    def fake_get(url, **kwargs):
        return responses[url]

    monkeypatch.setattr(fetch.requests, "get", fake_get)
    assert fetch.fetch_robots_text("https://x.com/robots.txt") is None

    responses["https://x.com/robots.txt"] = FakeResponse(200, "User-agent: *\nDisallow: /private/")
    assert "Disallow" in fetch.fetch_robots_text("https://x.com/robots.txt")


def test_tier1_redirect_to_internal_host_is_blocked(monkeypatch) -> None:
    # A public URL must not be allowed to 302 into private/metadata space.
    class FakeResponse:
        def __init__(self, status_code, headers=None, text=""):
            self.status_code = status_code
            self.headers = headers or {}
            self.text = text
            self.is_redirect = status_code in (301, 302, 303, 307, 308)

    responses = {
        "https://evil.example/": FakeResponse(302, {"location": "http://169.254.169.254/meta"}),
    }

    def fake_get(url, **kwargs):
        assert kwargs.get("allow_redirects") is False
        return responses[url]

    monkeypatch.setattr(fetch.requests, "get", fake_get)

    with pytest.raises(Blocked):
        fetch.validated_tier1_fetch("https://evil.example/", security_check=lambda url: (
            (_ for _ in ()).throw(Blocked("internal"))
            if "169.254" in url
            else None
        ))


def test_tier1_redirect_to_public_host_is_followed(monkeypatch) -> None:
    class FakeResponse:
        def __init__(self, status_code, headers=None, text=""):
            self.status_code = status_code
            self.headers = headers or {}
            self.text = text
            self.is_redirect = status_code in (301, 302, 303, 307, 308)

    responses = {
        "https://a.example/": FakeResponse(301, {"location": "https://b.example/page"}),
        "https://b.example/page": FakeResponse(200, text="<article>" + "fine " * 50 + "</article>"),
    }

    def fake_get(url, **kwargs):
        return responses[url]

    monkeypatch.setattr(fetch.requests, "get", fake_get)

    html = fetch.validated_tier1_fetch("https://a.example/", security_check=lambda url: None)

    assert "fine" in html


def test_fetch_robots_text_returns_none_on_network_error(monkeypatch) -> None:
    def fake_get(url, **kwargs):
        raise OSError("connection refused")

    monkeypatch.setattr(fetch.requests, "get", fake_get)
    assert fetch.fetch_robots_text("https://x.com/robots.txt") is None


def test_github_raw_readme_url() -> None:
    assert (
        fetch.github_raw_readme_url("https://github.com/owner/repo")
        == "https://raw.githubusercontent.com/owner/repo/HEAD/README.md"
    )
    assert fetch.github_raw_readme_url("https://github.com/owner") is None
    # README route applies only to repo-root URLs, not issues/PRs/files.
    assert fetch.github_raw_readme_url("https://github.com/owner/repo/issues/5") is None


def test_extract_readable_text_prefers_article_and_caps() -> None:
    html = "<nav>menu</nav><article>" + ("real content " * 50) + "</article>"
    text = fetch.extract_readable_text(html, max_chars=80)

    assert text.startswith("real content")
    assert len(text) == 80


ARTICLE_HTML = """
<html>
<head><title>My Post - Example Blog</title></head>
<body>
<nav>Home About Subscribe</nav>
<article>
<h1>My Post</h1>
<p>First paragraph with enough words to be considered real readable content here.</p>
<p>Second paragraph that continues the article with even more meaningful text content.</p>
</article>
<footer>All rights reserved</footer>
</body>
</html>
"""


def test_extract_document_returns_title_and_separated_paragraphs() -> None:
    doc = fetch.extract_document(ARTICLE_HTML)

    assert doc["title"] and "My Post" in doc["title"]
    assert "First paragraph" in doc["text"]
    assert "Second paragraph" in doc["text"]
    # Blocks must stay separated markdown-style, not collapsed into one line.
    assert "\n\n" in doc["text"]
    assert doc["truncated"] is False
    # Navigation chrome must not leak into the extracted text.
    assert "Subscribe" not in doc["text"]


def test_extract_document_sets_truncated_flag_when_capped() -> None:
    doc = fetch.extract_document(ARTICLE_HTML, max_chars=40)

    assert len(doc["text"]) <= 40
    assert doc["truncated"] is True


def test_extract_document_handles_empty_html() -> None:
    doc = fetch.extract_document("")

    assert doc == {"text": "", "title": None, "truncated": False}


COMPONENT_SOUP_HTML = """
<html>
<head><title>Release Notes</title></head>
<body>
<nav><p>Home About Subscribe to our newsletter</p></nav>
<div class="t"><h1>Release Notes</h1></div>
<div class="t"><p>Intro paragraph with plenty of meaningful words describing the release.</p></div>
<div class="t"><h2>Section One: Foundation</h2></div>
<div class="t"><p>Body paragraph one with enough text to count as real content here.</p></div>
<div class="t"><h2>Section Two: Discovery</h2></div>
<div class="t"><p>Body paragraph two also has plenty of meaningful text content to keep.</p></div>
<div class="t"><h2>Empty Trailing Section</h2></div>
<footer><p>All rights reserved</p></footer>
</body>
</html>
"""

PARAGRAPHS_ONLY = (
    "Intro paragraph with plenty of meaningful words describing the release.\n\n"
    "Body paragraph one with enough text to count as real content here.\n\n"
    "Body paragraph two also has plenty of meaningful text content to keep."
)


def test_missing_heading_ratio_detects_dropped_headings() -> None:
    assert fetch.missing_heading_ratio(COMPONENT_SOUP_HTML, PARAGRAPHS_ONLY) > 0.5
    complete = (
        "# Release Notes\n## Section One: Foundation\n## Section Two: Discovery\n"
        "## Empty Trailing Section\n" + PARAGRAPHS_ONLY
    )
    assert fetch.missing_heading_ratio(COMPONENT_SOUP_HTML, complete) == 0.0


def test_rebuild_with_headings_reinserts_headings_in_order() -> None:
    text = fetch.rebuild_with_headings(COMPONENT_SOUP_HTML, PARAGRAPHS_ONLY)

    assert "## Section One: Foundation" in text
    assert "## Section Two: Discovery" in text
    # Document order preserved: heading before its section's paragraph.
    assert text.index("Section One") < text.index("Body paragraph one")
    assert text.index("Body paragraph one") < text.index("Section Two")
    # Nav/footer content stays out even though they contain <p> nodes.
    assert "Subscribe" not in text
    assert "rights reserved" not in text
    # Headings of sections with no kept content are dropped.
    assert "Empty Trailing Section" not in text


def test_extract_document_repairs_missing_headings(monkeypatch) -> None:
    monkeypatch.setattr(
        fetch.trafilatura, "extract", lambda html, **kwargs: PARAGRAPHS_ONLY
    )

    doc = fetch.extract_document(COMPONENT_SOUP_HTML)

    assert "## Section One: Foundation" in doc["text"]
    assert "Body paragraph two" in doc["text"]


def test_fetch_url_result_includes_title_and_truncated() -> None:
    doc = fetch.fetch_url(
        "https://example.dev/post",
        fetch_html=lambda url, tier: ARTICLE_HTML,
        robots_check=lambda url: True,
        security_check=lambda url: None,
    )

    assert doc["title"] and "My Post" in doc["title"]
    assert doc["truncated"] is False
    assert "First paragraph" in doc["text"]


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
        raw_fetcher=lambda url: None,
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
        "title": None,
        "truncated": False,
    }


def test_fetch_url_blocks_when_robots_disallow() -> None:
    with pytest.raises(Blocked):
        fetch.fetch_url(
            "https://example.com/private",
            fetch_html=lambda url, tier: "<article>ok</article>",
            robots_check=lambda url: False,
            security_check=lambda url: None,
        )


def test_validate_blocks_cloud_metadata_ip() -> None:
    with pytest.raises(Blocked):
        fetch.validate_public_http_url("http://169.254.169.254/latest/meta-data/")


def test_validate_blocks_host_resolving_to_metadata_ip() -> None:
    def resolver(host, port, type):
        return [(None, None, None, "", ("169.254.169.254", port))]

    with pytest.raises(Blocked):
        fetch.validate_public_http_url("https://innocent.example/", resolver=resolver)


def test_validate_blocks_private_and_ula_literals() -> None:
    for url in ("http://10.0.0.1/", "http://192.168.1.1/", "http://[fd00::1]/"):
        with pytest.raises(Blocked):
            fetch.validate_public_http_url(url)


def test_validate_allows_public_host() -> None:
    def resolver(host, port, type):
        return [(None, None, None, "", ("93.184.216.34", port))]

    # Should not raise.
    fetch.validate_public_http_url("https://example.com/page", resolver=resolver)


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
