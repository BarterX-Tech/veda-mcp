from __future__ import annotations

from pathlib import Path

import pytest

from veda_client import VedaUnreachable, _resolve_endpoint, _resolve_token


def test_endpoint_defaults_to_local_mcp_url() -> None:
    assert _resolve_endpoint({}) == "http://127.0.0.1:8765/mcp"


def test_endpoint_uses_env_override() -> None:
    assert _resolve_endpoint({"VEDA_MCP_URL": "https://veda.example/mcp"}) == (
        "https://veda.example/mcp"
    )


def test_token_env_overrides_file(tmp_path: Path) -> None:
    token_file = tmp_path / "token"
    token_file.write_text("file-token\n")

    assert (
        _resolve_token({"VEDA_AUTH_TOKEN": " env-token ", "VEDA_TOKEN_FILE": str(token_file)})
        == "env-token"
    )


def test_empty_token_env_errors() -> None:
    with pytest.raises(VedaUnreachable) as exc:
        _resolve_token({"VEDA_AUTH_TOKEN": "   "})

    assert exc.value.code == "unreachable"
    assert "VEDA_AUTH_TOKEN is empty" in str(exc.value)


def test_missing_token_file_errors(tmp_path: Path) -> None:
    missing = tmp_path / "missing-token"

    with pytest.raises(VedaUnreachable) as exc:
        _resolve_token({"VEDA_TOKEN_FILE": str(missing)})

    assert exc.value.code == "unreachable"
    assert str(missing) in str(exc.value)


def test_empty_token_file_errors(tmp_path: Path) -> None:
    token_file = tmp_path / "token"
    token_file.write_text("\n")

    with pytest.raises(VedaUnreachable) as exc:
        _resolve_token({"VEDA_TOKEN_FILE": str(token_file)})

    assert exc.value.code == "unreachable"
    assert "empty" in str(exc.value)
