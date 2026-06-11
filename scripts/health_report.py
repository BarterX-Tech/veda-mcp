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

PROBES = (
    "probe_tiers",
    "probe_external",
    "probe_subreddit_rules",
    "probe_reddit_thread",
    "probe_reddit_user",
)
PROBE_LABELS = {
    "probe_tiers": "Fetch tiers",
    "probe_external": "External URLs",
    "probe_subreddit_rules": "Subreddit rules",
    "probe_reddit_thread": "Reddit thread",
    "probe_reddit_user": "Reddit user profile",
}

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
    headline = "All systems healthy" if fails == 0 else f"{fails} check(s) failing"
    cells = "".join(
        f"<td style='text-align:center;padding-left:16px;'>"
        f"<div style='{_MONO};font-weight:600;font-size:22px;line-height:1;"
        f"color:{_palette(s)['ink']};'>{v}</div>"
        f"<div style='{_SANS};font-size:11px;padding-top:4px;color:#8a877f;'>{label}</div></td>"
        for v, label, s in ((fails, "Failing", "fail"), (oks, "Passing", "ok"))
    )
    return (
        "<tr><td style='padding:0 28px;'>"
        f"<table role='presentation' width='100%' cellpadding='0' cellspacing='0' "
        f"style='margin:20px 0 4px;background:{p['bg']};border:1px solid {p['bg2']};"
        f"border-left:5px solid {p['base']};border-radius:11px;'><tr>"
        f"<td style='padding:16px 18px;vertical-align:middle;'>"
        f"<div style='{_SANS};font-weight:600;font-size:11px;color:{p['ink']};"
        f"padding-bottom:6px;'>System status</div>"
        f"<div style='{_SANS};font-weight:700;font-size:21px;line-height:1.2;color:{p['ink']};'>"
        f"{html.escape(headline)}</div>"
        f"<div style='{_P};padding-top:6px;'>{html.escape(when)}</div></td>"
        f"<td align='right' style='padding:16px 18px;vertical-align:middle;'>"
        f"<table role='presentation' cellpadding='0' cellspacing='0'><tr>{cells}</tr></table>"
        "</td></tr></table></td></tr>"
    )


