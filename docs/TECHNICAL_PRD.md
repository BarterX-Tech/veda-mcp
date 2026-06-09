# veda — Technical PRD

**Status:** DRAFT · **Date:** 2026-06-09 · **Owner:** Nitin
**Companion:** [`PRD.md`](./PRD.md). This is the deep spec — repo layout, tool contract, parser specs, tests, tasks.

> **Scope discipline:** this document describes **veda only**. veda is caller-agnostic — it never references a consumer, what the data is used for, or any other project. Its contract is *requested resource → clean data*.

---

## 1. Architecture

### 1.0 Repository, runtime, integration
- **Repo:** `git@github.com:BarterX-Tech/veda.reddit-operator.git` · **Path:** `~/Documents/Services/Veda`
- **veda is an MCP server.** It exposes its reads as **MCP tools over HTTP/SSE** (Streamable HTTP) and runs as **one long-lived server** (locally via `launchd`; a real host later — same shape).
- **One server ⇒ one rate-limiter + one browser pool + one cache** against the platform. Any MCP client connects to the same server.
- **Internal shape:** veda = **scraping core** (transport, parsers, the read functions) + a **thin MCP shell** that registers the tools. The core is MCP-agnostic and unit-testable on its own.
- **Dependencies:** stdlib + scrapling + lxml + requests + an MCP server lib. **Nothing else.** veda imports nothing from any caller and has no knowledge one exists.

