from __future__ import annotations

from veda.reddit.thread import normalize_to_json_url


def test_share_links_resolve_before_json_normalization() -> None:
    captured: dict[str, str] = {}

    def resolver(url: str) -> str:
        captured["url"] = url
        return "https://www.reddit.com/r/macapps/comments/abc123/post/"

    normalized = normalize_to_json_url("https://reddit.com/s/shortcode?utm=1", resolver=resolver)

    assert captured["url"] == "https://reddit.com/s/shortcode"
    assert normalized == "https://old.reddit.com/r/macapps/comments/abc123/post.json"
