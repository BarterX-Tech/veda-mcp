# veda — PRD

**Status:** DRAFT · **Date:** 2026-06-09 · **Owner:** Nitin
**Deep dive:** [`TECHNICAL_PRD.md`](./TECHNICAL_PRD.md) — repo layout, tool contract, parser specs, tasks.

**Client integration:** [`INTEGRATION_PRD.md`](./INTEGRATION_PRD.md) — how clients connect to
veda and use the tools safely.

The zoom-out picture of **veda**: what it is, the one job it does, and what "done" looks like. veda is a self-contained service; it knows nothing about who calls it or what they do with the data.

---

## 1. What this is

**veda** is a standalone **platform-read service**. Give it a URL, a username, or a subreddit; it returns clean, structured data. Starting with Reddit (`veda.reddit`), with generic web (`veda.external`) and future platforms (`veda.x`, …) as sibling sub-scrapers.

- **Repo:** `git@github.com:BarterX-Tech/veda.reddit-operator.git` · **Path:** `~/Documents/Services/Veda`
- **Interface:** an **MCP server over HTTP/SSE** exposing a few read tools.
- **Runs as** one long-lived server (locally via `launchd`; a real host later).

veda is **step 1 of modularising a larger system** into independent services. **Strict isolation is the point:** veda has no idea what a caller is building, how the data is used, or that any particular client exists. Its entire contract is *requested resource → clean data*. It follows its instructions and returns the data — nothing more.

---

## 2. The one job, done well

### 2a. One way to read a platform
Reddit has two front doors: the **`.json` route** (clean, but Cloudflare-blocks our traffic) and the **HTML page** (a stealth browser still loads it; veda parses it).

> **Try the structured route first. If it fails, scrape the HTML page — and return the same shape of data either way.**

```text
   any MCP client
        │  calls a tool: fetch_thread / fetch_user / fetch_profile / fetch_rules / fetch_url
        ▼
   ┌──────────────────────────────────────┐
   │  veda  (MCP server, HTTP/SSE)         │   try structured route ─► blocked ─► scrape HTML
   │   core: transport + parsers           │                                         │
   │   + one rate-limiter + cache          │   ◄────────── same canonical shape ◄────┘
   └──────────────────────────────────────┘
        knows nothing about the caller
```

The non-negotiable: **the HTML route returns the same fields as the structured route.** If HTML hands back less, the data is silently degraded. That **shape-parity** is veda's core quality bar.

### 2b. Isolation
veda is its own repo + its own process. It imports only the standard library + scraping tools (scrapling, lxml) + an MCP server lib. It depends on **nothing** outside itself and is **unaware of any caller**. One running server means **one rate-limiter** against the platform — the single coordination point that keeps us un-blocked.

Internally, veda = **scraping core** (transport, parsers, the read functions) + a **thin MCP shell** (registers the tools). Because it's MCP-over-HTTP, veda *is* the deployable service — no extra web layer later.

---

## 3. Why it matters

Whatever consumes veda is only as good as the data veda returns. Two correctness bars veda must hit (the current scraping logic fails both):

- **Completeness:** a thread's comments must come back **with their scores, OP-flags, and ids** — so a caller can tell the top/relevant comments from the rest. Today the HTML route drops these.
- **Reliability:** rules, share-links, and user pages must actually resolve over the working route — not silently return empty because they tried only the blocked `.json`.

A clean, well-tested read service is reusable by any client and across platforms, and a single choke point makes rate-limiting + reliability solvable in one place.

---

## 4. What's broken in the current scraping logic (veda must fix on the way in)

| # | Problem | Cost |
|---|---------|------|
| 1 | **HTML thread parse is lossy** — drops comment score / OP-flag / id / timestamp. | 🔴 Callers can't identify top comments; data silently degraded. |
| 2 | **Rules fetched over the blocked `.json`** → empty list. | 🟠 `fetch_rules` returns nothing. |
| 3 | **Mobile share links (`/s/…`) not resolved** before the blocked route is tried → hard fail. | 🟠 Some threads won't load. |
| 4 | **Post metadata gaps on the HTML route** (`score=0`, wrong comment count). | 🟢 Folded into #1. |

