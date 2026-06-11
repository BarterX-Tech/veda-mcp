# Security Policy

## Reporting a Vulnerability

Please report security issues privately via
[GitHub Security Advisories](../../security/advisories/new) for this
repository. Do not open public issues for vulnerabilities.

You can expect an initial response within 7 days.

## Scope and Threat Model

veda is designed to run as a **loopback-only service** (`127.0.0.1`) with
bearer-token authentication:

- The server refuses to start on a non-loopback address without
  `VEDA_AUTH_TOKEN` / `VEDA_TOKEN_FILE` set.
- `fetch_url` blocks requests to localhost, private, link-local
  (including cloud metadata), and otherwise non-global addresses, and
  re-validates every redirect hop on the plain-request route.
- Browser-based fetch tiers (stealth/dynamic) follow redirects inside the
  browser; if you expose veda to untrusted callers, treat the browser
  tiers as able to reach any address the host machine can reach, and run
  the service in a sandboxed or network-restricted environment.

## Out of Scope

- Abuse of the service by an authorized caller (rate limits are
  protective defaults, not a security boundary).
- Issues requiring a malicious local user on the same machine.
