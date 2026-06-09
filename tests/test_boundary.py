from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ALLOWED_ROOTS = {
    "__future__",
    "collections",
    "contextlib",
    "dataclasses",
    "datetime",
    "enum",
    "functools",
    "importlib",
    "json",
    "logging",
    "os",
    "pathlib",
    "re",
    "signal",
    "sys",
    "threading",
    "time",
    "typing",
    "urllib",
    "webbrowser",
    "lxml",
    "mcp",
    "requests",
    "scrapling",
    "veda",
}
FORBIDDEN_TEXT = ("reddit_operator",)


def _root(name: str) -> str:
    return name.split(".", 1)[0]


def test_veda_import_boundary() -> None:
    problems: list[str] = []
    for path in sorted((ROOT / "veda").rglob("*.py")):
        text = path.read_text()
        for forbidden in FORBIDDEN_TEXT:
            if forbidden in text:
                problems.append(f"{path.relative_to(ROOT)} references {forbidden}")

        tree = ast.parse(text, filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    root = _root(alias.name)
                    if root not in ALLOWED_ROOTS:
                        problems.append(f"{path.relative_to(ROOT)} imports {alias.name}")
            elif isinstance(node, ast.ImportFrom):
                if node.level:
                    continue
                if node.module is None:
                    continue
                root = _root(node.module)
                if root not in ALLOWED_ROOTS:
                    problems.append(f"{path.relative_to(ROOT)} imports {node.module}")

    assert not problems, "\n".join(problems)


def test_veda_read_paths_do_not_write_files() -> None:
    problems: list[str] = []
    write_methods = {"write_text", "write_bytes", "mkdir", "unlink"}
    write_modes = {"w", "a", "x", "w+", "a+", "x+"}

    for path in sorted((ROOT / "veda").rglob("*.py")):
        tree = ast.parse(path.read_text(), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Attribute) and node.func.attr in write_methods:
                    problems.append(f"{path.relative_to(ROOT)} calls {node.func.attr}()")
                if isinstance(node.func, ast.Name) and node.func.id == "open":
                    mode = node.args[1] if len(node.args) > 1 else None
                    if isinstance(mode, ast.Constant) and str(mode.value) in write_modes:
                        problems.append(f"{path.relative_to(ROOT)} opens a file in {mode.value!r}")

    assert not problems, "\n".join(problems)
