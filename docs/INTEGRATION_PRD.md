# veda — Integration PRD

**Status:** DRAFT · **Date:** 2026-06-10 · **Owner:** Nitin
**Companions:** [`PRD.md`](./PRD.md), [`TECHNICAL_PRD.md`](./TECHNICAL_PRD.md)

This document explains how any client should integrate with **veda**. It is intentionally
client-agnostic: veda does not know who is calling it, what workflow the data supports, or where
the data goes after it is returned. The integration contract is simple:

```text
client sends plain MCP tool args -> veda returns plain JSON data or a typed error
```

---

## 1. Purpose

veda is the read service for public Reddit and generic web pages. Clients should use it whenever
they need fresh structured data from:

- a Reddit thread URL
- a Reddit username
- a Reddit profile/about page
- a subreddit rules page
- a non-Reddit web URL

Clients should not scrape these sources themselves. Centralizing reads in veda gives every client
the same canonical shapes, one shared rate limiter, one cache, one health surface, and one place to
fix parser breakage.

---

## 2. Integration Shape

### 2.1 Transport

veda runs as a long-lived MCP server over **Streamable HTTP**.

Local default endpoint:

```text
http://127.0.0.1:8765/mcp
```

Local lifecycle:

```bash
scripts/veda-server start
scripts/veda-server status
scripts/veda-server stop
```

Production or remote deployments should keep the same MCP shape and swap only the endpoint URL,
host, auth, and service-management layer.

Active scrape routes are service configuration, not client contract. Local defaults currently keep
Reddit `.json` disabled (`VEDA_REDDIT_JSON_ENABLED=0`) and Reddit HTML enabled
(`VEDA_REDDIT_HTML_ENABLED=1`) because live `.json` probes return blocked HTML.

### 2.2 Tools

Clients call five MCP tools:

| Tool | Use |
| --- | --- |
| `fetch_thread` | Get a Reddit post plus a comment tree. |
| `fetch_user` | Get a Reddit user's profile (bio, links, karma, account age) plus recent posts and/or comments. |
| `fetch_rules` | Get subreddit rules. |
| `fetch_url` | Get readable text for a generic web URL. |
| `health_status` | Inspect service health metrics. |

The first four are data-read tools. `health_status` is operational and should be used by clients,
monitors, and deployment checks.

---

## 3. Client Responsibilities

Clients should:

- Treat veda outputs as the canonical data shape.
- Handle typed errors by `.code`.
- Preserve veda's returned metadata, especially `route`, `comments_fetched`,
  `comments_collapsed`, and `scraped_at`.
- Avoid retry storms. If a call fails with `blocked`, pause or back off rather than looping.
- Use `health_status` before broad backfills or scheduled runs.
- Keep client-specific interpretation outside veda.

Clients should not:

- Ask veda to save files or persist caller state.
- Depend on route internals beyond observability fields.
- Re-scrape Reddit or external URLs as a fallback without first checking veda health.
- Send workflow-specific state, prompts, campaign labels, user preferences, or private context to
  veda.

---

## 4. Tool Contracts

### 4.1 `fetch_thread`

```python
fetch_thread(url: str, comment_limit: int = 500, comment_sort: str = "top") -> ThreadResult
```

Use when a client needs the full context of a Reddit post and its comments.

Expected input:

- Any Reddit thread URL, including old/new/www/mobile variants.
- Mobile share links such as `/s/...` are supported.

Output shape:

```text
{
  post: {
    title, author, subreddit, subreddit_prefixed, score, upvote_ratio,
    num_comments, created_utc, permalink, url, selftext, link_flair,
    is_self, over_18, locked, archived
  },
  comments: [
    {
      id, author, body, score, created_utc, depth, parent_id,
      permalink, is_op, edited, gilded, replies:[...]
    }
  ],
  subreddit_rules: [Rule],
  meta: {
    scraped_at, source_url, comments_fetched, comments_collapsed, sort, route
  }
}
```

Client use cases:

- Thread summarization
- Comment ranking or triage
- Compliance checks against subreddit rules
- Conversation context assembly
- Outcome or analytics systems that need stable comment IDs and scores

Client notes:

- Prefer `comment_sort="top"` when the downstream task needs high-signal comments.
- Use `comments_collapsed` to decide whether the result is enough or whether a deeper read strategy
  is needed later.
