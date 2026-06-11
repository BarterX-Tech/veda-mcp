"""Daily health report emailer for veda-mcp.

Runs the live canary probes plus a health snapshot, collects small data
samples from each read path, renders an HTML/text report, and sends it via
Resend. All secrets and addresses come from the environment (loaded from a
gitignored env file); nothing sensitive lives in the repo.

Env (loaded from a gitignored env file; never commit real values):
    RESEND_API_KEY    Resend API key (required to send)
    VEDA_REPORT_FROM  sender address on a Resend-verified domain
    VEDA_REPORT_TO    recipient address
"""
from __future__ import annotations

import html
import os
import sys
from datetime import UTC

import requests

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from veda import health  # noqa: E402
from veda._transport import tier_capabilities  # noqa: E402

PROBES = ("probe_tiers", "probe_external", "probe_subreddit_rules", "probe_reddit_thread")

_SANS = "font-family:IBM Plex Sans,Helvetica,Arial,sans-serif"
_MONO = "font-family:IBM Plex Mono,ui-monospace,SFMono-Regular,Menlo,monospace"
_P = f"margin:0;{_SANS};font-weight:400;font-size:13px;line-height:1.55;color:#6b6862"
_EYEBROW = (
    f"{_MONO};font-weight:600;font-size:10px;line-height:1;"
    "letter-spacing:0.14em;text-transform:uppercase;color:#a8a59d"
)
_ROW_TD = "padding:9px 0;border-bottom:1px solid #f0eeeb;vertical-align:middle"


def _palette(status: str) -> dict[str, str]:
    return {
        "ok": {"base": "#3a9c6d", "bg": "#e7f4ec", "bg2": "#cfe8da", "ink": "#1a6e49"},
        "warn": {"base": "#d79b2b", "bg": "#fbf2e0", "bg2": "#ecdcb8", "ink": "#8a6516"},
        "fail": {"base": "#cc3322", "bg": "#fbeae7", "bg2": "#f2d0c9", "ink": "#a52a1c"},
    }.get(status, {"base": "#3a9c6d", "bg": "#e7f4ec", "bg2": "#cfe8da", "ink": "#1a6e49"})


def _badge(status: str, *, large: bool = False) -> str:
    p = _palette(status)
    size = "12px" if large else "10px"
    pad = "7px 12px" if large else "4px 7px"
    return (
        f"<span style='display:inline-block;background:{p['bg']};color:{p['ink']};{_MONO};"
        f"font-weight:600;font-size:{size};line-height:1;letter-spacing:0.06em;"
        f"padding:{pad};border-radius:9px;border:1px solid {p['bg2']};'>"
        f"{html.escape(status.upper())}</span>"
    )


def _shell(body: str, sender: str, recipient: str) -> str:
    footer = (
        "<tr><td style='padding:18px 28px 24px;background:#faf9f7;border-top:1px solid #efedea;'>"
        f"<table role='presentation' width='100%' cellpadding='0' cellspacing='0'><tr>"
        f"<td style='{_MONO};font-weight:400;font-size:11px;line-height:1.5;color:#a8a59d;'>"
        f"{html.escape(sender)} -&gt; {html.escape(recipient)}<br>"
        "Daily report from the veda-mcp health monitor.</td>"
        f"<td align='right' style='{_MONO};font-weight:400;font-size:11px;line-height:1.5;"
        "color:#a8a59d;vertical-align:bottom;'>deterministic + no caller data</td>"
        "</tr></table></td></tr>"
    )
    return (
        "<!doctype html><html lang='en'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width, initial-scale=1'>"
        "<meta name='color-scheme' content='light only'>"
        "<title>veda-mcp health report</title>"
        "<style>body{margin:0!important;padding:0!important;background:#f4f4f2!important;}"
        "table{border-collapse:separate;}"
        ".break-word{overflow-wrap:anywhere;word-break:break-word;}</style>"
        "</head><body style='margin:0;padding:0;background:#f4f4f2;'>"
        "<table role='presentation' width='100%' cellpadding='0' cellspacing='0' "
        "style='background:#f4f4f2;'><tr><td align='center' style='padding:28px 16px 40px;'>"
        "<table role='presentation' width='100%' cellpadding='0' cellspacing='0' "
        "style='width:100%;max-width:600px;background:#ffffff;border:1px solid #e6e4e0;"
        "border-radius:14px;overflow:hidden;'>"
        f"{body}{footer}"
        "</table></td></tr></table></body></html>"
    )


