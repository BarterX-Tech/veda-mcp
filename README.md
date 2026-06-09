# veda

Standalone MCP server for public Reddit and web reads. veda knows nothing about callers:
inputs are URLs/usernames/subreddits, outputs are JSON-serializable data.

## Setup

```bash
cd /Users/nitinkhanna/Documents/Services/Veda
uv venv --python /Users/nitinkhanna/.local/bin/python3.11
uv pip install -e ".[dev]"
```

## Run

```bash
scripts/veda-server start
scripts/veda-server status
scripts/veda-server stop
```

Defaults:

- `VEDA_HOST=127.0.0.1`
- `VEDA_PORT=8765`
- Streamable HTTP endpoint: `http://127.0.0.1:8765/mcp`

Launchd plist: `scripts/com.barterx.veda.plist`.

## MCP Tools

- `fetch_thread(url, comment_limit=500, comment_sort="top")`
- `fetch_user(username, kinds=("submitted","comments"), pages=2)`
- `fetch_profile(username)`
- `fetch_rules(subreddit)`
- `fetch_url(url, max_chars=20000)`

The Reddit thread ladder is JSON-first, then HTML fallback. M0 preserves the
ported HTML thread parser behavior; the parity harness is marked `xfail` until
M1 makes the HTML branch field-complete.

## MCP Client

Point an MCP Streamable HTTP client at:

```text
http://127.0.0.1:8765/mcp
```

For Claude slash-command setups, use `scripts/veda-server.md` as the thin
`/veda-server` wrapper.

## Development

```bash
pytest
ruff check .
```

The boundary test AST-scans `veda/**/*.py` and fails on imports outside the
allowed dependency set or any `reddit_operator` reference. Read paths return data
only; they do not save files.
