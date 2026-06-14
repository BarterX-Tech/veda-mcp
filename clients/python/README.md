# veda-client

Small synchronous Python client for the
[veda MCP server](https://github.com/BarterX-Tech/veda-mcp). It is only the
client half of the protocol: it talks to an existing veda server over MCP
Streamable HTTP and does not include the server's scraping stack.

## Install

```bash
pip install veda-client
```

Install directly from this repository:

```bash
pip install "veda-client @ git+https://github.com/BarterX-Tech/veda-mcp.git#subdirectory=clients/python"
```

The package depends only on `mcp>=1.0` and `anyio`.

## Configuration

- `VEDA_MCP_URL`: MCP endpoint. Defaults to `http://127.0.0.1:8765/mcp`.
- `VEDA_AUTH_TOKEN`: bearer token. Overrides any token file.
- `VEDA_TOKEN_FILE`: bearer token file. Defaults to `run/veda-token`.

## Usage

```python
from veda_client import VedaBlocked, fetch_thread

try:
    thread = fetch_thread("https://old.reddit.com/r/Python/comments/abc123/title/")
except VedaBlocked:
    thread = None
```

The client emits one stdout line per call, for example:

```text
[veda] fetch_thread https://old.reddit.com/r/Python/comments/abc123/title/ -> ok route=html
```

URL query strings and fragments are stripped from logged resources so signed
URLs and tracking tokens are not printed.

## Protocol Versioning

`veda-client` starts at `0.1.0`. Its `MAJOR.MINOR` version is intended to track
the veda server protocol it speaks, so client and server contract changes can
move together in this repository.
