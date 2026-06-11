from __future__ import annotations

from veda.reddit import _html_profile, _html_user, user

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
    <h1>alice</h1>
    <span class="karma">135</span> post karma
    <span class="karma comment-karma">86</span> comment karma
    <span class="age">since
      <time datetime="2026-02-26T04:50:09+00:00">3 months</time></span>
    <div class="usertext-body">
      Building tools at https://example.com/about.
      <a href="https://github.com/alice/project">GitHub</a>
      <a href="https://reddit.com/r/macapps">Reddit</a>
      <a href="https://github.com/alice/project">Duplicate</a>
    </div>
  </div>
</body></html>
"""


NEW_PROFILE_HTML = """
<html><body>
<div data-testid="profile-details-content-wrapper">
  <div data-testid="profile-description-wrapper">
    <p data-testid="profile-description">
      indie dev | writing at example.io
    </p>
  </div>
  <faceplate-tracker source="profile" action="click" noun="social_link"
    data-faceplate-tracking-context=
      '{"social_link":{"type":"TWITTER","url":"https://twitter.com/alice","name":"a"}}'>
    <a href="https://twitter.com/alice" target="_blank">alice</a>
  </faceplate-tracker>
  <faceplate-tracker source="profile" action="click" noun="social_link"
    data-faceplate-tracking-context=
      '{"social_link":{"type":"CUSTOM","url":"https://example.io","name":"S","position":1}}'>
    <a href="https://example.io" target="_blank">My Site</a>
  </faceplate-tracker>
</div>
</body></html>
"""


def test_extract_new_profile_reads_bio_and_social_links() -> None:
    parsed = _html_profile.extract_new_profile(NEW_PROFILE_HTML)

    assert parsed["about_text"] == "indie dev | writing at example.io"
    assert parsed["external_urls"] == ["https://twitter.com/alice", "https://example.io"]


def test_extract_new_profile_handles_empty_html() -> None:
    parsed = _html_profile.extract_new_profile("")

    assert parsed == {"about_text": None, "external_urls": []}


def test_fetch_user_augments_from_new_profile_when_sidebar_empty(monkeypatch) -> None:
    monkeypatch.setattr(
        user._html_user,
        "fetch_user_history",
        lambda username, pages=2: {
            "posts": [],
            "comments": [],
            "profile": {
                "about_text": None,
                "external_urls": [],
                "post_karma": 1730,
                "comment_karma": 2890,
                "created_utc": 1605017799.0,
            },
        },
    )
    fetched_urls: list[str] = []

    def fake_new_profile(url: str):
        fetched_urls.append(url)
        return NEW_PROFILE_HTML

    monkeypatch.setattr(user, "_fetch_new_profile_html", fake_new_profile)

    result = user.fetch_user("alice", pages=1)

    assert fetched_urls == ["https://www.reddit.com/user/alice/"]
    assert result["bio"] == "indie dev | writing at example.io"
    assert result["links"] == ["https://twitter.com/alice", "https://example.io"]
    # Sidebar stats are kept.
    assert result["post_karma"] == 1730
    assert result["created_utc"] == 1605017799.0


def test_fetch_user_skips_new_profile_fetch_when_sidebar_has_bio(monkeypatch) -> None:
    monkeypatch.setattr(
        user._html_user,
        "fetch_user_history",
        lambda username, pages=2: {
            "posts": [],
            "comments": [],
            "profile": {
                "about_text": "old-style bio",
                "external_urls": ["https://example.com"],
                "post_karma": 1,
                "comment_karma": 2,
                "created_utc": 3.0,
            },
        },
    )

    def explode(url: str):
        raise AssertionError("new-profile fetch should not happen")

    monkeypatch.setattr(user, "_fetch_new_profile_html", explode)

    result = user.fetch_user("alice", pages=1)

    assert result["bio"] == "old-style bio"


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


def test_parse_user_listing_reads_time_datetime_when_no_data_timestamp() -> None:
    # Current old.reddit user pages carry <time datetime=...> instead of a
    # data-timestamp attribute on the thing div.
    html = """
    <html><body>
      <div class="thing comment" data-subreddit="SaaS"
           data-permalink="/r/SaaS/comments/abc/thread/c9/">
        <span class="score unvoted" title="3">3 points</span>
        <time datetime="2026-02-26T04:50:09+00:00">2 days ago</time>
        <div class="usertext-body"><div class="md"><p>a real comment body</p></div></div>
      </div>
    </body></html>
    """
    parsed = _html_user.parse_user_listing(html)

    from datetime import datetime

    expected = datetime.fromisoformat("2026-02-26T04:50:09+00:00").timestamp()
    assert parsed["items"][0]["created_utc"] == expected


LISTING_WITH_SIDEBAR_HTML = """
<html><body>
  <div class="titlebox">
    <h1>alice</h1>
    <span class="karma">135</span>
    <span class="karma comment-karma">86</span>
    <span class="age"><time datetime="2026-02-26T04:50:09+00:00">3 months</time></span>
    <div class="usertext-body">Maker of things at https://example.com/about.</div>
  </div>
  <div class="thing comment" data-subreddit="python" data-timestamp="1710000100000"
       data-permalink="/r/python/comments/def/thread/c1/">
    <span class="score unvoted" title="5">5 points</span>
    <div class="usertext-body"><div class="md"><p>helpful comment</p></div></div>
  </div>
