from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import anyio
from mcp import ClientSession

try:
    from mcp.client.streamable_http import streamablehttp_client as _streamablehttp_client
except ImportError:  # pragma: no cover - compatibility with newer-only mcp releases
    _streamablehttp_client = None

try:
    from mcp.client.streamable_http import create_mcp_http_client, streamable_http_client
except ImportError:  # pragma: no cover - compatibility with early mcp 1.x releases
    create_mcp_http_client = None
    streamable_http_client = None

DEFAULT_MCP_URL = "http://127.0.0.1:8765/mcp"
DEFAULT_TOKEN_FILE = "run/veda-token"


class VedaClientError(Exception):
    code = "veda_error"

    def __init__(self, message: str, *, code: str | None = None) -> None:
        super().__init__(message)
        if code is not None:
            self.code = code


class VedaBlocked(VedaClientError):
    code = "blocked"


class VedaNotFound(VedaClientError):
    code = "not_found"


class VedaParseError(VedaClientError):
    code = "parse_error"


class VedaUnreachable(VedaClientError):
    code = "unreachable"


_ERROR_CLASSES: dict[str, type[VedaClientError]] = {
    "blocked": VedaBlocked,
    "not_found": VedaNotFound,
    "parse_error": VedaParseError,
    "veda_error": VedaClientError,
}


def fetch_thread(
    url: str,
    *,
    comment_limit: int = 500,
    comment_sort: str = "top",
) -> Any:
    return _call_sync(
        "fetch_thread",
        _logged_url(url),
        {
            "url": url,
            "comment_limit": comment_limit,
            "comment_sort": comment_sort,
        },
    )


def fetch_user(
    username: str,
    *,
    kinds: tuple[str, ...] = ("submitted", "comments"),
    pages: int = 2,
) -> Any:
    return _call_sync(
        "fetch_user",
        username,
        {"username": username, "kinds": kinds, "pages": pages},
    )


def fetch_rules(subreddit: str) -> Any:
    return _call_sync("fetch_rules", subreddit, {"subreddit": subreddit})


def fetch_url(url: str, *, max_chars: int = 20000) -> Any:
    return _call_sync("fetch_url", _logged_url(url), {"url": url, "max_chars": max_chars})


def health_status() -> Any:
    return _call_sync("health_status", "-", {})


def _resolve_endpoint(environ: dict[str, str] | None = None) -> str:
    environ = os.environ if environ is None else environ
    return environ.get("VEDA_MCP_URL") or DEFAULT_MCP_URL


def _resolve_token(environ: dict[str, str] | None = None) -> str:
    environ = os.environ if environ is None else environ
    if "VEDA_AUTH_TOKEN" in environ:
        token = environ["VEDA_AUTH_TOKEN"].strip()
        if not token:
            raise VedaUnreachable("VEDA_AUTH_TOKEN is empty")
        return token

    token_file = Path(environ.get("VEDA_TOKEN_FILE", DEFAULT_TOKEN_FILE)).expanduser()
    try:
        token = token_file.read_text().strip()
    except OSError as exc:
        raise VedaUnreachable(f"VEDA token file not found: {token_file}") from exc
    if not token:
        raise VedaUnreachable(f"VEDA token file is empty: {token_file}")
    return token


async def _call_tool(name: str, arguments: dict[str, Any]) -> Any:
    headers = {"Authorization": f"Bearer {_resolve_token()}"}
    endpoint = _resolve_endpoint()
    if _streamablehttp_client is not None:
        async with _streamablehttp_client(endpoint, headers=headers) as (read, write, _):
            return await _initialized_call(name, arguments, read, write)

    if create_mcp_http_client is None or streamable_http_client is None:
        raise VedaUnreachable("MCP Streamable HTTP client is unavailable")

    async with create_mcp_http_client(headers=headers) as http_client:
        async with streamable_http_client(endpoint, http_client=http_client) as (read, write, _):
            return await _initialized_call(name, arguments, read, write)


async def _initialized_call(name: str, arguments: dict[str, Any], read: Any, write: Any) -> Any:
    async with ClientSession(read, write) as session:
        await session.initialize()
        return await session.call_tool(name, arguments)


def _call_sync(name: str, resource: str, arguments: dict[str, Any]) -> Any:
    try:
        result = anyio.run(_call_tool, name, arguments)
        payload = _unwrap(result)
    except VedaClientError as exc:
        _log_error(name, resource, exc.code)
        raise
    except Exception as exc:
        error = VedaUnreachable(f"Veda MCP unreachable: {exc}")
        _log_error(name, resource, error.code)
        raise error from exc

    _log_ok(name, resource, _route(payload))
    return payload


def _unwrap(result: Any) -> Any:
    if bool(getattr(result, "isError", False) or getattr(result, "is_error", False)):
        message = _result_text(result) or "Veda MCP tool failed"
        code, clean_message = _parse_error(message)
        raise _error_for_code(code, clean_message)

    structured = getattr(result, "structuredContent", None)
    if structured is None:
        structured = getattr(result, "structured_content", None)
    if structured is not None:
        return structured

    content = getattr(result, "content", None)
    if not content:
        return result

    first = content[0]
    text = getattr(first, "text", None)
    if isinstance(text, str):
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return text
    return first


def _result_text(result: Any) -> str:
    content = getattr(result, "content", None)
    if not content:
        return str(result)
    parts = [getattr(item, "text", None) for item in content]
    return "\n".join(part for part in parts if isinstance(part, str))


def _parse_error(message: str) -> tuple[str, str]:
    match = re.match(r"^\[([a-z0-9_]+)]\s*(.*)$", message.strip(), flags=re.I | re.S)
    if not match:
        return "veda_error", message
    code = match.group(1)
    clean_message = match.group(2) or message
    return code, clean_message


def _error_for_code(code: str, message: str) -> VedaClientError:
    error_class = _ERROR_CLASSES.get(code)
    if error_class is None:
        return VedaClientError(message, code=code)
    return error_class(message)


def _route(payload: Any) -> str:
    if isinstance(payload, dict):
        meta = payload.get("meta")
        if isinstance(meta, dict) and meta.get("route"):
            return str(meta["route"])
        if payload.get("route"):
            return str(payload["route"])
    return "core"


def _logged_url(url: str) -> str:
    parsed = urlsplit(url)
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, "", ""))


def _log_ok(name: str, resource: str, route: str) -> None:
    print(f"[veda] {name} {resource} -> ok route={route}")


def _log_error(name: str, resource: str, code: str) -> None:
    print(f"[veda] {name} {resource} -> error {code}")


__all__ = [
    "VedaBlocked",
    "VedaClientError",
    "VedaNotFound",
    "VedaParseError",
    "VedaUnreachable",
    "fetch_rules",
    "fetch_thread",
    "fetch_url",
    "fetch_user",
    "health_status",
]
