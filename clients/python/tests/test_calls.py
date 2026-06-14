from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest

import veda_client
from veda_client import VedaBlocked


@dataclass
class Text:
    text: str


@dataclass
class Result:
    content: list[Any]
    isError: bool = False


def test_public_call_logs_success_with_redacted_url(monkeypatch, capsys) -> None:
    async def fake_call_tool(name: str, arguments: dict[str, Any]) -> Result:
        assert name == "fetch_url"
        assert arguments["url"] == "https://example.com/path?sig=placeholder#frag"
        return Result([Text('{"route":"tier1","text":"ok"}')])

    monkeypatch.setattr(veda_client, "_call_tool", fake_call_tool)

    assert veda_client.fetch_url("https://example.com/path?sig=placeholder#frag")["text"] == "ok"

    assert capsys.readouterr().out == (
        "[veda] fetch_url https://example.com/path -> ok route=tier1\n"
    )


def test_public_call_logs_typed_error_with_redacted_url(monkeypatch, capsys) -> None:
    async def fake_call_tool(name: str, arguments: dict[str, Any]) -> Result:
        assert name == "fetch_thread"
        assert arguments["url"] == "https://reddit.com/r/x/comments/abc/t/?token=placeholder"
        return Result([Text("[blocked] no route worked")], isError=True)

    monkeypatch.setattr(veda_client, "_call_tool", fake_call_tool)

    with pytest.raises(VedaBlocked):
        veda_client.fetch_thread("https://reddit.com/r/x/comments/abc/t/?token=placeholder")

    assert capsys.readouterr().out == (
        "[veda] fetch_thread https://reddit.com/r/x/comments/abc/t/ -> error blocked\n"
    )
