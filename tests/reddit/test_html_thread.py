from __future__ import annotations

from pathlib import Path

from veda.reddit import _html_thread


def test_parse_thread_html_extracts_field_complete_post_and_comments() -> None:
    html = (Path(__file__).parents[1] / "fixtures" / "thread.html").read_text()
    result = _html_thread.parse_thread_html(html)

    assert result["post"]["author"] == "Downtown-Art2865"
    assert result["post"]["subreddit"] == "macapps"
    assert result["post"]["score"] == 42
    assert result["post"]["created_utc"] == 1710000000
    assert result["post"]["num_comments"] == 2
    assert result["comments"][0]["author"] == "alice"
    assert result["comments"][0]["body"] == "alice top comment"
    assert result["comments"][0]["id"] == "c1"
    assert result["comments"][0]["score"] == 7
    assert result["comments"][0]["created_utc"] == 1710000100
    assert result["comments"][0]["is_op"] is False
    assert result["comments"][0]["replies"][0]["author"] == "Downtown-Art2865"
    assert result["comments"][0]["replies"][0]["id"] == "c2"
    assert result["comments"][0]["replies"][0]["is_op"] is True
    assert result["comments"][0]["replies"][0]["edited"] is True
    assert result["comments"][0]["replies"][0]["gilded"] == 1
