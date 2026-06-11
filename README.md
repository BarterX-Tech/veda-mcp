# veda

Standalone MCP server for public Reddit and web reads. veda knows nothing about callers:
inputs are URLs/usernames/subreddits, outputs are JSON-serializable data.

## Setup

```bash
cd /Users/nitinkhanna/Documents/Services/Veda
uv venv --python /Users/nitinkhanna/.local/bin/python3.11
uv pip install -e ".[dev]"
```

Dependencies include `scrapling[fetchers]` (stealth + dynamic browser tiers) and
`trafilatura` (readable-text extraction). On a fresh machine, fetch the browser
binaries once:

```bash
.venv/bin/scrapling install
```

`health_status()` reports `tiers_available`; the server also logs a warning at
startup when a fetch tier is unavailable, so a broken browser dependency is loud
instead of silently degrading every external fetch.

## Run

```bash
scripts/veda-server start
scripts/veda-server status
scripts/veda-server restart
scripts/veda-server stop
```

Defaults:

- `VEDA_HOST=127.0.0.1`
- `VEDA_PORT=8765`
- `VEDA_REDDIT_JSON_ENABLED=0`
- `VEDA_REDDIT_HTML_ENABLED=1`
- `VEDA_EXTERNAL_GITHUB_RAW_ENABLED=1`
- `VEDA_EXTERNAL_TIER1_ENABLED=1`
- `VEDA_EXTERNAL_TIER2_ENABLED=1`
- `VEDA_EXTERNAL_TIER3_ENABLED=1`
- Streamable HTTP endpoint: `http://127.0.0.1:8765/mcp`
- Local bearer token file: `run/veda-token`

Launchd plist: `scripts/tech.barterx.veda.plist`.

`scripts/veda-server start` generates a local token if `VEDA_AUTH_TOKEN` is not
already set. The token is ignored by git and used by `scripts/veda-server status`
automatically. MCP clients should send:

```text
Authorization: Bearer <contents of run/veda-token>
```

## MCP Tools

- `fetch_thread(url, comment_limit=500, comment_sort="top")`
- `fetch_user(username, kinds=("submitted","comments"), pages=2)`
- `fetch_rules(subreddit)`
- `fetch_url(url, max_chars=20000)`
- `health_status()`

Scraping paths are controlled centrally by environment flags. Reddit `.json`
routes are disabled by default because live probes currently return blocked HTML
instead of JSON; Reddit reads go directly to old.reddit HTML unless
`VEDA_REDDIT_JSON_ENABLED=1` is set. Mobile `/s/` share links resolve through
the stealth fetch path before normalization. Shared transport owns the request
fingerprint, rate limiter, and bounded in-memory cache.

`fetch_user` falls back per requested listing kind, so a working submitted JSON
listing can be combined with an HTML comments fallback. Its result also carries
the profile sidebar — bio text, deduped non-Reddit external URLs, post/comment
karma, and the account-created timestamp — extracted from the listing pages at
no extra request cost (one extra profile-page read only on the JSON route).
New-style bios/social links that old.reddit never renders are filled by one
stealth fetch of the new-reddit profile page when the sidebar is empty.

`fetch_url` honors robots.txt (fetched with a cheap plain request, never the
browser ladder), blocks localhost/private-network targets, and fetches GitHub
repository READMEs through the raw markdown path (`HEAD` ref, repo-root URLs
only, status-checked). Every host tries the cheap tier1 request first, then
escalates through stealth (tier2) and dynamic-browser (tier3) HTML tiers when
extracted text is thin. Text extraction uses trafilatura with markdown-style
block separation, falling back to an xpath chain; results include `title` and a
`truncated` flag, and text is capped to `max_chars`.

The MCP dispatcher applies conservative per-tool rate limits before calling the
core. The shared transport still owns platform-facing pacing and the bounded
in-memory cache.

Health monitoring records per-tool calls, successes, errors, route counts,
`.json` vs HTML ratio, error codes, average latency, the active scraping
config, and `tiers_available` (which fetch tiers can run in this environment).
Use the `health_status()` MCP tool or `scripts/veda-server status` against a
running server.

`scripts/veda-canary` runs live probes (tier availability, two external URLs,
subreddit rules, one archived Reddit thread) and exits non-zero when any probe fails or returns
field-incomplete data. Run it manually or on a schedule to catch silent
degradation — broken fetch dependencies, Reddit markup drift, extraction
regressions.

## MCP Client

Point an MCP Streamable HTTP client at:

```text
http://127.0.0.1:8765/mcp
```

If `run/veda-token` exists, configure the client with an `Authorization: Bearer`
header using that token.

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

## Docs

- [Product PRD](docs/PRD.md)
- [Technical PRD](docs/TECHNICAL_PRD.md)
- [Integration PRD](docs/INTEGRATION_PRD.md)