Root cause: the HTML parser returns **fewer fields** than the structured parser (parity gap), and a couple of reads never got the HTML fallback. veda fixes both as it absorbs the code — its parsers become field-complete and every read goes through the same structured→HTML→canonical path.

*(Separately: the `.json` tiers are mostly dead weight today — veda keeps the JSON-first→HTML flow **as-is for now** and revisits dropping `.json` only after health monitoring shows the real `.json` success rate.)*

---

## 5. What "done" looks like

- ✅ A standalone **veda repo + MCP server** exposing five tools: `fetch_thread`, `fetch_user`, `fetch_profile`, `fetch_rules`, `fetch_url`.
- ✅ **structured-first → HTML-fallback → identical shape** inside veda; field-complete parsers (scores, OP-flags, ids, timestamps).
- ✅ **Strict isolation** — zero knowledge of any caller; depends on nothing external (boundary test enforces it).
- ✅ One server, **one rate-limiter** + cache against the platform; robust parsing (deleted bodies, missing nodes, deep trees, pagination).
- ✅ **Health monitoring** — per-tool/route success rates, `.json`-vs-HTML ratio, latency.
- ✅ Ops: **always-updated README** + a **`/veda-server` start/stop/status command**.
- ✅ Service-ready: deploying to a real host later is just pointing the MCP config at a URL.

---

## 6. Scope

**In:** the standalone veda repo; its MCP server (HTTP/SSE) + tools; the scraping core (transport, parsers, rate-limiter) ported and made **field-complete + robust**; health monitoring; ops (README, `/veda-server`).

**Out:** anything about callers or how the data is used; remote/production deployment (runs locally first); a generic cross-platform interface (Reddit + external concrete now, generalise when X arrives); authenticated platform APIs / OAuth (public reads only).

---

## 7. Roadmap (milestones)

Granular checkboxes in [`TECHNICAL_PRD.md` §9](./TECHNICAL_PRD.md):

- [ ] **M0 — Stand up the veda repo + MCP server.** Init repo, port the scraping core, build the MCP server (5 tools, HTTP/SSE) + rate-limiter, README, `/veda-server` + launchd, boundary + parity-test harness.
- [ ] **M1 — Field-complete thread parser (#1, #4).** HTML thread parse returns score/OP/id/created; shape-parity tests. *The keystone.*
- [ ] **M2 — Rules + share links (#2, #3).** `fetch_rules` over HTML; `/s/` resolution.
- [ ] **M3 — `fetch_user` + `fetch_profile` tools.**
- [ ] **M4 — `fetch_url` (external) tool.**
- [ ] **M5 — Health monitoring.** Success rates, route ratio, latency; status surface.
- [ ] *(Later)* `.json`-drop decision (using M5 data); deploy the server to a real host.

Each milestone ships test-first, one reviewable PR, with your sign-off before the next.

---

## 8. Decisions (confirmed 2026-06-09)

- **Standalone repo** (`~/Documents/Services/Veda`) · **MCP server over HTTP/SSE** · one server, one rate-limiter.
- **Strict isolation** — veda knows nothing about callers; depends on nothing external.
- **Scope = pure platform reads;** Reddit-concrete now, generalise later.
- **`.json` policy:** keep JSON-first→HTML **as-is**; revisit dropping `.json` after health monitoring (M5).
- Ops: always-updated README + `/veda-server` command.

**Operator-side adoption** (MCP client, repointing, the feedback loop, removing the operator's own scraping) is tracked separately in `reddit-operator/docs/veda-integration/` — **not here**, because veda must stay caller-agnostic.

**Ready to begin M0.**