def _section(title: str) -> str:
    return (
        "<tr><td style='padding:22px 28px 4px;'>"
        f"<div style='{_SANS};font-weight:600;font-size:15px;color:#2b2926;'>"
        f"{html.escape(title)}</div></td></tr>"
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


def _label(key: str) -> str:
    """Human field label: capitalize, keep acronyms upper (URL, JSON)."""
    text = key[:1].upper() + key[1:]
    for acro in ("Url", "Json", "Utc", "Id", "Op"):
        text = text.replace(acro, acro.upper())
    return text


def _sample_rows(samples: list[dict]) -> str:
    body = ""
    for s in samples:
        fields = "".join(
            f"<tr><td style='{_P};font-size:12px;padding:1px 14px 1px 0;white-space:nowrap;'>"
            f"<b style='color:#2b2926;font-weight:600'>{html.escape(_label(k))}</b></td>"
            f"<td class='break-word' style='{_P};font-size:12px;padding:1px 0;'>"
            f"{html.escape(str(v))}</td></tr>"
            for k, v in s["fields"].items()
        )
        shape = (
            f"<pre style='margin:8px 0 0;padding:11px 13px;background:#f7f6f4;"
            f"border:1px solid #ececea;border-radius:8px;{_MONO};font-size:11px;"
            f"line-height:1.5;color:#4a4842;white-space:pre;overflow-x:auto;'>"
            f"{html.escape(s['shape'])}</pre>"
            if s["shape"]
            else ""
        )
        body += (
            "<tr>"
            f"<td class='break-word' style='{_ROW_TD};padding-top:14px;'>"
            f"<span style='{_MONO};font-weight:600;font-size:13px;color:#1f6feb;'>"
            f"{html.escape(s['tool'])}</span>"
            f"<table role='presentation' cellpadding='0' cellspacing='0' "
            f"style='margin-top:7px;'>{fields}</table>"
            f"{shape}"
            "</td></tr>"
        )
    return (
        "<tr><td style='padding:0 28px 4px;'>"
        f"<table role='presentation' width='100%' cellpadding='0' cellspacing='0'>{body}</table>"
        "</td></tr>"
    )


def _describe(value, indent: int = 0) -> str:
    """Pretty multi-line JSON-shape sketch: keys and nesting, no data values."""
    pad = "  " * indent
    if isinstance(value, dict):
        if not value:
            return "{}"
        if indent >= 2:
            keys = ", ".join(list(value)[:8])
            return "{ " + keys + (", …" if len(value) > 8 else "") + " }"
        lines = ["{"]
        for k, v in list(value.items())[:14]:
            lines.append(f"{pad}  {k}: {_describe(v, indent + 1)},")
        if len(value) > 14:
            lines.append(f"{pad}  …")
        lines.append(pad + "}")
        return "\n".join(lines)
    if isinstance(value, list):
        if not value:
            return "[]"
        return f"[ {len(value)} × {_describe(value[0], indent)} ]"
    return type(value).__name__


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

    from veda.reddit import fetch_user

    try:
        user = fetch_user(canary.REDDIT_USER, pages=1)
        samples.append({
            "tool": f"fetch_user ({canary.REDDIT_USER})",
            "fields": {
                "post karma": user["post_karma"],
                "comment karma": user["comment_karma"],
                "bio": (user["bio"][:50] + "…") if user["bio"] else "—",
                "posts / comments": f"{len(user['posts'])} / {len(user['comments'])}",
            },
            "shape": _describe(user),
        })
    except Exception as exc:  # noqa: BLE001
        samples.append({"tool": "fetch_user", "fields": {"error": str(exc)[:120]}, "shape": ""})

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
        label = PROBE_LABELS.get(name, name)
        try:
            fn()
            rows.append({"name": label, "ok": True, "detail": "Passed"})
        except Exception as exc:  # noqa: BLE001
            rows.append({"name": label, "ok": False, "detail": f"{type(exc).__name__}: {exc}"})
    return rows


def _tiers_row(tiers: dict, totals: dict) -> str:
    tiers_text = "   ·   ".join(
        f"{k}: {'Up' if v['available'] else 'Down'}" for k, v in tiers.items()
    )
    return (
        "<tr><td style='padding:16px 28px 8px;'>"
        f"<div style='{_SANS};font-size:12px;color:#6b6862;'>"
        f"<b style='color:#2b2926;font-weight:600'>Fetch tiers</b> &nbsp; "
        f"{html.escape(tiers_text)}</div>"
        f"<div style='{_SANS};font-size:12px;color:#a8a59d;padding-top:4px;'>"
        f"Process totals: {totals.get('calls', 0)} calls, "
        f"{totals.get('errors', 0)} errors</div>"
        "</td></tr>"
    )


def render(rows: list[dict], samples: list[dict], tiers: dict, totals: dict, ts: str):
    fails = sum(1 for r in rows if not r["ok"])
    status = "ok" if fails == 0 else "fail"
    body = (
        _header(status)
        + _banner(status, ts, fails, len(rows) - fails)
        + _section("Probe results")
        + _probe_rows(rows)
        + _section("Data samples")
        + _sample_rows(samples)
        + _tiers_row(tiers, totals)
    )

    headline = "All systems healthy" if fails == 0 else f"{fails} check(s) failing"
    text_lines = [
        "veda-mcp health report",
        ts,
        f"Status: {headline}",
        "",
        "Probe results:",
    ]
    for r in rows:
        mark = "PASS" if r["ok"] else "FAIL"
        text_lines.append(f"  [{mark}] {r['name']} — {r['detail']}")
    text_lines += ["", "Data samples:"]
    for s in samples:
        text_lines.append(f"  {s['tool']}")
        for k, v in s["fields"].items():
            text_lines.append(f"    {_label(k)}: {v}")
        if s["shape"]:
            text_lines.append("    Structure:")
            text_lines += [f"      {ln}" for ln in s["shape"].splitlines()]
        text_lines.append("")
    text_lines.append("Fetch tiers: " + ", ".join(
        f"{k}={'Up' if v['available'] else 'Down'}" for k, v in tiers.items()
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
    now = datetime.now(UTC).astimezone()  # machine-local time
    # e.g. "Thursday, June 12, 2026 at 10:00 AM IST"
    ts = now.strftime("%A, %B %-d, %Y at %-I:%M %p %Z")
    subject_date = now.strftime("%B %-d, %Y")
    rows = _run_probes()
    samples = _collect_samples()
    tiers = tier_capabilities(refresh=True)
    totals = health.snapshot().get("totals", {})
    html_body, text, healthy = render(rows, samples, tiers, totals, ts)
    state = "All systems OK" if healthy else "Issues detected"
    subject = f"veda-mcp health — {state} — {subject_date}"
    _send(subject, html_body, text)
    print(f"sent report: {subject}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
