"""Live canary for veda.

Fetches a small set of known-good resources through the real core code paths and
asserts the results are field-complete. Catches silent degradation: broken fetch
tier dependencies, Reddit markup drift, extraction regressions.

Exit code 0 = all probes passed, 1 = at least one failed.
"""
from __future__ import annotations

import os
import subprocess
import sys
import traceback

from veda._transport import tier_capabilities

EXTERNAL_URLS = (
    "https://blog.cloudflare.com/",
    "https://github.com/psf/requests",
)
# All-time top r/announcements thread: archived, stable, never deleted.
REDDIT_THREAD = (
    "https://old.reddit.com/r/announcements/comments/7jsyqt/"
    "the_fccs_vote_was_predictably_frustrating_but/"
)
MIN_EXTERNAL_CHARS = 200


def probe_tiers() -> None:
    caps = tier_capabilities(refresh=True)
    broken = {tier: info["detail"] for tier, info in caps.items() if not info["available"]}
    assert not broken, f"fetch tiers unavailable: {broken}"


def probe_external() -> None:
    from veda.external.fetch import fetch_url

    for url in EXTERNAL_URLS:
        doc = fetch_url(url)
        assert len(doc["text"]) >= MIN_EXTERNAL_CHARS, (
            f"{url}: only {len(doc['text'])} chars via {doc['route']}"
        )
        assert "truncated" in doc and "title" in doc, f"{url}: missing metadata fields"


def probe_subreddit_rules() -> None:
    from veda.reddit import fetch_rules

    rules = fetch_rules("macapps")
    assert rules, "fetch_rules returned empty list for r/macapps"
    assert rules[0].get("short_name"), "rule missing short_name"


def probe_reddit_thread() -> None:
    from veda.reddit import fetch_thread

    result = fetch_thread(REDDIT_THREAD, comment_limit=50)
    post = result["post"]
    assert post["title"], "post title missing"
    assert post["author"], "post author missing"
    comments = result["comments"]
    assert comments, "no comments returned"
    sample = comments[0]
    for field in ("id", "author", "body", "score", "created_utc"):
        assert sample.get(field) is not None, f"comment field {field!r} missing/None"


def main() -> int:
    probes = (probe_tiers, probe_external, probe_subreddit_rules, probe_reddit_thread)
    failures = 0
    for probe in probes:
        name = probe.__name__
        try:
            probe()
        except Exception:
            failures += 1
            print(f"FAIL {name}")
            traceback.print_exc()
        else:
            print(f"ok   {name}")
    if failures:
        print(f"{failures}/{len(probes)} canary probes FAILED")
        _notify_failure(failures, len(probes))
        return 1
    print("all canary probes passed")
    return 0


def _notify_failure(failures: int, total: int) -> None:
    """Desktop alert for scheduled runs (VEDA_CANARY_NOTIFY=1, macOS only)."""
    if not os.environ.get("VEDA_CANARY_NOTIFY") or sys.platform != "darwin":
        return
    message = (
        f"{failures}/{total} canary probes FAILED — "
        "see ~/Library/Logs/veda-canary.log"
    )
    script = f'display notification "{message}" with title "veda-mcp" sound name "Basso"'
    try:
        subprocess.run(["osascript", "-e", script], check=False, timeout=10)
    except Exception:
        pass


if __name__ == "__main__":
    sys.exit(main())
