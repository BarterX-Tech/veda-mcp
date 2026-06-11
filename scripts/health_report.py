"""Daily health report emailer for veda-mcp.

Runs the live canary probes plus a health snapshot, renders a small HTML/text
report, and sends it via Resend. All secrets and addresses come from the
environment (loaded from a gitignored env file by the launchd job) — nothing
sensitive lives in the repo.

Env (loaded from a gitignored env file; never commit real values):
    RESEND_API_KEY    Resend API key (required to send)
    VEDA_REPORT_FROM  sender address on a Resend-verified domain
    VEDA_REPORT_TO    recipient address
"""
from __future__ import annotations

import html as html_lib
import os
import sys

import requests

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from datetime import UTC

from veda import health  # noqa: E402
from veda._transport import tier_capabilities  # noqa: E402

PROBES = ("probe_tiers", "probe_external", "probe_subreddit_rules", "probe_reddit_thread")


def _run_probes() -> list[dict]:
    import canary  # scripts/ is on sys.path when run as a script

    rows = []
    for name in PROBES:
        fn = getattr(canary, name)
        try:
            fn()
            rows.append({"name": name, "ok": True, "detail": ""})
        except Exception as exc:  # noqa: BLE001 - report any failure
            rows.append({"name": name, "ok": False, "detail": f"{type(exc).__name__}: {exc}"})
    return rows


def _render(rows: list[dict], tiers: dict, totals: dict, ts: str) -> tuple[str, str, bool]:
    failures = [r for r in rows if not r["ok"]]
    healthy = not failures
    status = "OK" if healthy else f"{len(failures)} FAILING"
    color = "#1a7f37" if healthy else "#cf222e"

    text_lines = [f"veda-mcp health report — {ts}", f"Status: {status}", ""]
    for r in rows:
        text_lines.append(f"  [{'ok' if r['ok'] else 'FAIL'}] {r['name']}"
                          + (f" — {r['detail']}" if r["detail"] else ""))
    text_lines += ["", "Fetch tiers: " + ", ".join(
        f"{k}={'up' if v['available'] else 'DOWN'}" for k, v in tiers.items()
    )]
    text = "\n".join(text_lines)

    rows_html = "".join(
        f"<tr><td style='padding:4px 10px'>{'✅' if r['ok'] else '❌'}</td>"
        f"<td style='padding:4px 10px;font-family:monospace'>{html_lib.escape(r['name'])}</td>"
        f"<td style='padding:4px 10px;color:#57606a'>{html_lib.escape(r['detail'])}</td></tr>"
        for r in rows
    )
    tiers_html = ", ".join(
        f"{html_lib.escape(k)}: {'up' if v['available'] else '<b style=color:#cf222e>DOWN</b>'}"
        for k, v in tiers.items()
    )
    html = (
        f"<div style='font-family:-apple-system,Segoe UI,sans-serif;max-width:560px'>"
        f"<h2 style='margin:0 0 4px'>veda-mcp health</h2>"
        f"<p style='margin:0 0 12px;color:#57606a'>{html_lib.escape(ts)}</p>"
        f"<p style='font-size:18px;font-weight:600;color:{color};margin:0 0 14px'>{status}</p>"
        f"<table style='border-collapse:collapse;font-size:14px'>{rows_html}</table>"
        f"<p style='font-size:13px;color:#57606a;margin-top:14px'>Fetch tiers: {tiers_html}</p>"
        f"<p style='font-size:13px;color:#57606a'>Lifetime totals: "
        f"{totals.get('calls', 0)} calls, {totals.get('errors', 0)} errors</p>"
        f"</div>"
    )
    return html, text, healthy


def _load_env_file() -> None:
    """Load run/veda-mail.env (gitignored) when vars are not already set."""
    path = os.path.join(os.path.dirname(__file__), "..", "run", "veda-mail.env")
    if not os.path.exists(path):
        return
    with open(path) as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())


def _send(subject: str, html: str, text: str) -> None:
    key = os.environ.get("RESEND_API_KEY")
    sender = os.environ.get("VEDA_REPORT_FROM")
    recipient = os.environ.get("VEDA_REPORT_TO")
    if not (key and sender and recipient):
        raise SystemExit("RESEND_API_KEY, VEDA_REPORT_FROM, VEDA_REPORT_TO must be set")
    resp = requests.post(
        "https://api.resend.com/emails",
        json={"from": sender, "to": recipient, "subject": subject, "html": html, "text": text},
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "User-Agent": "veda-mcp-health/1.0",
        },
        timeout=30,
    )
    if resp.status_code < 200 or resp.status_code >= 300:
        raise SystemExit(f"Resend HTTP {resp.status_code}: {resp.text}")


def main() -> int:
    from datetime import datetime

    _load_env_file()
    ts = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
    rows = _run_probes()
    tiers = tier_capabilities(refresh=True)
    totals = health.snapshot().get("totals", {})
    html, text, healthy = _render(rows, tiers, totals, ts)
    subject = f"veda-mcp health: {'OK' if healthy else 'FAILING'} — {ts}"
    _send(subject, html, text)
    print(f"sent report: {subject}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
