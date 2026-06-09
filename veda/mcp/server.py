from __future__ import annotations

import os
from collections.abc import Awaitable, Callable
from hmac import compare_digest
from typing import Any

from mcp.server.fastmcp import FastMCP

from veda.mcp import tools

Receive = Callable[[], Awaitable[dict[str, Any]]]
Send = Callable[[dict[str, Any]], Awaitable[None]]
AsgiApp = Callable[[dict[str, Any], Receive, Send], Awaitable[None]]


HOME_HTML = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>veda MCP server</title>
  <style>
    :root {
      color-scheme: light dark;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }
    body { margin: 0; padding: 48px 24px; background: Canvas; color: CanvasText; }
    main { max-width: 760px; margin: 0 auto; }
    h1 { font-size: 32px; margin: 0 0 8px; }
    p { line-height: 1.55; }
    code {
      background: color-mix(in srgb, CanvasText 10%, Canvas);
      padding: 2px 6px;
      border-radius: 4px;
    }
    ul { padding-left: 22px; }
    .panel {
      border: 1px solid color-mix(in srgb, CanvasText 22%, Canvas);
      border-radius: 8px;
      padding: 18px;
      margin-top: 20px;
    }
  </style>
</head>
<body>
  <main>
    <h1>veda MCP server</h1>
    <p>veda is running. This browser page is only a friendly status surface for humans.</p>
    <div class="panel">
      <p><strong>MCP endpoint:</strong> <code>/mcp</code></p>
      <p>Connect with an MCP Streamable HTTP client and call the tools below.</p>
      <ul>
        <li><code>fetch_thread</code></li>
        <li><code>fetch_user</code></li>
        <li><code>fetch_profile</code></li>
        <li><code>fetch_rules</code></li>
        <li><code>fetch_url</code></li>
        <li><code>health_status</code></li>
      </ul>
    </div>
  </main>
</body>
</html>
"""


class BrowserHomePage:
    def __init__(self, app: AsgiApp, *, path: str, html: str = HOME_HTML) -> None:
        self.app = app
        self.path = path
        self.body = html.encode()

    async def __call__(self, scope: dict[str, Any], receive: Receive, send: Send) -> None:
        if self._is_browser_home_request(scope):
            await send(
                {
                    "type": "http.response.start",
                    "status": 200,
                    "headers": [
                        (b"content-type", b"text/html; charset=utf-8"),
                        (b"content-length", str(len(self.body)).encode()),
                    ],
                }
            )
            await send({"type": "http.response.body", "body": self.body})
            return
        await self.app(scope, receive, send)

    def _is_browser_home_request(self, scope: dict[str, Any]) -> bool:
        if scope.get("type") != "http":
            return False
        if scope.get("method") != "GET" or scope.get("path") != self.path:
            return False
        headers = {key.lower(): value for key, value in scope.get("headers", [])}
        accept = headers.get(b"accept", b"").decode(errors="ignore")
        return "text/html" in accept and "text/event-stream" not in accept


class BearerTokenAuth:
    def __init__(self, app: AsgiApp, *, token: str | None, public_app: BrowserHomePage) -> None:
        self.app = app
        self.token = token
        self.public_app = public_app

    async def __call__(self, scope: dict[str, Any], receive: Receive, send: Send) -> None:
        if not self.token or scope.get("type") != "http":
            await self.public_app(scope, receive, send)
            return
        if self.public_app._is_browser_home_request(scope):
            await self.public_app(scope, receive, send)
            return
        if self._authorized(scope):
            await self.app(scope, receive, send)
            return
        body = b'{"error":"unauthorized"}'
        await send(
            {
                "type": "http.response.start",
                "status": 401,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"content-length", str(len(body)).encode()),
                    (b"www-authenticate", b"Bearer"),
                ],
            }
        )
        await send({"type": "http.response.body", "body": body})

    def _authorized(self, scope: dict[str, Any]) -> bool:
        headers = {key.lower(): value for key, value in scope.get("headers", [])}
        auth = headers.get(b"authorization", b"").decode(errors="ignore")
        prefix = "Bearer "
        if not auth.startswith(prefix):
            return False
        return compare_digest(auth[len(prefix) :], self.token or "")


def create_server() -> FastMCP:
    server = FastMCP("veda")

    @server.tool()
    async def fetch_thread(
        url: str,
        comment_limit: int = 500,
        comment_sort: str = "top",
    ) -> dict:
        return await tools.call_tool(
            "fetch_thread",
            {
                "url": url,
                "comment_limit": comment_limit,
                "comment_sort": comment_sort,
            },
        )

    @server.tool()
    async def fetch_user(
        username: str,
        kinds: tuple[str, ...] = ("submitted", "comments"),
        pages: int = 2,
    ) -> dict:
        return await tools.call_tool(
            "fetch_user",
            {"username": username, "kinds": kinds, "pages": pages},
        )

    @server.tool()
    async def fetch_profile(username: str) -> dict:
        return await tools.call_tool("fetch_profile", {"username": username})

    @server.tool()
    async def fetch_rules(subreddit: str) -> list[dict]:
        return await tools.call_tool("fetch_rules", {"subreddit": subreddit})

    @server.tool()
    async def fetch_url(url: str, max_chars: int = 20000) -> dict:
        return await tools.call_tool("fetch_url", {"url": url, "max_chars": max_chars})

    @server.tool()
    async def health_status() -> dict:
        return await tools.call_tool("health_status", {})

    _install_browser_home_page(server)
    return server


def _install_browser_home_page(server: FastMCP) -> None:
    original = server.streamable_http_app

    def streamable_http_app():
        mcp_app = original()
        home_app = BrowserHomePage(mcp_app, path=server.settings.streamable_http_path)
        return BearerTokenAuth(
            mcp_app,
            token=_auth_token(),
            public_app=home_app,
        )

    server.streamable_http_app = streamable_http_app


def _auth_token() -> str | None:
    if os.environ.get("VEDA_AUTH_TOKEN"):
        return os.environ["VEDA_AUTH_TOKEN"]
    token_file = os.environ.get("VEDA_TOKEN_FILE", "run/veda-token")
    try:
        token = open(token_file).read().strip()
    except OSError:
        return None
    return token or None


def main() -> None:
    server = create_server()
    host = os.environ.get("VEDA_HOST", "127.0.0.1")
    port = int(os.environ.get("VEDA_PORT", "8765"))
    server.settings.host = host
    server.settings.port = port
    server.run(transport="streamable-http")


if __name__ == "__main__":
    main()
