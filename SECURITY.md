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
- `fetch_url` blocks requests to localhost, private, link-local, and
  otherwise non-global addresses. Cloud-metadata endpoints
  (`169.254.169.254`, `fd00:ec2::254`, `100.100.100.200`) are also denied
  by name as defense-in-depth.
- The plain-request (tier1) route follows redirects manually and re-runs
  the address check on every hop, so a public URL cannot bounce into
  private or metadata space.

### Known residual: DNS rebinding

The address check resolves the hostname and validates the returned IPs,
then the HTTP client resolves again to connect. A hostname that returns a
public IP at check time and a private IP at connect time (DNS rebinding)
could in principle bypass the tier1 guard. The window is small and the
service is loopback-only by default; if you expose veda to untrusted
callers, run it in a network-restricted environment.
- Browser-based fetch tiers (stealth/dynamic) follow redirects inside the
  browser; if you expose veda to untrusted callers, treat the browser
  tiers as able to reach any address the host machine can reach, and run
  the service in a sandboxed or network-restricted environment.

## Out of Scope

- Abuse of the service by an authorized caller (rate limits are
  protective defaults, not a security boundary).
- Issues requiring a malicious local user on the same machine.
