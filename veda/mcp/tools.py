from __future__ import annotations

import asyncio
import time
from collections.abc import Callable
from typing import Any

from veda import external as external_fetch
from veda import health
from veda.errors import VedaError
from veda.reddit import rules as reddit_rules
from veda.reddit import thread as reddit_thread
from veda.reddit import user as reddit_user
from veda.security import SlidingWindowRateLimiter


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


def _fetch_thread(args: dict[str, Any]) -> Any:
    return reddit_thread.fetch_thread(
        str(args["url"]),
        comment_limit=int(args.get("comment_limit", 500)),
        comment_sort=str(args.get("comment_sort", "top")),
    )


def _fetch_user(args: dict[str, Any]) -> Any:
    return reddit_user.fetch_user(
        str(args["username"]),
        kinds=_tuple_arg(args.get("kinds"), ("submitted", "comments")),
        pages=int(args.get("pages", 2)),
    )


def _fetch_rules(args: dict[str, Any]) -> Any:
    return reddit_rules.fetch_rules(str(args["subreddit"]))


def _fetch_url(args: dict[str, Any]) -> Any:
    return external_fetch.fetch_url(
        str(args["url"]),
        max_chars=int(args.get("max_chars", 20000)),
    )


def _health_status(args: dict[str, Any]) -> Any:
    return health.snapshot()


TOOL_HANDLERS: dict[str, Callable[[dict[str, Any]], Any]] = {
    "fetch_thread": _fetch_thread,
    "fetch_user": _fetch_user,
    "fetch_rules": _fetch_rules,
    "fetch_url": _fetch_url,
    "health_status": _health_status,
}

TOOL_RATE_LIMITS: dict[str, tuple[int, float]] = {
    "fetch_thread": (30, 60.0),
    "fetch_user": (20, 60.0),
    "fetch_rules": (60, 60.0),
    "fetch_url": (30, 60.0),
    "health_status": (120, 60.0),
}
_TOOL_LIMITERS = {
    name: SlidingWindowRateLimiter(limit, window)
    for name, (limit, window) in TOOL_RATE_LIMITS.items()
}


def reset_rate_limits() -> None:
    for limiter in _TOOL_LIMITERS.values():
        limiter.reset()


def _check_tool_rate_limit(name: str) -> None:
    limiter = _TOOL_LIMITERS.get(name)
    if limiter is not None:
        try:
            limiter.check()
        except VedaError as exc:
            raise ToolError(str(exc), code=exc.code) from exc


def _route_for_result(result: Any) -> str:
    if isinstance(result, dict):
        meta = result.get("meta")
        if isinstance(meta, dict) and meta.get("route"):
            return str(meta["route"])
        if result.get("route"):
            return str(result["route"])
    return "core"


async def call_tool(name: str, arguments: dict[str, Any] | None = None) -> Any:
    if name not in TOOL_HANDLERS:
        raise ToolError(f"Unknown tool: {name}", code="unknown_tool")
    started = time.monotonic()
    try:
        _check_tool_rate_limit(name)
        result = await asyncio.to_thread(TOOL_HANDLERS[name], arguments or {})
    except ToolError as exc:
        health.record(
            name,
            route="security",
            outcome="error",
            latency_ms=(time.monotonic() - started) * 1000,
            error_code=exc.code,
        )
        raise
    except VedaError as exc:
        health.record(
            name,
            route="error",
            outcome="error",
            latency_ms=(time.monotonic() - started) * 1000,
            error_code=exc.code,
        )
        raise ToolError(str(exc), code=exc.code) from exc
    except Exception:
        health.record(
            name,
            route="error",
            outcome="error",
            latency_ms=(time.monotonic() - started) * 1000,
            error_code="exception",
        )
        raise
    health.record(
        name,
        route=_route_for_result(result),
        outcome="success",
        latency_ms=(time.monotonic() - started) * 1000,
    )
    return result
