<p align="center">
  <img src="assets/logo.png" alt="veda-mcp logo" width="160">
</p>

# veda-mcp

**A standalone MCP server for public Reddit and web reads.** Give it a URL, a
username, or a subreddit; it returns clean, structured, JSON-serializable
data. veda is strictly caller-agnostic — it knows nothing about who calls it
or what the data is used for.

- **Transport:** MCP over Streamable HTTP (`/mcp`), bearer-token gated
- **Reddit reads:** thread + comment tree, user activity + profile, subreddit
  rules — field-complete (ids, scores, timestamps, OP flags)
- **Web reads:** readable markdown text from any public URL, with a tiered
  fetch ladder (plain request → stealth browser → dynamic browser) for
  JS-rendered sites
- **No credentials required:** public reads only — no Reddit API keys, no
  OAuth, no accounts

## Setup

```bash
git clone https://github.com/BarterX-Tech/veda-mcp.git
cd veda-mcp
uv venv --python 3.11
uv pip install -e ".[dev]"
.venv/bin/scrapling install   # one-time browser binaries for stealth tiers
```

## Run

```bash
scripts/veda-server start
scripts/veda-server status
scripts/veda-server restart
scripts/veda-server stop
```

On macOS this manages a launchd service (rendered from
`scripts/launchd.plist.template`); elsewhere it runs the server directly.

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

`scripts/veda-server start` generates a local token if `VEDA_AUTH_TOKEN` is
not already set. The token is ignored by git. MCP clients should send:

```text
Authorization: Bearer <contents of run/veda-token>
```

**Security:** the server refuses to start on a non-loopback address without a
token, so it cannot accidentally become an open proxy. See
[SECURITY.md](SECURITY.md) for the threat model.

## MCP Tools

- `fetch_thread(url, comment_limit=500, comment_sort="top")`
- `fetch_user(username, kinds=("submitted","comments"), pages=2)`
- `fetch_rules(subreddit)`
- `fetch_url(url, max_chars=20000)`
- `health_status()`

Scraping paths are controlled centrally by environment flags. Reddit `.json`
routes are disabled by default because live probes currently return blocked
HTML instead of JSON; Reddit reads go directly to old.reddit HTML unless
`VEDA_REDDIT_JSON_ENABLED=1` is set. Mobile `/s/` share links resolve through
the stealth fetch path before normalization. Shared transport owns the request
fingerprint, rate limiter, and bounded in-memory cache.

`fetch_user` falls back per requested listing kind, so a working submitted
JSON listing can be combined with an HTML comments fallback. Its result also
carries the profile sidebar — bio text, deduped non-Reddit external URLs,
post/comment karma, and the account-created timestamp — extracted from the
listing pages at no extra request cost. New-style bios/social links that
old.reddit never renders are filled by one stealth fetch of the new-reddit
profile page when the sidebar is empty.

`fetch_url` honors robots.txt (fetched with a cheap plain request, never the
browser ladder), blocks localhost/private-network targets, re-validates every
redirect hop on the plain-request route, and fetches GitHub repository
READMEs through the raw markdown path (`HEAD` ref, repo-root URLs only,
status-checked). Every host tries the cheap tier1 request first, then
escalates through stealth (tier2) and dynamic-browser (tier3) HTML tiers when
extracted text is thin. Text extraction uses trafilatura with markdown-style
block separation, falling back to an xpath chain; results include `title` and
a `truncated` flag, and text is capped to `max_chars`.

The MCP dispatcher applies conservative per-tool rate limits before calling
the core. The shared transport still owns platform-facing pacing and the
bounded in-memory cache.

Health monitoring records per-tool calls, successes, errors, route counts,
`.json` vs HTML ratio, error codes, average latency, the active scraping
config, and `tiers_available` (which fetch tiers can run in this
environment). Use the `health_status()` MCP tool or
`scripts/veda-server status` against a running server.

`scripts/veda-canary` runs live probes (tier availability, two external URLs,
subreddit rules, one archived Reddit thread) and exits non-zero when any
probe fails or returns field-incomplete data. Run it manually or on a
schedule to catch silent degradation — broken fetch dependencies, Reddit
markup drift, extraction regressions.

## MCP Client

Point an MCP Streamable HTTP client at:

```text
http://127.0.0.1:8765/mcp
```

If `run/veda-token` exists, configure the client with an
`Authorization: Bearer` header using that token.

## Development

```bash
pytest
ruff check .
```

The boundary test AST-scans `veda/**/*.py` and fails on imports outside the
allowed dependency set. Read paths return data only; they do not save files.
See [CONTRIBUTING.md](CONTRIBUTING.md).

## Responsible Use

veda reads **publicly available** pages only — it uses no credentials,
performs no authenticated requests, and applies conservative rate limiting by
default. You are responsible for how you use it:

- Comply with the terms of service and robots.txt of the sites you read, and
  with the laws of your jurisdiction.
- Do not use veda to collect personal data in ways that violate privacy laws
  (GDPR, CCPA, or equivalents).
- Keep request volumes reasonable; the built-in rate limits are defaults, not
  permission to circumvent platform protections at scale.

This project is **not affiliated with, endorsed by, or sponsored by Reddit,
Inc.** or any other platform it can read. "Reddit" is a trademark of Reddit,
Inc., used here only to describe interoperability.

The software is provided "as is", without warranty of any kind — see
[LICENSE](LICENSE).

## License

[Apache License 2.0](LICENSE) · Copyright 2026 BarterX Tech

## Docs

- [Product PRD](docs/PRD.md)
- [Technical PRD](docs/TECHNICAL_PRD.md)
- [Integration PRD](docs/INTEGRATION_PRD.md)
- [Security policy](SECURITY.md)
