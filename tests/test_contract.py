from __future__ import annotations

import json
from pathlib import Path

from veda.external.fetch import fetch_url
from veda.reddit import fetch_rules, fetch_thread, fetch_user


def test_thread_result_is_canonical_and_json_serializable(monkeypatch) -> None:
    from veda.reddit import _html_thread, thread

    fixture = Path(__file__).parent / "fixtures" / "thread.html"

    monkeypatch.setattr(thread, "fetch_json_tier1", lambda url, **kw: None)
    monkeypatch.setattr(thread, "fetch_json_tier2", lambda permalink, **kw: None)
    monkeypatch.setattr(thread, "fetch_json_tier3", lambda permalink, **kw: None)
    monkeypatch.setattr(
        _html_thread,
        "fetch_thread",
        lambda raw_url, fetch=None: _html_thread.parse_thread_html(fixture.read_text()),
    )
    monkeypatch.setattr(thread, "fetch_rules", lambda subreddit: [])

    result = fetch_thread("https://www.reddit.com/r/macapps/comments/abc123/post/")

    assert set(result) == {"post", "comments", "subreddit_rules", "meta"}
    assert result["meta"]["route"] == "html"
    assert result["post"]["subreddit_prefixed"] == "r/macapps"
    assert result["comments"][0]["replies"][0]["depth"] == 1
    json.dumps(result)


def test_other_core_results_are_json_serializable(monkeypatch) -> None:
    from veda.external import fetch as external_fetch
    from veda.reddit import rules, user

    monkeypatch.setattr(user, "fetch_json", lambda url: None)
    profile_html = (
        "<html><body><div class='titlebox'><div class='usertext-body'>"
        "hello https://example.com</div></div></body></html>"
    )
    monkeypatch.setattr(
        user._html_user,
        "fetch_user_history",
        lambda username, pages=2, fetch_html=None: {
            "posts": [],
            "comments": [],
            "profile": user.extract_profile(profile_html),
        },
    )
    monkeypatch.setattr(
        rules,
        "_fetch_rules_json",
        lambda subreddit: [{"short_name": "Be kind", "description": "No abuse"}],
    )
    monkeypatch.setattr(external_fetch, "robots_allowed", lambda url, fetch_robots: True)
    monkeypatch.setattr(
        external_fetch,
        "_default_fetch_html",
        lambda url, tier: "<article>Readable page text " * 20,
    )

    user_result = fetch_user("alice")
    assert user_result["username"] == "alice"
    assert user_result["bio"].startswith("hello")
    assert "https://example.com" in user_result["links"]

    results = [
        user_result,
        fetch_rules("macapps"),
        fetch_url("https://example.com", max_chars=80, security_check=lambda url: None),
    ]

    for result in results:
        json.dumps(result)
