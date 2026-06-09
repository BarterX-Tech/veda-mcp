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
- `health_status()`

The Reddit thread ladder is JSON-first, then HTML fallback. M0 preserves the
ported fetch ladder while M1+ make the HTML branch field-complete. Subreddit
rules also fall back to old.reddit HTML when JSON is blocked or empty, and
mobile `/s/` share links resolve through the stealth fetch path before
normalization.

`fetch_user` falls back per requested listing kind, so a working submitted JSON
listing can be combined with an HTML comments fallback. `fetch_profile` returns
the old.reddit bio text plus deduped non-Reddit external URLs.

`fetch_url` honors robots.txt, chooses a static-first route for known lightweight
hosts, escalates through stealth/dynamic HTML tiers when extracted text is thin,
and caps returned text to `max_chars`.

Health monitoring records per-tool calls, successes, errors, route counts,
error codes, and average latency. Use the `health_status()` MCP tool or
`scripts/veda-server status` against a running server.

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