</body></html>
"""


def test_fetch_user_history_extracts_profile_from_listing_sidebar() -> None:
    result = _html_user.fetch_user_history(
        "alice", pages=1, fetch_html=lambda url: LISTING_WITH_SIDEBAR_HTML
    )

    assert result["comments"][0]["body"] == "helpful comment"
    profile = result["profile"]
    assert profile["post_karma"] == 135
    assert profile["comment_karma"] == 86
    assert profile["created_utc"] is not None
    assert profile["about_text"].startswith("Maker of things")
    assert "https://example.com/about" in profile["external_urls"]


def test_fetch_user_returns_merged_profile_fields(monkeypatch) -> None:
    monkeypatch.setattr(
        user._html_user,
        "fetch_user_history",
        lambda username, pages=2: {
            "posts": [],
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
            "profile": {
                "about_text": "Maker of things",
                "external_urls": ["https://example.com/about"],
                "post_karma": 135,
                "comment_karma": 86,
                "created_utc": 1772081409.0,
            },
        },
    )

    result = user.fetch_user("alice", pages=1)

    assert result["username"] == "alice"
    assert result["bio"] == "Maker of things"
    assert result["links"] == ["https://example.com/about"]
    assert result["post_karma"] == 135
    assert result["comment_karma"] == 86
    assert result["created_utc"] == 1772081409.0
    assert result["comments"][0]["body"] == "HTML comment"


def test_fetch_user_fetches_profile_page_when_json_route_satisfies(monkeypatch) -> None:
    monkeypatch.setenv("VEDA_REDDIT_JSON_ENABLED", "1")

    def fake_json(url: str):
        children = [
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
        if "/submitted.json" in url:
            return {"data": {"children": children}}
        if "/comments.json" in url:
            children[0]["data"]["body"] = "json comment"
            return {"data": {"children": children}}
        return None

    monkeypatch.setattr(user, "fetch_json", fake_json)
    monkeypatch.setattr(user, "fetch_html", lambda url: PROFILE_HTML)

    result = user.fetch_user("alice", pages=1)

    assert result["posts"][0]["title"] == "JSON post"
    assert result["post_karma"] == 135
    assert result["bio"].startswith("Building tools")


def test_fetch_user_falls_back_per_kind(monkeypatch) -> None:
    monkeypatch.setenv("VEDA_REDDIT_JSON_ENABLED", "1")
    monkeypatch.setattr(user, "_fetch_new_profile_html", lambda url: None)

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


def test_extract_profile_reads_karma_and_created() -> None:
    from datetime import datetime

    parsed = _html_profile.extract_profile(PROFILE_HTML)

    assert parsed["post_karma"] == 135
    assert parsed["comment_karma"] == 86
    expected = datetime.fromisoformat("2026-02-26T04:50:09+00:00").timestamp()
    assert parsed["created_utc"] == expected


def test_extract_profile_karma_fields_none_when_missing() -> None:
    parsed = _html_profile.extract_profile("<html><body><p>nothing here</p></body></html>")

    assert parsed["post_karma"] is None
    assert parsed["comment_karma"] is None
    assert parsed["created_utc"] is None