- The `route` field is operational. Clients should currently expect Reddit routes to be `html`
  unless service operators explicitly re-enable Reddit `.json`.

### 4.2 `fetch_user`

```python
fetch_user(username: str, kinds=("submitted", "comments"), pages: int = 2) -> UserResult
```

Use when a client needs a Reddit user's public profile and/or recent activity.

Output shape:

```text
{
  username, bio, links:[str], post_karma, comment_karma, created_utc,
  posts: [
    {type:"post", subreddit, title, score, created_utc, permalink}
  ],
  comments: [
    {type:"comment", subreddit, body, score, created_utc, permalink}
  ]
}
```

Client use cases:

- Public activity summaries
- Profile context (bio, external links, karma, account age)
- Community/activity analysis
- External link discovery for follow-up `fetch_url` calls
- Finding recent public comments or submissions for later `fetch_thread` calls

Client notes:

- Use `kinds=("comments",)` or `kinds=("submitted",)` when only one listing type is needed.
- Use low `pages` values for interactive workflows; increase only for batch jobs.
- veda may combine a successful structured listing with an HTML fallback for the other kind.
- `links` excludes Reddit links and dedupes repeated URLs.
- `bio`, `post_karma`, `comment_karma`, and `created_utc` come from the profile
  sidebar and are `null` when not present in the markup.
- Profile fields are extracted from listing pages veda already fetches, so they
  cost no extra requests on the default HTML route.
- New-style profile bios and social links never appear in old.reddit markup;
  when the sidebar has none, veda makes one stealth fetch of the new-reddit
  profile page to fill `bio` and `links`.

### 4.3 `fetch_rules`

```python
fetch_rules(subreddit: str) -> list[Rule]
```

Use when a client needs subreddit rules without loading a full thread.

Output shape:

```text
[
  {short_name, description, ...}
]
```

Client use cases:

- Preflight policy checks
- Moderation/rule summaries
- Rule-aware generation or validation systems

Client notes:

- The subreddit may be passed as `macapps` or `r/macapps`.
- veda uses the configured Reddit routes. Local defaults skip structured rules JSON and use
  old.reddit HTML.

### 4.4 `fetch_url`

```python
fetch_url(url: str, max_chars: int = 20000) -> ExternalDoc
```

Use when a client needs readable text from a non-Reddit web URL.

Output shape:

```text
{ url, status, route, content_type, text, title, truncated }
```

Client use cases:

- Reading a profile-linked website
- Fetching public project pages
- Pulling article or blog text
- Reading GitHub repository README content

Client notes:

- veda honors robots.txt.
- GitHub repository root URLs use the raw README route when available.
- `text` is markdown-style readable text with block separation (headings,
  paragraphs); JS-rendered sites are handled by browser tiers automatically.
- `title` is the extracted page title and may be `null`.
- `max_chars` caps returned text for downstream token control; `truncated` is
  `true` when the cap cut content, so clients can re-fetch with a larger budget
  instead of treating the result as complete.
- `route` may be `github_raw`, `tier1`, `tier2`, or `tier3`. Every host tries
  the cheap `tier1` route first and escalates only when extracted text is thin.

### 4.5 `health_status`

```python
health_status() -> dict
```

Use before and after scheduled work, batch reads, or client-level monitoring.

Output shape:

```text
{
  tools: {
    tool_name: {
      calls, successes, errors, avg_latency_ms, routes, error_codes
    }
  },
  routes: {...},
  json_vs_html: {json, html, html_ratio},
  scraping_config: {...},
  tiers_available: {tier1: {available, detail}, tier2: {...}, tier3: {...}},
  totals: {calls, successes, errors}
}
```

Client use cases:

- Confirm the server is reachable.
- Confirm `tiers_available` before batch external reads — an unavailable tier
  means the service environment is degraded.
- Detect if Reddit `.json` routes are consistently blocked.
- Detect parser or platform failures by rising error counts.
- Decide whether a client batch should continue, slow down, or pause.

---

## 5. Error Handling

veda exposes typed errors derived from `VedaError`.

| Code | Meaning | Client behavior |
| --- | --- | --- |
| `blocked` | Platform gated, unreachable, disallowed, or no readable content. | Back off; check `health_status`; retry later if appropriate. |
| `not_found` | Resource does not exist or is unavailable. | Do not retry aggressively; surface as missing. |
| `parse_error` | Markup or payload could not be parsed. | Record the URL and route; retry later or escalate if repeated. |
| `veda_error` | Generic veda error. | Treat as service failure; check logs and health. |