def _header(status: str) -> str:
    return (
        "<tr><td style='padding:22px 28px 18px;border-bottom:1px solid #efedea;'>"
        "<table role='presentation' width='100%' cellpadding='0' cellspacing='0'><tr>"
        "<td style='vertical-align:middle;'>"
        "<table role='presentation' cellpadding='0' cellspacing='0'><tr>"
        "<td style='vertical-align:middle;padding-right:11px;'>"
        "<div style='width:30px;height:30px;border-radius:8px;background:#1f6feb;"
        "text-align:center;line-height:30px;'>"
        "<span style='display:inline-block;width:12px;height:12px;border-radius:3px;"
        "background:#ffffff;vertical-align:middle;'></span></div></td>"
        "<td style='vertical-align:middle;'>"
        f"<div style='{_SANS};font-weight:600;font-size:14px;"
        "line-height:1.2;color:#2b2926;'>veda-mcp</div>"
        f"<div style='{_EYEBROW};font-size:10px;line-height:1.3;'>health monitor</div>"
        "</td></tr></table></td>"
        f"<td align='right' style='vertical-align:middle;'>{_badge(status, large=True)}</td>"
        "</tr></table></td></tr>"
    )


def _banner(status: str, when: str, fails: int, oks: int) -> str:
    p = _palette(status)
    cells = "".join(
        f"<td style='text-align:center;padding-left:14px;'>"
        f"<div style='{_MONO};font-weight:600;font-size:22px;line-height:1;"
        f"color:{_palette(s)['ink']};'>{v}</div>"
        f"<div style='{_EYEBROW};font-size:9px;padding-top:4px;'>{label}</div></td>"
        for v, label, s in ((fails, "fail", "fail"), (oks, "ok", "ok"))
    )
    return (
        "<tr><td style='padding:0 28px;'>"
        f"<table role='presentation' width='100%' cellpadding='0' cellspacing='0' "
        f"style='margin:20px 0 4px;background:{p['bg']};border:1px solid {p['bg2']};"
        f"border-left:5px solid {p['base']};border-radius:11px;'><tr>"
        f"<td style='padding:16px 18px;vertical-align:middle;'>"
        f"<div style='{_EYEBROW};color:{p['ink']};padding-bottom:6px;'>System status</div>"
        f"<div style='{_MONO};font-weight:600;font-size:26px;line-height:1;color:{p['ink']};'>"
        f"{html.escape(status.upper())}</div>"
        f"<div style='{_P};padding-top:6px;'>{html.escape(when)}</div></td>"
        f"<td align='right' style='padding:16px 18px;vertical-align:middle;'>"
        f"<table role='presentation' cellpadding='0' cellspacing='0'><tr>{cells}</tr></table>"
        "</td></tr></table></td></tr>"
    )


def _section(title: str) -> str:
    return (
        "<tr><td style='padding:20px 28px 2px;'>"
        f"<div style='{_EYEBROW};'>{html.escape(title)}</div></td></tr>"
    )


def _probe_rows(rows: list[dict]) -> str:
    body = "".join(
        "<tr>"
        f"<td width='64' style='{_ROW_TD}'>{_badge('ok' if r['ok'] else 'fail')}</td>"
        f"<td class='break-word' style='{_ROW_TD}'>"
        f"<span style='{_SANS};font-weight:600;font-size:13px;color:#2b2926;'>"
        f"{html.escape(r['name'])}</span>"
        f"<div style='{_P};font-size:11.5px;padding-top:4px;'>{html.escape(r['detail'])}</div>"
        "</td></tr>"
        for r in rows
    )
    return (
        "<tr><td style='padding:0 28px 4px;'>"
        f"<table role='presentation' width='100%' cellpadding='0' cellspacing='0'>{body}</table>"
        "</td></tr>"
    )


def _sample_rows(samples: list[dict]) -> str:
    body = ""
    for s in samples:
        fields = "".join(
            f"<div style='{_P};font-size:11.5px;'><b style='color:#2b2926'>"
            f"{html.escape(k)}</b>: {html.escape(str(v))}</div>"
            for k, v in s["fields"].items()
        )
        body += (
            "<tr>"
            f"<td class='break-word' style='{_ROW_TD}'>"
            f"<span style='{_MONO};font-weight:600;font-size:12px;color:#2b2926;'>"
            f"{html.escape(s['tool'])}</span>"
            f"<div style='padding-top:5px'>{fields}</div>"
            f"<div style='{_MONO};font-size:10.5px;color:#8a877f;padding-top:6px;'>"
            f"{html.escape(s['shape'])}</div>"
            "</td></tr>"
        )
    return (
        "<tr><td style='padding:0 28px 4px;'>"
        f"<table role='presentation' width='100%' cellpadding='0' cellspacing='0'>{body}</table>"
        "</td></tr>"
    )


def _describe(value, depth: int = 0) -> str:
    """Compact JSON-structure sketch: keys with nested hints, no data values."""
    if isinstance(value, dict):
        if depth >= 2:
            return "{…}"
        inner = ", ".join(
            f"{k}{_suffix(v, depth)}" for k, v in list(value.items())[:12]
        )
        more = ", …" if len(value) > 12 else ""
        return "{" + inner + more + "}"
    if isinstance(value, list):
        if not value:
            return "[]"
        return f"[{len(value)}]" + _describe(value[0], depth + 1)
    return ""


def _suffix(v, depth: int) -> str:
    if isinstance(v, dict | list):
        return _describe(v, depth + 1)
    return ""


