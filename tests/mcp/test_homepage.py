from __future__ import annotations

import anyio

from veda.mcp.server import BrowserHomePage


async def _call_app(app, accept: bytes) -> tuple[int, bytes, bytes]:
    messages = []

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message):
        messages.append(message)

    await app(
        {
            "type": "http",
            "method": "GET",
            "path": "/mcp",
            "headers": [(b"accept", accept)],
        },
        receive,
        send,
    )
    start = messages[0]
    body = messages[1]
    headers = dict(start["headers"])
    return start["status"], headers.get(b"content-type", b""), body["body"]


def test_browser_get_mcp_returns_home_page() -> None:
    async def fallback(scope, receive, send):
        raise AssertionError("browser homepage request should not reach MCP app")

    status, content_type, body = anyio.run(
        _call_app,
        BrowserHomePage(fallback, path="/mcp"),
        b"text/html",
    )

    assert status == 200
    assert content_type == b"text/html; charset=utf-8"
    assert b"veda MCP server" in body
    assert b"fetch_thread" in body


def test_mcp_stream_get_is_delegated() -> None:
    called = {"value": False}

    async def fallback(scope, receive, send):
        called["value"] = True
        await send({"type": "http.response.start", "status": 204, "headers": []})
        await send({"type": "http.response.body", "body": b""})

    status, _, _ = anyio.run(
        _call_app,
        BrowserHomePage(fallback, path="/mcp"),
        b"text/event-stream",
    )

    assert status == 204
    assert called["value"] is True