Clients should branch on error `.code`, not on English message text.

---

## 6. Common Integration Recipes

### 6.1 Thread Context Recipe

Use when a client needs a Reddit thread context bundle.

1. Call `fetch_thread(url, comment_limit=500, comment_sort="top")`.
2. Read `post`, `comments`, and `subreddit_rules`.
3. Preserve `meta.route`, `meta.comments_fetched`, and `meta.comments_collapsed`.
4. If `comments_collapsed` is high, mark the output as partial rather than silently complete.

### 6.2 User Context Recipe

Use when a client needs public user activity.

1. Call `fetch_user(username, kinds=("submitted","comments"), pages=2)`.
2. Read profile fields (bio, links, karma, account age) from the same result.
3. For each external profile link, call `fetch_url(link, max_chars=<budget>)`.
4. Keep the profile/activity interpretation in the client.

### 6.3 Rules-Only Recipe

Use when a client needs policy or moderation context.

1. Call `fetch_rules(subreddit)`.
2. If rules are empty, call `health_status`.
3. Treat empty rules as "unavailable" rather than "no rules" unless independently verified.

### 6.4 External Page Recipe

Use when a client needs readable web text.

1. Call `fetch_url(url, max_chars=<budget>)`.
2. Use `route` to understand how the page was fetched.
3. Respect `blocked` as a real robots/platform refusal.

### 6.5 Batch Job Recipe

Use before scheduled or high-volume reads.

1. Call `health_status()`.
2. If error counts are rising, reduce concurrency or pause.
3. Run reads with bounded client-side concurrency.
4. Call `health_status()` again and store the before/after totals.

---

## 7. Operational Expectations

### 7.1 Local Development

```bash
uv venv --python /Users/nitinkhanna/.local/bin/python3.11
uv pip install -e ".[dev]"
scripts/veda-server start
scripts/veda-server status
```

### 7.2 Client Configuration

Any MCP client should be configured with:

```text
transport: streamable_http
url: http://127.0.0.1:8765/mcp
headers:
  Authorization: Bearer <contents of run/veda-token>
```

Remote deployments should use the deployed HTTPS endpoint once available.

For local service mode, `scripts/veda-server start` generates `run/veda-token` when
`VEDA_AUTH_TOKEN` is not already set. Clients running on the same machine should read that token
or use the same environment variable. Browser-style `GET /mcp` is a human status page; MCP
protocol calls should include the bearer header.

The local token is long-lived. It does not expire automatically and remains valid until rotated.
Rotate it by stopping veda, deleting `run/veda-token`, starting veda again, and updating every
local MCP client with the new bearer value. Remote deployments should not inherit this local-token
policy; they need production auth with managed secrets, HTTPS, rotation, and expiry.

### 7.3 Concurrency

veda owns the platform-facing rate limiter. Clients should still avoid creating unbounded parallel
tool calls. Recommended defaults:

- Interactive workflows: one call at a time.
- Small batches: 2-4 concurrent client requests.
- Large batches: use a queue and monitor `health_status`.

### 7.4 Caching

veda has an internal bounded in-memory cache. Clients may add their own cache for workflow-specific
dedupe, but client caches must not change veda's canonical shapes.

### 7.5 Observability

Clients should record:

- tool name
- input resource
- veda route
- returned `scraped_at` when present
- error code when a call fails
- health totals before/after scheduled jobs

---

## 8. Acceptance Criteria For Client Integrations

A client integration is ready when:

- It connects to the Streamable HTTP MCP endpoint.
- It can list veda tools.
- It can call every tool it intends to use with representative inputs.
- It handles `blocked`, `not_found`, and `parse_error` by `.code`.
- It stores or forwards veda result shapes without removing required fields.
- It calls `health_status` in operational paths.
- It does not send caller-specific private state to veda.
- It does not perform its own Reddit scraping as the normal fallback path.

---

## 9. Out Of Scope

This integration PRD does not specify:

- A particular client application.
- How clients should interpret, rank, generate from, or persist returned data.
- Remote hosting, auth, or production secrets.
- Any caller-specific prompt, job, workflow, or business logic.

Those decisions belong in client-specific plans. veda remains only the read service.
