# veda — Technical PRD

**Status:** DRAFT · **Date:** 2026-06-10 · **Owner:** Nitin
**Companion:** [`PRD.md`](./PRD.md). This is the deep spec — repo layout, tool contract, parser specs, tests, tasks.

> **Scope discipline:** this document describes **veda only**. veda is caller-agnostic — it never references a consumer, what the data is used for, or any other project. Its contract is *requested resource → clean data*.

---

## 1. Architecture

### 1.0 Repository, runtime, integration
- **Repo:** `git@github.com:BarterX-Tech/veda.reddit-operator.git` · **Path:** `~/Documents/Services/Veda`
- **veda is an MCP server.** It exposes its reads as **MCP tools over HTTP/SSE** (Streamable HTTP) and runs as **one long-lived server** (locally via `launchd`; a real host later — same shape).
- **One server ⇒ one rate-limiter + one browser pool + one cache** against the platform. Any MCP client connects to the same server.
- **Internal shape:** veda = **scraping core** (transport, parsers, the read functions) + a **thin MCP shell** that registers the tools. The core is MCP-agnostic and unit-testable on its own.
- **Dependencies:** stdlib + scrapling (with its `[fetchers]` extra — stealth/dynamic browser tiers are hard requirements, not optional) + trafilatura + lxml + requests + an MCP server lib. **Nothing else.** veda imports nothing from any caller and has no knowledge one exists.