### 1.1 Sub-scrapers (one per source)
- `veda.reddit` — Reddit reads (this PRD's focus).
- `veda.external` — generic non-Reddit web pages (robots-aware).
- *(future)* `veda.x`, etc.

Each tries the source's structured route, falls back to scraping HTML, returns a **canonical shape**.

### 1.2 The contract — core functions ↔ MCP tools
The **core** is five functions; the **MCP shell** exposes each as a tool of the same name. Tool args = function kwargs; tool result = the JSON shape (§3). Errors are typed and carry a `.code`.

```python
# CORE (the scraping library the tools wrap)
def fetch_thread(url: str, *, comment_limit: int = 500,
                 comment_sort: str = "top") -> ThreadResult: ...   # post + comment tree
def fetch_user(username: str, *, kinds=("submitted", "comments"),
               pages: int = 2) -> UserResult: ...                  # post/comment history
def fetch_profile(username: str) -> ProfileResult: ...             # about/bio page + linked URLs
def fetch_rules(subreddit: str) -> list[Rule]: ...                 # subreddit rules
def fetch_url(url: str, *, max_chars: int = 20000) -> ExternalDoc: ...  # robots-aware readable text

class VedaError(Exception): ...   # base (carries .code)
class Blocked(VedaError): ...     # platform gated / unreachable
class NotFound(VedaError): ...    # 404
class ParseError(VedaError): ...  # markup unparseable
```

**MCP tools (HTTP/SSE):** `fetch_thread`, `fetch_user`, `fetch_profile`, `fetch_rules`, `fetch_url` — names/args/results 1:1 with the core. `VedaError` → MCP tool error carrying `.code`. Inputs are `str`/`int`/tuples; outputs are plain JSON-serializable dicts/lists; **no side effects** (veda returns data, persists nothing).

### 1.3 Repo layout (`~/Documents/Services/Veda`)
```text
Veda/
  pyproject.toml          # package `veda`; deps: scrapling, lxml, requests, mcp
  README.md               # ALWAYS-UPDATED: run/config, tool reference, health/metrics (synced each milestone)
  .github/workflows/      # CI: tests + boundary + contract on every push
  scripts/
    veda-server           # start/stop/status entrypoint (backs /veda-server + launchd)
    tech.barterx.veda.plist# launchd unit for the local always-on server
  veda/
    __init__.py
    _transport.py         # fingerprint/headers, StealthyFetcher wrappers, rate-limiter, .json/HTML tier ladder
    errors.py             # VedaError hierarchy
    reddit/
      __init__.py         # core reads: fetch_thread, fetch_user, fetch_profile, fetch_rules
      types.py            # ThreadResult, UserResult, ProfileResult, Rule (TypedDict) + shapers
      _html_thread.py     # HTML thread parser — field-complete (#1)
      _html_user.py       # HTML user parser
      _html_profile.py    # HTML about/bio parser
      thread.py / user.py / profile.py / rules.py
    external/
      __init__.py         # core read: fetch_url
      fetch.py            # robots check, host routing, extraction, escalation
    mcp/
      server.py           # MCP server (HTTP/SSE): registers the 5 tools
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
- **Client config:** local MCP clients should read `run/veda-token` or be configured with the same `VEDA_AUTH_TOKEN`.
- **SSRF guard:** `fetch_url` accepts only `http`/`https` URLs whose host resolves to public IPs. It blocks localhost, `.local`, private, loopback, link-local, multicast, reserved, and otherwise non-global addresses.
- **Tool throttling:** the MCP dispatcher applies conservative per-tool sliding-window limits before calling the core. Transport-level pacing still controls platform-facing request cadence.
- **Logs:** launchd logs write to `~/Library/Logs/veda-server.log`, avoiding macOS Documents privacy blocks and keeping service logs out of git.
- **Stop/status:** `scripts/veda-server stop` must stop the launchd service when loaded; `status` must call `health_status` with the local bearer token.

### 1.6 The fetch ladder (inside `_transport`)
```text
.json tier1 (requests, old.reddit/.json)     ┐ .json routes are Cloudflare-gated →
  → tier2 (StealthyFetcher on .json)          │ fail in practice (kept as-is for now; see §8)
  → tier3 (dynamic/Chromium on .json)         ┘
  → HTML fallback (StealthyFetcher → HTML page) → parse → canonical shape   ← the working route
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

### 3.3 `ProfileResult` (`fetch_profile`)
```text
{ username, bio, links: [str] }     # about/bio text + linked external URLs
```

### 3.4 `Rule` (`fetch_rules` → list)
```text
{ short_name, description, ... }
```

### 3.5 `ExternalDoc` (`fetch_url`)
```text
{ url, status, route, content_type, text }   # readable text, robots-honored, length-capped
```

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
- **`fetch_profile`:** port the about/bio extractor → `_html_profile.py`; `profile.py` fetches `/user/<u>/` → `ProfileResult`.
- **`fetch_url`:** port the external scraper → `external/fetch.py` → `ExternalDoc` (robots, host-routing, escalation, text-cap).
- **Health monitoring (M5):** `health.py` tracks per-tool / per-route success rates, `.json`-vs-HTML hit ratio, block/parse-error counts, latency; surfaced via a status tool/endpoint + `/veda-server status`.

---

## 6. The `.json` tier policy
Reddit gates `.json`, so tiers 1–3 mostly fail before the HTML route wins (a latency cost). **Decision (2026-06-09):** keep the flow **as-is for now**; collect real success-rate data via health monitoring (M5), then decide whether to drop the `.json` tiers. No reshape until then.

---

## 7. Test strategy
- **Parity test** (linchpin): one fixture → structured-branch parse and HTML-branch parse → assert identical field sets + values where determinable. Fails if HTML drifts.
- **Boundary test:** AST-scan `veda/**` → no imports outside veda's allowed deps; no caller-specific code.
- **Unit (core):** real HTML fixtures → `_html_thread` yields `score/is_op/created_utc/id`; share-link resolve; rules parse; robustness (deleted bodies, missing nodes, score-span variants, pagination).
- **MCP-tool test (shell):** call each tool against an in-process server fixture; args→kwargs, results = §3 shapes, `VedaError`→MCP error with `.code`.
- **Contract test:** every tool result is JSON-serializable (it crosses the wire).
- **Health test:** metrics increment correctly per route/outcome.
- **Security tests:** bearer-token middleware blocks unauthenticated MCP traffic; `fetch_url` rejects localhost/private DNS targets; tool dispatcher reports `rate_limited`.

---

## 8. Open / deferred
- **`.json`-drop** — deferred until M5 health data (§6).
- **Multi-platform interface** — deferred until a second platform exists.
- **Remote deploy + production auth** — later (local bearer auth exists; remote hosting still needs HTTPS/domain and stronger auth policy).

---

## 9. Task list (TDD, one slice per commit, one PR per milestone)

### M0 — Repo + MCP server scaffold
- [ ] Init repo at `~/Documents/Services/Veda` → remote `git@github.com:BarterX-Tech/veda.reddit-operator.git`; `pyproject.toml` (deps scrapling/lxml/requests/`mcp`), `.github` CI
- [ ] Scaffold core (`_transport` + rate-limiter, `errors`, `reddit/`, `external/`) + shell (`mcp/{server,tools}.py`); `tests/`
- [ ] **Port** the scraping logic in: transport + `.json` ladder → `_transport`; HTML thread/user parsers → `reddit/_html_*`; thread/rules/share-link → `reddit/{thread,rules}.py` (no behavior change yet)
- [ ] Stand up the five core reads (delegating to ported logic); stub TypedDicts + `VedaError`
- [ ] **MCP server** (`mcp/server.py`, HTTP/SSE): register the 5 tools; error→MCP mapping; MCP-tool tests
- [ ] **Boundary test** + **parity-test harness**
- [ ] **Ops:** `scripts/veda-server` (start/stop/status) + `launchd` unit; always-updated `README`; `/veda-server` Claude command
- [ ] Move these PRD docs into the repo (`docs/`); leave a pointer stub in the origin repo
- [ ] PR: M0 (server runs; 5 tools callable)

### M1 — Field-complete thread parser (#1, #4) — keystone
- [ ] Fixture: real old.reddit `/comments/` HTML
- [ ] Failing parity test: HTML comment `score/is_op/created_utc/id` present
- [ ] Extract comment `score/created_utc/is_op/id`; post `score/created_utc/num_comments`; shaper carries real values
- [ ] Robustness: deleted/removed bodies, missing-node tolerance, deep trees + `more`, score-span variant
- [ ] PR: M1

### M2 — Rules + share links (#2, #3)
- [ ] `fetch_rules` structured→HTML `/about/rules`
- [ ] `/s/` resolve via stealth inside `fetch_thread`
- [ ] Tests: rules populate; `/s/` resolves; README updated
- [ ] PR: M2

### M3 — `fetch_user` + `fetch_profile` tools
- [ ] `fetch_user` (structured→`_html_user`, `UserResult`)
- [ ] `fetch_profile` (`_html_profile` → `ProfileResult`)
- [ ] Tool + contract tests; README
- [ ] PR: M3

### M4 — `fetch_url` external tool
- [ ] Port external scraper → `external/fetch.py` → `ExternalDoc`; expose the tool
- [ ] Preserve robots / host-routing / escalation / text-cap; tests; README
- [ ] PR: M4

### M5 — Health monitoring
- [ ] `health.py`: per-tool/route success rates, `.json`-vs-HTML ratio, error counts, latency
- [ ] Status surface (tool/endpoint + `/veda-server status`); README health section
- [ ] PR: M5 — *informs the later `.json`-drop decision*

### M6 — Local security hardening
- [ ] Keep local service bound to `127.0.0.1`
- [ ] Add optional bearer-token auth for MCP traffic
- [ ] Generate/store local token outside git for launchd and script starts
- [ ] Block private/internal targets in `fetch_url`
- [ ] Add per-tool sliding-window limits at the MCP dispatcher
- [ ] Update `scripts/veda-server stop/status` for launchd + token-aware health checks
- [ ] Tests + README/PRD updates

### Later (separate effort)
- [ ] `.json`-drop decision using M5 data
- [ ] Deploy the MCP server to a real host (flip `localhost` → host + production auth)
