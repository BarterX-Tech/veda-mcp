from __future__ import annotations

from collections.abc import Callable
from typing import Any

from veda import external as external_fetch
from veda.errors import VedaError
from veda.reddit import profile as reddit_profile
from veda.reddit import rules as reddit_rules
from veda.reddit import thread as reddit_thread
from veda.reddit import user as reddit_user


class ToolError(Exception):
    def __init__(self, message: str, *, code: str = "tool_error") -> None:
        super().__init__(message)
        self.code = code


def _tuple_arg(value: Any, default: tuple[str, ...]) -> tuple[str, ...]:
    if value is None:
        return default
    if isinstance(value, str):
        return (value,)
    return tuple(value)


async def _fetch_thread(args: dict[str, Any]) -> Any:
    return reddit_thread.fetch_thread(
        str(args["url"]),
        comment_limit=int(args.get("comment_limit", 500)),
        comment_sort=str(args.get("comment_sort", "top")),
    )


async def _fetch_user(args: dict[str, Any]) -> Any:
    return reddit_user.fetch_user(
        str(args["username"]),
        kinds=_tuple_arg(args.get("kinds"), ("submitted", "comments")),
        pages=int(args.get("pages", 2)),
    )


async def _fetch_profile(args: dict[str, Any]) -> Any:
    return reddit_profile.fetch_profile(str(args["username"]))


async def _fetch_rules(args: dict[str, Any]) -> Any:
    return reddit_rules.fetch_rules(str(args["subreddit"]))


async def _fetch_url(args: dict[str, Any]) -> Any:
    return external_fetch.fetch_url(
        str(args["url"]),
        max_chars=int(args.get("max_chars", 20000)),
    )


TOOL_HANDLERS: dict[str, Callable[[dict[str, Any]], Any]] = {
    "fetch_thread": _fetch_thread,
    "fetch_user": _fetch_user,
    "fetch_profile": _fetch_profile,
    "fetch_rules": _fetch_rules,
    "fetch_url": _fetch_url,
}


async def call_tool(name: str, arguments: dict[str, Any] | None = None) -> Any:
    if name not in TOOL_HANDLERS:
        raise ToolError(f"Unknown tool: {name}", code="unknown_tool")
    try:
        return await TOOL_HANDLERS[name](arguments or {})
    except VedaError as exc:
        raise ToolError(str(exc), code=exc.code) from exc
