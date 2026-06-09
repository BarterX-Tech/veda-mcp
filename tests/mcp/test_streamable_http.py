from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import anyio
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def test_streamable_http_server_lists_and_calls_status_tool() -> None:
    port = _free_port()
    root = Path(__file__).resolve().parents[2]
    env = {
        **os.environ,
        "VEDA_HOST": "127.0.0.1",
        "VEDA_PORT": str(port),
        "VEDA_TOKEN_FILE": os.fspath(root / "run" / "test-no-token"),
    }
    process = subprocess.Popen(
        [sys.executable, "-m", "veda.mcp.server"],
        cwd=os.fspath(root),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    try:
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            try:
                with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                    break
            except OSError as exc:
                if process.poll() is not None:
                    output = process.stdout.read() if process.stdout else ""
                    raise AssertionError(f"server exited early:\n{output}") from exc
                time.sleep(0.1)
        else:
            raise AssertionError("server did not start")

        async def exercise() -> None:
            async with streamable_http_client(f"http://127.0.0.1:{port}/mcp") as (
                read,
                write,
                _,
            ):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    listed = await session.list_tools()
                    assert {tool.name for tool in listed.tools} == {
                        "fetch_thread",
                        "fetch_user",
                        "fetch_profile",
                        "fetch_rules",
                        "fetch_url",
                        "health_status",
                    }
                    status = await session.call_tool("health_status", {})
                    assert status.content

        anyio.run(exercise)
    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)