def _collect_samples() -> list[dict]:
    """Small live reads per tool; transport cache makes probe-adjacent reads cheap."""
    import canary

    samples: list[dict] = []

    from veda.reddit import fetch_rules, fetch_thread

    try:
        thread = fetch_thread(canary.REDDIT_THREAD, comment_limit=20)
        samples.append({
            "tool": "fetch_thread",
            "fields": {
                "title": thread["post"]["title"][:70],
                "score": thread["post"]["score"],
                "comments returned": len(thread["comments"]),
                "route": thread["meta"]["route"],
            },
            "shape": _describe(thread),
        })
    except Exception as exc:  # noqa: BLE001
        samples.append({"tool": "fetch_thread", "fields": {"error": str(exc)[:120]}, "shape": ""})

    try:
        rules = fetch_rules("macapps")
        samples.append({
            "tool": "fetch_rules",
            "fields": {
                "rules": len(rules),
                "first": rules[0]["short_name"] if rules else "—",
            },
            "shape": _describe(rules),
        })
    except Exception as exc:  # noqa: BLE001
        samples.append({"tool": "fetch_rules", "fields": {"error": str(exc)[:120]}, "shape": ""})

    from veda.external.fetch import fetch_url

    try:
        doc = fetch_url(canary.EXTERNAL_URLS[0], max_chars=4000)
        samples.append({
            "tool": "fetch_url",
            "fields": {
                "url": doc["url"],
                "route": doc["route"],
                "title": doc["title"] or "—",
                "chars": len(doc["text"]),
                "truncated": doc["truncated"],
            },
            "shape": _describe(doc),
        })
    except Exception as exc:  # noqa: BLE001
        samples.append({"tool": "fetch_url", "fields": {"error": str(exc)[:120]}, "shape": ""})

    return samples


def _run_probes() -> list[dict]:
    import canary

    rows = []
    for name in PROBES:
        fn = getattr(canary, name)
        try:
            fn()
            rows.append({"name": name, "ok": True, "detail": "passed"})
        except Exception as exc:  # noqa: BLE001
            rows.append({"name": name, "ok": False, "detail": f"{type(exc).__name__}: {exc}"})
    return rows


def _tiers_row(tiers: dict, totals: dict) -> str:
    tiers_text = "  ·  ".join(
        f"{k}: {'up' if v['available'] else 'DOWN'}" for k, v in tiers.items()
    )
    return (
        "<tr><td style='padding:14px 28px 8px;'>"
        f"<div style='{_MONO};font-size:11px;color:#6b6862;'>{html.escape(tiers_text)}</div>"
        f"<div style='{_MONO};font-size:11px;color:#a8a59d;padding-top:4px;'>"
        f"process totals: {totals.get('calls', 0)} calls, {totals.get('errors', 0)} errors</div>"
        "</td></tr>"
    )


def render(rows: list[dict], samples: list[dict], tiers: dict, totals: dict, ts: str):
    fails = sum(1 for r in rows if not r["ok"])
    status = "ok" if fails == 0 else "fail"
    body = (
        _header(status)
        + _banner(status, ts, fails, len(rows) - fails)
        + _section("Probes")
        + _probe_rows(rows)
        + _section("Data samples")
        + _sample_rows(samples)
        + _tiers_row(tiers, totals)
    )

    text_lines = [f"veda-mcp health report — {ts}", f"Status: {status.upper()}", "", "Probes:"]
    for r in rows:
        text_lines.append(f"  [{'ok' if r['ok'] else 'FAIL'}] {r['name']} — {r['detail']}")
    text_lines.append("")
    text_lines.append("Data samples:")
    for s in samples:
        pairs = "; ".join(f"{k}={v}" for k, v in s["fields"].items())
        text_lines.append(f"  {s['tool']}: {pairs}")
        if s["shape"]:
            text_lines.append(f"    shape: {s['shape']}")
    text_lines.append("")
    text_lines.append("Tiers: " + ", ".join(
        f"{k}={'up' if v['available'] else 'DOWN'}" for k, v in tiers.items()
    ))
    return body, "\n".join(text_lines), fails == 0


def _load_env_file() -> None:
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


def _send(subject: str, html_body: str, text: str) -> None:
    key = os.environ.get("RESEND_API_KEY")
    sender = os.environ.get("VEDA_REPORT_FROM")
    recipient = os.environ.get("VEDA_REPORT_TO")
    if not (key and sender and recipient):
        raise SystemExit("RESEND_API_KEY, VEDA_REPORT_FROM, VEDA_REPORT_TO must be set")
    resp = requests.post(
        "https://api.resend.com/emails",
        json={
            "from": sender,
            "to": recipient,
            "subject": subject,
            "html": _shell(html_body, sender, recipient),
            "text": text,
        },
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
    samples = _collect_samples()
    tiers = tier_capabilities(refresh=True)
    totals = health.snapshot().get("totals", {})
    html_body, text, healthy = render(rows, samples, tiers, totals, ts)
    subject = f"veda-mcp health: {'OK' if healthy else 'FAILING'} — {ts}"
    _send(subject, html_body, text)
    print(f"sent report: {subject}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
