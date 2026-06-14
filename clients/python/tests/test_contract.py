from __future__ import annotations

import ast
from pathlib import Path

from veda.errors import VedaError

import veda_client


def _server_error_codes() -> set[str]:
    return {
        value.code
        for value in VedaError.__subclasses__() + [VedaError]
        if isinstance(getattr(value, "code", None), str)
    }


def _server_tool_names() -> set[str]:
    root = Path(__file__).resolve().parents[3]
    tree = ast.parse((root / "veda" / "mcp" / "tools.py").read_text())
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "TOOL_HANDLERS":
                    return _dict_keys(node.value)
        if (
            isinstance(node, ast.AnnAssign)
            and isinstance(node.target, ast.Name)
            and node.target.id == "TOOL_HANDLERS"
        ):
            return _dict_keys(node.value)
    raise AssertionError("TOOL_HANDLERS not found")


def _dict_keys(node: ast.expr | None) -> set[str]:
    assert isinstance(node, ast.Dict)
    return {
        key.value
        for key in node.keys
        if isinstance(key, ast.Constant) and isinstance(key.value, str)
    }


def test_client_error_classes_cover_server_error_codes() -> None:
    expected = {
        "blocked": veda_client.VedaBlocked,
        "not_found": veda_client.VedaNotFound,
        "parse_error": veda_client.VedaParseError,
        "veda_error": veda_client.VedaClientError,
    }

    server_codes = _server_error_codes()

    assert set(expected) == server_codes
    for code, error_class in expected.items():
        assert error_class.code == code


def test_client_functions_cover_server_read_tools() -> None:
    for tool_name in _server_tool_names():
        assert callable(getattr(veda_client, tool_name, None)), tool_name
