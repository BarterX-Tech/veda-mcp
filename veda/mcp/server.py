from __future__ import annotations

import os

from mcp.server.fastmcp import FastMCP

from veda.mcp import tools


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

    return server


def main() -> None:
    server = create_server()
    host = os.environ.get("VEDA_HOST", "127.0.0.1")
    port = int(os.environ.get("VEDA_PORT", "8765"))
    server.settings.host = host
    server.settings.port = port
    server.run(transport="streamable-http")


if __name__ == "__main__":
    main()
