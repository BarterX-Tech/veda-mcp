# Contributing to veda-mcp

Thanks for your interest in contributing!

## Development setup

```bash
git clone https://github.com/BarterX-Tech/veda-mcp.git
cd veda-mcp
uv venv --python 3.11
uv pip install -e ".[dev]"
.venv/bin/scrapling install   # browser binaries for the stealth/dynamic tiers
```

Run the checks:

```bash
pytest
ruff check .
scripts/veda-canary   # optional: live probes against real sources
```

## Ground rules

- **Test-first.** Every behavior change lands with a failing test written
  before the fix. The suite must stay offline — mock network access; live
  verification belongs in `scripts/canary.py`.
- **Caller-agnostic.** veda never knows who calls it. No caller-specific
  code, naming, or context. The boundary test enforces the allowed
  dependency set.
- **Canonical shapes.** Tool results are stable contracts documented in
  `docs/TECHNICAL_PRD.md` §3. Additive fields are fine; removing or
  renaming fields is a breaking change and needs discussion first.
- **No side effects.** Read paths return data; they never write files.

## Pull requests

- One logical change per PR, with tests.
- Conventional Commits for messages (`feat:`, `fix:`, `docs:`, ...).
- CI (tests + ruff + fetcher-import check) must pass.

## Developer Certificate of Origin

By contributing, you certify the
[Developer Certificate of Origin](https://developercertificate.org/).
Sign off your commits with `git commit -s`.
