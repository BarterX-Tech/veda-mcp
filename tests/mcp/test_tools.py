from __future__ import annotations

import asyncio

import pytest

from veda import health
from veda.errors import Blocked
from veda.mcp import tools
from veda.mcp.server import create_server


def test_tool_registry_has_five_tools() -> None:
    assert set(tools.TOOL_HANDLERS) == {
        "fetch_thread",
        "fetch_user",
        "fetch_profile",
        "fetch_rules",
        "fetch_url",
        "health_status",
    }


def test_call_tool_delegates_to_core(monkeypatch) -> None:
    health.reset()
    monkeypatch.setattr(
        tools.reddit_thread,
        "fetch_thread",
        lambda url, comment_limit=500, comment_sort="top": {
            "post": {"title": "T"},
            "comments": [],
            "subreddit_rules": [],
            "meta": {"route": "html"},
        },
    )

    result = asyncio.run(
        tools.call_tool(
            "fetch_thread",
            {"url": "https://old.reddit.com/r/x/comments/abc/t/", "comment_limit": 1},
        )
    )

    assert result["post"]["title"] == "T"
    snapshot = health.snapshot()
    assert snapshot["tools"]["fetch_thread"]["successes"] == 1
    assert snapshot["routes"]["html"] == 1


def test_call_tool_maps_veda_error(monkeypatch) -> None:
    health.reset()
    def fail(url, max_chars=20000):
        raise Blocked("nope")

    monkeypatch.setattr(tools.external_fetch, "fetch_url", fail)

    with pytest.raises(tools.ToolError) as exc:
        asyncio.run(tools.call_tool("fetch_url", {"url": "https://example.com"}))

    assert exc.value.code == "blocked"
    snapshot = health.snapshot()
    assert snapshot["tools"]["fetch_url"]["errors"] == 1
    assert snapshot["tools"]["fetch_url"]["error_codes"]["blocked"] == 1


def test_fastmcp_server_lists_and_calls_all_tools(monkeypatch) -> None:
    monkeypatch.setattr(
        tools.reddit_thread,
        "fetch_thread",
        lambda url, comment_limit=500, comment_sort="top": {
            "post": {},
            "comments": [],
            "subreddit_rules": [],
            "meta": {},
        },
    )
    monkeypatch.setattr(
        tools.reddit_user,
        "fetch_user",
        lambda username, kinds=("submitted", "comments"), pages=2: {"posts": [], "comments": []},
    )
    monkeypatch.setattr(
        tools.reddit_profile,
        "fetch_profile",
        lambda username: {"username": username, "bio": None, "links": []},
    )
    monkeypatch.setattr(tools.reddit_rules, "fetch_rules", lambda subreddit: [])
    monkeypatch.setattr(
        tools.external_fetch,
        "fetch_url",
        lambda url, max_chars=20000: {
            "url": url,
            "status": 200,
            "route": "tier1",
            "content_type": "text/html",
            "text": "ok",
        },
    )

    async def exercise() -> None:
        server = create_server()
        listed = await server.list_tools()
        assert {tool.name for tool in listed} == set(tools.TOOL_HANDLERS)
        calls = {
            "fetch_thread": {"url": "https://old.reddit.com/r/x/comments/abc/t/"},
            "fetch_user": {"username": "alice"},
            "fetch_profile": {"username": "alice"},
            "fetch_rules": {"subreddit": "macapps"},
            "fetch_url": {"url": "https://example.com"},
            "health_status": {},
        }
        for name, arguments in calls.items():
            result = await server.call_tool(name, arguments)
            assert result

    asyncio.run(exercise())
