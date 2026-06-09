from __future__ import annotations

from pathlib import Path

import pytest

from veda.errors import Blocked
from veda.reddit import _html_thread, thread, user


def test_fetch_thread_skips_json_when_disabled(monkeypatch) -> None:
    fixture = Path(__file__).parents[1] / "fixtures" / "thread.html"
    calls = {"json": 0}

    def json_tier(*args, **kwargs):
        calls["json"] += 1
        return None

    monkeypatch.delenv("VEDA_REDDIT_JSON_ENABLED", raising=False)
    monkeypatch.setattr(thread, "fetch_json_tier1", json_tier)
    monkeypatch.setattr(thread, "fetch_json_tier2", json_tier)
    monkeypatch.setattr(thread, "fetch_json_tier3", json_tier)
    monkeypatch.setattr(
        _html_thread,
        "fetch_thread",
        lambda raw_url, fetch=None: _html_thread.parse_thread_html(fixture.read_text()),
    )
    monkeypatch.setattr(thread, "fetch_rules", lambda subreddit: [])

    result = thread.fetch_thread("https://www.reddit.com/r/macapps/comments/abc123/post/")

    assert calls["json"] == 0
    assert result["meta"]["route"] == "html"


def test_fetch_thread_uses_json_when_enabled(monkeypatch) -> None:
    monkeypatch.setenv("VEDA_REDDIT_JSON_ENABLED", "1")
    monkeypatch.setattr(
        thread,
        "fetch_json_tier1",
        lambda url, **kwargs: [
            {"data": {"children": [{"data": {"title": "JSON", "subreddit": "macapps"}}]}},
            {"data": {"children": []}},
        ],
    )
    monkeypatch.setattr(thread, "fetch_rules", lambda subreddit: [])

    result = thread.fetch_thread("https://www.reddit.com/r/macapps/comments/abc123/post/")

    assert result["post"]["title"] == "JSON"
    assert result["meta"]["route"] == "json"


def test_fetch_user_skips_json_when_disabled(monkeypatch) -> None:
    calls = {"json": 0}

    def fake_json(url: str):
        calls["json"] += 1
        return {"data": {"children": []}}

    monkeypatch.delenv("VEDA_REDDIT_JSON_ENABLED", raising=False)
    monkeypatch.setattr(user, "fetch_json", fake_json)
    monkeypatch.setattr(
        user._html_user,
        "fetch_user_history",
        lambda username, pages=2: {
            "posts": [{"type": "post", "subreddit": "macapps", "title": "HTML post"}],
            "comments": [],
        },
    )

    result = user.fetch_user("alice", kinds=("submitted",), pages=1)

    assert calls["json"] == 0
    assert result["posts"][0]["title"] == "HTML post"


def test_reddit_reads_block_when_all_routes_disabled(monkeypatch) -> None:
    monkeypatch.setenv("VEDA_REDDIT_JSON_ENABLED", "0")
    monkeypatch.setenv("VEDA_REDDIT_HTML_ENABLED", "0")

    with pytest.raises(Blocked):
        thread.fetch_thread("https://www.reddit.com/r/macapps/comments/abc123/post/")
