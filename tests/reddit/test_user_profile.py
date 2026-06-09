from __future__ import annotations

from veda.reddit import _html_profile, _html_user, profile, user

USER_HTML = """
<html><body>
  <div class="thing link" data-subreddit="macapps" data-timestamp="1710000000000"
       data-permalink="/r/macapps/comments/abc/post/">
    <span class="score unvoted" title="12">12 points</span>
    <a class="title">A useful app</a>
  </div>
  <div class="thing comment" data-subreddit="python" data-timestamp="1710000100000"
       data-permalink="/r/python/comments/def/thread/c1/">
    <span class="score unvoted" title="5">5 points</span>
    <div class="usertext-body"><div class="md"><p>helpful comment</p></div></div>
  </div>
  <div class="thing comment" data-subreddit="python">
    <div class="usertext-body"><div class="md"><p>[deleted]</p></div></div>
  </div>
  <span class="next-button"><a href="/user/alice/comments/?count=25&after=t3_next">next</a></span>
</body></html>
"""


PROFILE_HTML = """
<html><body>
  <div class="titlebox">
    <div class="usertext-body">
      Building tools at https://example.com/about.
      <a href="https://github.com/alice/project">GitHub</a>
      <a href="https://reddit.com/r/macapps">Reddit</a>
      <a href="https://github.com/alice/project">Duplicate</a>
    </div>
  </div>
</body></html>
"""


def test_parse_user_listing_posts_comments_and_after() -> None:
    parsed = _html_user.parse_user_listing(USER_HTML)

    assert parsed["after"] == "t3_next"
    assert parsed["items"][0] == {
        "type": "post",
        "subreddit": "macapps",
        "title": "A useful app",
        "score": 12,
        "created_utc": 1710000000,
        "permalink": "/r/macapps/comments/abc/post/",
    }
    assert parsed["items"][1]["type"] == "comment"
    assert parsed["items"][1]["body"] == "helpful comment"
    assert len(parsed["items"]) == 2


def test_fetch_user_falls_back_per_kind(monkeypatch) -> None:
    monkeypatch.setenv("VEDA_REDDIT_JSON_ENABLED", "1")

    def fake_json(url: str):
        if "/submitted.json" in url:
            return {
                "data": {
                    "children": [
                        {
                            "data": {
                                "subreddit": "macapps",
                                "title": "JSON post",
                                "score": 9,
                                "created_utc": 171,
                                "permalink": "/r/macapps/comments/a/post/",
                            }
                        }
                    ]
                }
            }
        return None

    monkeypatch.setattr(user, "fetch_json", fake_json)
    monkeypatch.setattr(
        user._html_user,
        "fetch_user_history",
        lambda username, pages=2: {
            "posts": [{"type": "post", "subreddit": "ignored", "title": "HTML post"}],
            "comments": [
                {
                    "type": "comment",
                    "subreddit": "python",
                    "body": "HTML comment",
                    "score": 3,
                    "created_utc": 172,
                    "permalink": "/r/python/comments/b/thread/c1/",
                }
            ],
        },
    )

    result = user.fetch_user("alice", pages=1)

    assert result["posts"][0]["title"] == "JSON post"
    assert result["comments"][0]["body"] == "HTML comment"


def test_extract_profile_dedupes_and_filters_reddit_urls() -> None:
    parsed = _html_profile.extract_profile(PROFILE_HTML)

    assert parsed["about_text"].startswith("Building tools")
    assert parsed["external_urls"] == [
        "https://github.com/alice/project",
        "https://example.com/about",
    ]


def test_fetch_profile_shapes_result(monkeypatch) -> None:
    monkeypatch.setattr(profile, "fetch_html", lambda url: PROFILE_HTML)

    result = profile.fetch_profile("alice")

    assert result["username"] == "alice"
    assert result["bio"].startswith("Building tools")
    assert "https://github.com/alice/project" in result["links"]
