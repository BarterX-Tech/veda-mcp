from __future__ import annotations

import anyio

from veda.mcp.server import BearerTokenAuth, BrowserHomePage


async def _call_app(
    app,
    accept: bytes,
    method: str = "GET",
    authorization: bytes | None = None,
) -> tuple[int, bytes, bytes]:
    messages = []

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message):
        messages.append(message)

    headers = [(b"accept", accept)]
    if authorization is not None:
        headers.append((b"authorization", authorization))

    await app(
        {
            "type": "http",
            "method": method,
            "path": "/mcp",
            "headers": headers,
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


def test_bearer_auth_blocks_mcp_without_token() -> None:
    async def fallback(scope, receive, send):
        await send({"type": "http.response.start", "status": 204, "headers": []})
        await send({"type": "http.response.body", "body": b""})

    home = BrowserHomePage(fallback, path="/mcp")
    app = BearerTokenAuth(fallback, token="secret", public_app=home)

    status, content_type, body = anyio.run(
        _call_app,
        app,
        b"application/json",
        "POST",
    )

    assert status == 401
    assert content_type == b"application/json"
    assert b"unauthorized" in body


def test_bearer_auth_allows_mcp_with_token() -> None:
    async def fallback(scope, receive, send):
        await send({"type": "http.response.start", "status": 204, "headers": []})
        await send({"type": "http.response.body", "body": b""})

    home = BrowserHomePage(fallback, path="/mcp")
    app = BearerTokenAuth(fallback, token="secret", public_app=home)

    status, _, _ = anyio.run(
        _call_app,
        app,
        b"application/json",
        "POST",
        b"Bearer secret",
    )

    assert status == 204


def test_bearer_auth_rejects_wrong_token() -> None:
    async def fallback(scope, receive, send):
        await send({"type": "http.response.start", "status": 204, "headers": []})
        await send({"type": "http.response.body", "body": b""})

    home = BrowserHomePage(fallback, path="/mcp")
    app = BearerTokenAuth(fallback, token="secret", public_app=home)

    status, _, body = anyio.run(
        _call_app,
        app,
        b"application/json",
        "POST",
        b"Bearer wrong-token",
    )

    assert status == 401
    assert b"unauthorized" in body
