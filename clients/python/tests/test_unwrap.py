from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest

from veda_client import (
    VedaBlocked,
    VedaClientError,
    VedaNotFound,
    VedaParseError,
    _logged_url,
    _route,
    _unwrap,
)


@dataclass
class Text:
    text: str


@dataclass
class Result:
    content: list[Any] | None = None
    isError: bool = False
    structuredContent: Any = None


def test_unwrap_json_text_content() -> None:
    result = Result(content=[Text('{"meta":{"route":"html"},"post":{"title":"T"}}')])

    assert _unwrap(result) == {"meta": {"route": "html"}, "post": {"title": "T"}}


def test_unwrap_structured_content() -> None:
    result = Result(content=[Text("{}")], structuredContent={"ok": True})

    assert _unwrap(result) == {"ok": True}


def test_unwrap_plain_text_content() -> None:
    result = Result(content=[Text("plain text")])

    assert _unwrap(result) == "plain text"


@pytest.mark.parametrize(
    ("message", "error_class", "code", "clean_message"),
    [
        ("[blocked] no route worked", VedaBlocked, "blocked", "no route worked"),
        ("[not_found] gone", VedaNotFound, "not_found", "gone"),
        ("[parse_error] bad html", VedaParseError, "parse_error", "bad html"),
        ("boom", VedaClientError, "veda_error", "boom"),
    ],
)
def test_unwrap_maps_error_codes(message, error_class, code, clean_message) -> None:
    with pytest.raises(error_class) as exc:
        _unwrap(Result(content=[Text(message)], isError=True))

    assert exc.value.code == code
    assert str(exc.value) == clean_message


def test_unwrap_preserves_unknown_error_code() -> None:
    with pytest.raises(VedaClientError) as exc:
        _unwrap(Result(content=[Text("[rate_limited] slow down")], isError=True))

    assert type(exc.value) is VedaClientError
    assert exc.value.code == "rate_limited"
    assert str(exc.value) == "slow down"


def test_route_prefers_meta_route_then_top_level_route() -> None:
    assert _route({"meta": {"route": "html"}, "route": "tier1"}) == "html"
    assert _route({"route": "tier1"}) == "tier1"
    assert _route({"ok": True}) == "core"


def test_logged_url_strips_query_and_fragment() -> None:
    assert _logged_url("https://example.com/path?a=signed#fragment") == "https://example.com/path"
