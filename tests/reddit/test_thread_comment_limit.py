from __future__ import annotations

from veda.reddit.thread import (
    _shape_html_result,
    _truncate_comment_tree,
    count_stats,
)


def _comment(cid: str, replies: list[dict] | None = None) -> dict:
    return {
        "id": cid,
        "author": "alice",
        "body": f"body {cid}",
        "score": 1,
        "created_utc": 0,
        "depth": 0,
        "parent_id": "",
        "permalink": "",
        "is_op": False,
        "edited": False,
        "gilded": 0,
        "replies": replies or [],
    }


def _more(count: int) -> dict:
    return {
        "_type": "more",
        "count": count,
        "depth": 0,
        "more_ids": [],
        "_note": f"{count} more replies collapsed.",
        "id": "",
        "author": "",
        "body": "",
        "score": 0,
        "created_utc": 0,
        "parent_id": "",
        "permalink": "",
        "is_op": False,
        "edited": False,
        "gilded": 0,
        "replies": [],
    }


def _nested_tree() -> list[dict]:
    # 5 real comments: c1 -> c2 -> c3, then c4 -> c5 at top level
    return [
        _comment("c1", [_comment("c2", [_comment("c3")])]),
        _comment("c4", [_comment("c5")]),
    ]


def test_truncate_keeps_exactly_limit_real_nodes_preorder() -> None:
    tree = _nested_tree()
    out = _truncate_comment_tree(tree, 3)
    assert count_stats(out)["fetched"] == 3
    # preorder => c1, c2, c3 kept; c4/c5 dropped
    assert out[0]["id"] == "c1"
    assert out[0]["replies"][0]["id"] == "c2"
    assert out[0]["replies"][0]["replies"][0]["id"] == "c3"
    assert len(out) == 1


def test_truncate_does_not_mutate_input() -> None:
    tree = _nested_tree()
    _truncate_comment_tree(tree, 2)
    assert count_stats(tree)["fetched"] == 5
    assert tree[0]["replies"][0]["replies"][0]["id"] == "c3"


def test_truncate_limit_larger_than_tree_returns_all() -> None:
    tree = _nested_tree()
    out = _truncate_comment_tree(tree, 100)
    assert count_stats(out)["fetched"] == 5


def test_truncate_limit_zero_returns_empty() -> None:
    out = _truncate_comment_tree(_nested_tree(), 0)
    assert out == []


def test_truncate_drops_trailing_more_markers_once_budget_exhausted() -> None:
    tree = [_comment("c1"), _comment("c2"), _more(9)]
    out = _truncate_comment_tree(tree, 2)
    assert count_stats(out)["fetched"] == 2
    assert all(c.get("_type") != "more" for c in out)


def test_shape_html_result_honors_comment_limit() -> None:
    html_result = {
        "post": {"subreddit": "macapps", "title": "t", "score": 1},
        "comments": [
            _comment("c1", [_comment("c2")]),
            _comment("c3"),
        ],
    }
    shaped = _shape_html_result(
        html_result,
        html_url="https://old.reddit.com/r/macapps/comments/abc/post/",
        json_url="https://old.reddit.com/r/macapps/comments/abc/post/.json",
        source_url="https://www.reddit.com/r/macapps/comments/abc/post/",
        comment_sort="top",
        rules_fetcher=lambda subreddit: [],
        comment_limit=2,
    )
    assert count_stats(shaped["comments"])["fetched"] == 2
    assert shaped["meta"]["comments_fetched"] == 2
