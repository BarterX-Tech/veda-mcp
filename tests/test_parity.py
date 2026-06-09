from __future__ import annotations

from pathlib import Path

import pytest

from veda.reddit import _html_thread
from veda.reddit.thread import _normalize_html_comments, extract_comments, extract_post

JSON_FIXTURE = [
    {
        "data": {
            "children": [
                {
                    "kind": "t3",
                    "data": {
                        "title": "My Clipboard Post",
                        "author": "Downtown-Art2865",
                        "subreddit": "macapps",
                        "subreddit_name_prefixed": "r/macapps",
                        "score": 42,
                        "upvote_ratio": 0.95,
                        "num_comments": 2,
                        "created_utc": 1710000000,
                        "permalink": "/r/macapps/comments/abc123/post/",
                        "url": "https://old.reddit.com/r/macapps/comments/abc123/post/",
                        "selftext": "post body here",
                        "link_flair_text": None,
                        "is_self": True,
                        "over_18": False,
                        "locked": False,
                        "archived": False,
                    },
                }
            ]
        }
    },
    {
        "data": {
            "children": [
                {
                    "kind": "t1",
                    "data": {
                        "id": "c1",
                        "author": "alice",
                        "body": "alice top comment",
                        "score": 7,
                        "created_utc": 1710000100,
                        "depth": 0,
                        "parent_id": "t3_abc123",
                        "permalink": "/r/macapps/comments/abc123/post/c1/",
                        "is_submitter": False,
                        "edited": False,
                        "gilded": 0,
                        "replies": "",
                    },
                }
            ]
        }
    },
]


@pytest.mark.xfail(reason="M1 makes the HTML thread parser field-complete.")
def test_json_and_html_thread_comment_field_parity() -> None:
    html = (Path(__file__).parent / "fixtures" / "thread.html").read_text()

    json_post = extract_post(JSON_FIXTURE[0]["data"]["children"][0])
    json_comment = extract_comments(JSON_FIXTURE[1])[0]
    html_result = _html_thread.parse_thread_html(html)
    html_comment = _normalize_html_comments(html_result["comments"])[0]

    assert set(html_result["post"]) == set(json_post)
    assert set(html_comment) == set(json_comment)
