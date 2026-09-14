# Packet M3-1-fix1 — restore full-suite green: per-instance OpenCode/Go fixture in test_staffing_staff.py

Kind: impl
Declared size: 1 file, approximately 20 changed/added lines
Owned paths: tests/test_staffing_staff.py
Oracle: `pytest tests/test_staffing_staff.py -q && pytest -q`
Review: independent review required after the oracle passes

Plan: `/home/lee/projects/chief-of-staff/docs/staffing-multi-account-plan.md`, milestone M3.
Independent review of M3-1 (`docs/staffing/packets/M3-1-eligibility-instances.md`, escalated to
`codex-gpt-5-6-sol-high-openai-sub` after the first reviewer's harness lacked bash tools) found
one contract-blocking regression, reproduced independently by the supervisor:
`pytest -q` goes from all-green to `1 failed, 1874 passed, 6 skipped` —
`tests/test_staffing_staff.py::test_auto_explicit_author_review_never_picks_the_selected_worker`
now selects `codex-gpt-5-6-luna-xhigh-openai-sub` instead of the expected
`opencode-opencode-go-deepseek-v4-flash-opencode-go`.

## Root cause (confirmed, not hypothesized)

`config/staffing/channels.yaml`'s `opencode-go` channel declares two real instances (M1,
already committed): `instance_id: a` and `instance_id: b`. `tests/test_staffing_staff.py`'s
`catalog` fixture loads that real production `config/staffing/channels.yaml` directly
(`load_staffing_catalog(REPO_CONFIG_DIR)`), but its own hand-built availability fixtures
(`_snapshot()` at line ~42 and `_snapshot_reserved()` at line ~640) each supply exactly one
untagged `"OpenCode/Go"` subscriptions entry — which `parse_availability` files under the
*implicit* instance id `"opencode-go"` (M2 convention: `bucket.instance` if set, else the
channel id). M3-1's per-instance eligibility check (already committed as this packet's
sibling) now reads `availability.instance_headroom("opencode-go", "a")` and
`("opencode-go", "b")` for the declared instances — neither key exists in these fixtures'
snapshots, so both instances read back `unknown` health and the route is vetoed by health,
where before M3-1 the channel-wide aggregate (which *did* have data) was used instead.

## Objective

Update the two OpenCode/Go subscription entries in `tests/test_staffing_staff.py`'s
`_snapshot()` and `_snapshot_reserved()` helpers so each yields **two** tagged entries —
`"instance": "a"` and `"instance": "b"` — instead of one untagged entry, each carrying the
same `status`/`remaining_pct` the untagged entry carried before (so every existing assertion
about OpenCode/Go headroom continues to hold: `_snapshot()`'s 80%-on-track case gives both
instances headroom above reserve, `_snapshot_reserved()`'s 8%-reserved case gives both
instances at/under the 0.10 D216 reserve). Do not change the `bucket` or `provider` fields;
only add the `"instance"` key and duplicate the entry. Do not touch any other provider's
entries in either helper.

## Owned paths

- `tests/test_staffing_staff.py`

## Forbidden paths

Every other file, including `src/lee_llm_router/staffing/eligibility.py`,
`src/lee_llm_router/availability.py`, `config/staffing/channels.yaml`, and every other test
file. If keeping the full suite green appears to require touching any of those, stop and
report — do not improvise a production-code change to route around a test fixture.

## Expected artifact

`tests/test_staffing_staff.py` diff: `_snapshot()` and `_snapshot_reserved()` each gain a
second `"OpenCode/Go"` entry with `"instance": "b"` (the existing entry gains `"instance": "a"`
in place), same `status`/`remaining_pct` values as today.

## Required evidence

```bash
cd /home/lee/projects/lee-llm-router
PYTHONPATH=src .venv/bin/python -m pytest tests/test_staffing_staff.py -q
PYTHONPATH=src .venv/bin/python -m pytest -q
.venv/bin/black --check tests/test_staffing_staff.py
.venv/bin/ruff check tests/test_staffing_staff.py
```

All four must exit 0, and the full-suite line must read `1874 passed` plus the one now-fixed
test (no `failed` count) — paste the full pytest summary line for both runs in your report.

## Stop/escalation condition

Stop and report if adding the two tagged entries does not restore the full suite to green —
that would mean the root-cause diagnosis above is wrong, and the fix needs re-diagnosis, not a
second guess at the same file. Runtime bound: 20 minutes. Oracle above is deterministic.
