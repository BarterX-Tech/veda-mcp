from __future__ import annotations

from pathlib import Path

from veda.reddit import _html_thread


def test_parse_thread_html_keeps_origin_shape_for_m0() -> None:
    html = (Path(__file__).parents[1] / "fixtures" / "thread.html").read_text()
    result = _html_thread.parse_thread_html(html)

    assert result["post"]["author"] == "Downtown-Art2865"
    assert result["post"]["subreddit"] == "macapps"
    assert result["comments"][0]["author"] == "alice"
    assert result["comments"][0]["body"] == "alice top comment"
    assert result["comments"][0]["replies"][0]["author"] == "Downtown-Art2865"