### 1.1 Sub-scrapers (one per source)
- `veda.reddit` — Reddit reads (this PRD's focus).
- `veda.external` — generic non-Reddit web pages (robots-aware).
- *(future)* `veda.x`, etc.

Each uses centrally configured scrape routes and returns a **canonical shape**. Reddit `.json`
routes are disabled by default for now; HTML is the active Reddit route.

### 1.2 The contract — core functions ↔ MCP tools
The **core** is four functions; the **MCP shell** exposes each as a tool of the same name (plus the operational `health_status` tool). Tool args = function kwargs; tool result = the JSON shape (§3). Errors are typed and carry a `.code`.

```python
# CORE (the scraping library the tools wrap)
def fetch_thread(url: str, *, comment_limit: int = 500,
                 comment_sort: str = "top") -> ThreadResult: ...   # post + comment tree
def fetch_user(username: str, *, kinds=("submitted", "comments"),
               pages: int = 2) -> UserResult: ...   # profile sidebar + post/comment history
def fetch_rules(subreddit: str) -> list[Rule]: ...                 # subreddit rules
def fetch_url(url: str, *, max_chars: int = 20000) -> ExternalDoc: ...  # robots-aware readable text

class VedaError(Exception): ...   # base (carries .code)
class Blocked(VedaError): ...     # platform gated / unreachable
class NotFound(VedaError): ...    # 404
class ParseError(VedaError): ...  # markup unparseable
```

**MCP tools (HTTP/SSE):** `fetch_thread`, `fetch_user`, `fetch_rules`, `fetch_url` — names/args/results 1:1 with the core. `VedaError` → MCP tool error carrying `.code`. Inputs are `str`/`int`/tuples; outputs are plain JSON-serializable dicts/lists; **no side effects** (veda returns data, persists nothing).

### 1.3 Repo layout (`~/Documents/Services/Veda`)
```text
Veda/
  pyproject.toml          # package `veda`; deps: scrapling[fetchers], trafilatura, lxml, requests, mcp
  README.md               # ALWAYS-UPDATED: run/config, tool reference, health/metrics (synced each milestone)
  .github/workflows/      # CI: tests + boundary + contract on every push
  scripts/
    veda-server           # start/stop/restart/status entrypoint (backs /veda-server + launchd)
    tech.barterx.veda.plist# launchd unit for the local always-on server
  veda/
    __init__.py
    config.py             # central scrape-route flags (Reddit JSON/HTML, external tiers)
    _transport.py         # fingerprint/headers, StealthyFetcher wrappers, rate-limiter, .json/HTML tier ladder
    errors.py             # VedaError hierarchy
    reddit/
      __init__.py         # core reads: fetch_thread, fetch_user, fetch_rules
      types.py            # ThreadResult, UserResult, Rule (TypedDict) + shapers
      _html_thread.py     # HTML thread parser — field-complete (#1)
      _html_user.py       # HTML user parser
      _html_profile.py    # HTML about/bio parser
      thread.py / user.py / rules.py
    external/
      __init__.py         # core read: fetch_url
      fetch.py            # robots check, host routing, extraction, escalation
    mcp/
      server.py           # MCP server (HTTP/SSE): registers the MCP tools
      tools.py            # tool schemas (args↔kwargs, result↔§3) + error mapping
    health.py             # per-tool/route metrics (M5)
  tests/                  # unit + parity + boundary + contract + MCP-tool tests
```
Underscore-prefixed modules are internal; only sub-package `__init__` names are public.

### 1.4 Isolation enforcement
- **Hard boundary:** veda is a separate repo + process. It cannot import any caller; it has no caller-specific code.
- **Boundary test** (veda's own suite): AST-scan `veda/**/*.py`; fail on any import outside veda's allowed dependency set (no project-specific imports).
- **No inbound knowledge:** tool inputs are plain values; veda never receives or stores caller context.

### 1.5 Local always-on security posture
Local veda is intended to run 24/7 for local agents, but only as a loopback service.

- **Bind address:** default `VEDA_HOST=127.0.0.1`. Local launchd/service mode must not bind to `0.0.0.0`.
- **Bearer auth:** if `VEDA_AUTH_TOKEN` is present, every MCP request must include `Authorization: Bearer <token>`. Browser-style `GET /mcp` remains a public local status page; actual MCP traffic is token-gated.
- **Token storage:** `scripts/veda-server` generates a token in `run/veda-token` (`0600`, ignored by git) when no `VEDA_AUTH_TOKEN` is provided. The launchd unit receives `VEDA_TOKEN_FILE` and the Python server reads that token at startup.
- **Token validity:** local tokens are long-lived and do not expire automatically. A token remains valid until `run/veda-token` is deleted/replaced or `VEDA_AUTH_TOKEN` changes and the server is restarted.
- **Token rotation:** rotate local auth by stopping veda, deleting `run/veda-token`, starting veda, and updating MCP clients with the new token. If `VEDA_AUTH_TOKEN` is managed externally, rotate that secret and restart the service.
- **Client config:** local MCP clients should read `run/veda-token` or be configured with the same `VEDA_AUTH_TOKEN`.
- **SSRF guard:** `fetch_url` accepts only `http`/`https` URLs whose host resolves to public IPs. It blocks localhost, `.local`, private, loopback, link-local, multicast, reserved, and otherwise non-global addresses.
- **Tool throttling:** the MCP dispatcher applies conservative per-tool sliding-window limits before calling the core. Transport-level pacing still controls platform-facing request cadence.
- **Logs:** launchd logs write to `~/Library/Logs/veda-server.log`, avoiding macOS Documents privacy blocks and keeping service logs out of git.
- **Stop/status:** `scripts/veda-server stop` must stop the launchd service when loaded; `status` must call `health_status` with the local bearer token.

### 1.6 The fetch ladder (inside `_transport`)
```text
central config
  ├─ Reddit `.json` route (default off)
  │    → tier1 requests → tier2 StealthyFetcher → tier3 dynamic/Chromium
  └─ Reddit HTML route (default on)
       → old.reddit HTML page → parse → canonical shape
```

Runtime flags:

```text
VEDA_REDDIT_JSON_ENABLED=0
VEDA_REDDIT_HTML_ENABLED=1
VEDA_EXTERNAL_GITHUB_RAW_ENABLED=1
VEDA_EXTERNAL_TIER1_ENABLED=1
VEDA_EXTERNAL_TIER2_ENABLED=1
VEDA_EXTERNAL_TIER3_ENABLED=1
```

---

## 2. Origin of the code
veda's core is **ported from an existing scraping implementation** (transport, the `.json` tier ladder, the `html_thread`/`html_user` parsers, thread/rules/share-link logic, the user-profile + external-page scrapers). Porting it is a mechanical move + the correctness fixes in §4. (Git origin only — no runtime coupling.)

---

## 3. Canonical data shapes (the contracts)

### 3.1 `ThreadResult` (`fetch_thread`)
```text
{ post: {title, author, subreddit, subreddit_prefixed, score, upvote_ratio,
         num_comments, created_utc, permalink, url, selftext, link_flair,
         is_self, over_18, locked, archived},
  comments: [ {id, author, body, score, created_utc, depth, parent_id,
               permalink, is_op, edited, gilded, replies:[...]} ],
  subreddit_rules: [ Rule ],
  meta: {scraped_at, source_url, comments_fetched, comments_collapsed, sort, route} }
```
`route` = `"json"` | `"html"` (which path won — observability, not a shape difference).

### 3.2 `UserResult` (`fetch_user`)
```text
{ posts:    [ {type:"post", subreddit, title, score, created_utc, permalink} ],
  comments: [ {type:"comment", subreddit, body, score, created_utc, permalink} ] }
```

### 3.3 Profile fields (merged into `UserResult`)
`fetch_user` results include `username, bio, links, post_karma, comment_karma,
created_utc` extracted from the old.reddit titlebox sidebar that appears on the
listing pages already being fetched (no extra request on the HTML route; one
profile-page read when the JSON route satisfies the listings). Values are
`null` when the markup lacks them.

### 3.4 `Rule` (`fetch_rules` → list)
```text
{ short_name, description, ... }
```

### 3.5 `ExternalDoc` (`fetch_url`)
```text
{ url, status, route, content_type, text, title, truncated }
```
`text` is markdown-style readable text (trafilatura extraction, xpath fallback),
robots-honored and capped to `max_chars`; `truncated` flags when the cap cut
content; `title` is the extracted page title (may be `null`). The external
ladder always tries tier1 (plain request) first for every host, then escalates
tier2 (stealth) → tier3 (dynamic browser) while extracted text is thin.
robots.txt is fetched with a plain status-checked request, never the browser
ladder. GitHub repo-root URLs resolve READMEs via the `HEAD` ref with a
status-checked fetch.

### 3.6 Parity gap (the defect that blocks everything)
The HTML thread parser currently returns only `{author,body,replies}` per comment and `{author,subreddit,title,selftext}` per post; the shaper back-fills `score=0, is_op=False, …`. The HTML user parser already extracts score/created from the *same* markup — proof the data is there. **#1 = close this gap so the HTML branch == the structured branch.** Enforced by a parity test (§7).

---

## 4. Correctness defects veda must fix

Severity: 🔴 wrong data · 🟠 silent empty/fail · 🟢 cosmetic.

| # | Sev | Defect | Where |
|---|-----|--------|-------|
| **1** | 🔴 | HTML thread parser drops `score/created_utc/is_op/id` → callers can't rank/identify comments. | `_html_thread` + the result shaper |
| **2** | 🟠 | `fetch_rules` uses the blocked `.json` route → returns `[]`. | `rules.py` |
| **3** | 🟠 | `/s/` share links resolved via blocked plain `requests` → unresolved → hard fail. | `thread.py` |
| **4** | 🟢 | HTML-route post `score=0`, comment count wrong. Folded into #1. | result shaper |

**Deferred (not a fix yet):** the dead `.json` tiers (latency) — keep the JSON-first→HTML flow as-is; revisit after health monitoring (§8).

---

## 5. Design per fix
- **#1 (keystone):** in `_html_thread`, extract comment `score` (`.score.unvoted[title]`), `created_utc` (`data-timestamp`), `is_op` (`a.author.submitter` in the comment's own entry), `id` (`data-fullname` → strip `t1_`); post `score`/`created_utc`/real `num_comments`. The shaper carries real values. **Robustness:** missing-node tolerance, `[deleted]`/`[removed]` bodies, the three score spans (pick `unvoted`), gilded/edited/stickied, deep reply trees + `more`, quarantine/over-18 interstitials, `after` pagination.
- **#2:** `fetch_rules` → structured-first → HTML `/about/rules`.
- **#3:** resolve `/s/` via stealth before normalising, inside `fetch_thread`.
- **#4:** post metadata extracted with #1.
- **Profile fields:** `_html_profile.py` extracts bio/links/karma/created from the titlebox; `fetch_user` merges them into `UserResult`.
- **`fetch_url`:** port the external scraper → `external/fetch.py` → `ExternalDoc` (robots, host-routing, escalation, text-cap).
- **Health monitoring (M5):** `health.py` tracks per-tool / per-route success rates, `.json`-vs-HTML hit ratio, block/parse-error counts, latency; surfaced via a status tool/endpoint + `/veda-server status`.

---

## 6. The `.json` tier policy
Reddit gates `.json`, so `.json` requests currently return blocked HTML instead of JSON from this
environment. **Decision (2026-06-10):** disable Reddit `.json` by default via
`VEDA_REDDIT_JSON_ENABLED=0` and go straight to old.reddit HTML. Keep the `.json` implementation
behind the config flag so it can be re-enabled for future probes without code changes.

---

## 7. Test strategy
- **Parity test** (linchpin): one fixture → structured-branch parse and HTML-branch parse → assert identical field sets + values where determinable. Fails if HTML drifts.
- **Boundary test:** AST-scan `veda/**` → no imports outside veda's allowed deps; no caller-specific code.
- **Unit (core):** real HTML fixtures → `_html_thread` yields `score/is_op/created_utc/id`; share-link resolve; rules parse; robustness (deleted bodies, missing nodes, score-span variants, pagination).
- **MCP-tool test (shell):** call each tool against an in-process server fixture; args→kwargs, results = §3 shapes, `VedaError`→MCP error with `.code`.
- **Contract test:** every tool result is JSON-serializable (it crosses the wire).
- **Health test:** metrics increment correctly per route/outcome.
- **Security tests:** bearer-token middleware blocks unauthenticated MCP traffic; `fetch_url` rejects localhost/private DNS targets; tool dispatcher reports `rate_limited`.
- **Config tests:** default Reddit `.json` is disabled; explicit env flags can re-enable JSON or disable HTML/external tiers.

---

## 8. Open / deferred
- **`.json`-drop** — deferred until M5 health data (§6).
- **Multi-platform interface** — deferred until a second platform exists.
- **Remote deploy + production auth** — later (local bearer auth exists; remote hosting still needs HTTPS/domain and stronger auth policy).

---

## 9. Task list (TDD, one slice per commit, one PR per milestone)

### M0 — Repo + MCP server scaffold
- [x] Init repo at `~/Documents/Services/Veda` → remote `git@github.com:BarterX-Tech/veda.reddit-operator.git`; `pyproject.toml` (deps scrapling/lxml/requests/`mcp`), `.github` CI
- [x] Scaffold core (`_transport` + rate-limiter, `errors`, `reddit/`, `external/`) + shell (`mcp/{server,tools}.py`); `tests/`
- [x] **Port** the scraping logic in: transport + `.json` ladder → `_transport`; HTML thread/user parsers → `reddit/_html_*`; thread/rules/share-link → `reddit/{thread,rules}.py` (no behavior change yet)
- [x] Stand up the five core reads (delegating to ported logic); stub TypedDicts + `VedaError`
- [x] **MCP server** (`mcp/server.py`, HTTP/SSE): register the 5 tools; error→MCP mapping; MCP-tool tests
- [x] **Boundary test** + **parity-test harness**
- [x] **Ops:** `scripts/veda-server` (start/stop/status) + `launchd` unit; always-updated `README`; `/veda-server` Claude command
- [x] Move these PRD docs into the repo (`docs/`); leave a pointer stub in the origin repo
- [x] PR: M0 (server runs; 5 tools callable)

### M1 — Field-complete thread parser (#1, #4) — keystone
- [x] Fixture: real old.reddit `/comments/` HTML
- [x] Failing parity test: HTML comment `score/is_op/created_utc/id` present
- [x] Extract comment `score/created_utc/is_op/id`; post `score/created_utc/num_comments`; shaper carries real values
- [x] Robustness: deleted/removed bodies, missing-node tolerance, deep trees + `more`, score-span variant
- [x] PR: M1

### M2 — Rules + share links (#2, #3)
- [x] `fetch_rules` structured→HTML `/about/rules`
- [x] `/s/` resolve via stealth inside `fetch_thread`
- [x] Tests: rules populate; `/s/` resolves; README updated
- [x] PR: M2

### M3 — `fetch_user` + `fetch_profile` tools *(fetch_profile later merged into fetch_user, 2026-06-12)*
- [x] `fetch_user` (structured→`_html_user`, `UserResult`)
- [x] `fetch_profile` (`_html_profile` → `ProfileResult`)
- [x] Tool + contract tests; README
- [x] PR: M3

### M4 — `fetch_url` external tool
- [x] Port external scraper → `external/fetch.py` → `ExternalDoc`; expose the tool
- [x] Preserve robots / host-routing / escalation / text-cap; tests; README
- [x] PR: M4

### M5 — Health monitoring
- [x] `health.py`: per-tool/route success rates, `.json`-vs-HTML ratio, error counts, latency
- [x] Status surface (tool/endpoint + `/veda-server status`); README health section
- [x] PR: M5 — *informs the later `.json`-drop decision*

### M5.5 — Central scrape-route config
- [x] Add central config for Reddit JSON/HTML and external route toggles
- [x] Disable Reddit `.json` by default
- [x] Expose active config in `health_status`
- [x] Tests + README/PRD updates

### M6 — Local security hardening
- [x] Keep local service bound to `127.0.0.1`
- [x] Add optional bearer-token auth for MCP traffic
- [x] Generate/store local token outside git for launchd and script starts
- [x] Document local token validity and rotation procedure
- [x] Block private/internal targets in `fetch_url`
- [x] Add per-tool sliding-window limits at the MCP dispatcher
- [x] Update `scripts/veda-server stop/status` for launchd + token-aware health checks
- [x] Tests + README/PRD updates

### M7 — External fetch reliability + extraction quality (2026-06-11)
- [x] Root cause: bare `scrapling` dep left `[fetchers]` extra uninstalled — tier2/tier3 failed every call (`No module named 'curl_cffi'`), and non-allowlisted hosts skipped tier1, so most external fetches returned `Blocked`
- [x] `scrapling[fetchers]>=0.4` + `trafilatura` in `pyproject.toml`
- [x] Tier capability probe (`tier_capabilities`) in `health_status` + loud startup warning
- [x] Ladder: tier1 always first for every host; tier failures logged, not swallowed
- [x] robots.txt via plain status-checked request (no browser ladder)
- [x] trafilatura markdown extraction with xpath fallback; `ExternalDoc` gains `title` + `truncated`
- [x] GitHub raw README: `HEAD` ref, repo-root URLs only, status-checked fetch
- [x] `scripts/veda-canary` live probes; CI step imports stealth fetchers

### Later (separate effort)
- [x] `.json` re-enable/drop decision using health data and live probes
- [x] Deploy the MCP server to a real host (flip `localhost` → host + production auth)
- [x] Schedule `scripts/veda-canary` (launchd) and persist health metrics across restarts
