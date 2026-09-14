# Packet M3-2-review — independent review of the uncommitted selected-instance diff

Kind: review
Declared size: 2 files, approximately 300 changed/added lines
Owned paths: src/lee_llm_router/staffing/block.py, tests/test_staffing_block.py
Oracle: none (judge review; verdict is the deliverable)
Review: n/a (this is the review)

The owned paths above are registered for conflict-freedom only — this is a
read-only review; write nothing.

Runtime bound: 20 minutes.

- Scope: the **uncommitted** diff in `/home/lee/projects/lee-llm-router` limited to
  `src/lee_llm_router/staffing/block.py` and `tests/test_staffing_block.py` (`git diff -- <those
  two>`). Ignore every other file, including untracked files elsewhere in the repo.
- Packet under review: `docs/staffing/packets/M3-2-staff-selected-instance.md`; plan:
  `/home/lee/projects/chief-of-staff/docs/staffing-multi-account-plan.md` (milestone M3, per the
  M3 design ruling and M3 ruling 2, 2026-09-14). M1/M2/M3-1 are already committed and must not
  appear changed in this diff.

## Judge (ACCEPT/REJECT, with what you reproduced)

1. `WorkerFacts` gained an additive `instance_headrooms: tuple[dict[str, Any], ...] = ()` field
   and `as_dict()` entry. Confirm it is populated from the eligibility row's own
   `instance_headrooms` (via the module's existing `_field()` helper, so both a real
   `EligibilityRow`/`EligibilityInstance` object and a plain-dict/mapping test double work),
   verbatim in the same order supplied (already most-headroom-first from M3-1 — this packet must
   not re-sort), and is an empty tuple when the row carries none (must not raise).
2. `StaffingBlock` gained an additive `selected_instance: str | None` field. Confirm
   `build_auto_block()` resolves it, once the route selection (`selection`) is already decided,
   to the `instance_id` of the *first* entry in the selected route's `instance_headrooms` whose
   `eligible` is `True` — reproduce against a case where the eligible instance is **not** first
   in supply order (the picker must not just take index 0). Confirm it is `None` when
   `selection` is `None`, when the selected route's `instance_headrooms` is empty, or when every
   supplied instance for the selected route is ineligible — none of these cases may raise.
3. `"selected_instance"` was added to both `StaffingBlock.as_dict()`'s returned mapping and the
   `STAFFING_BLOCK_JSON_KEYS` tuple, in the same position immediately after `"selected_route"` —
   confirm both changed together (a mismatch would silently drop the key from `render_json()`,
   since `render_json` filters strictly through `STAFFING_BLOCK_JSON_KEYS`) and that the ordering
   assertion in the test file's `test_json_carries_exactly_the_text_facts` still checks exact key
   order, not just membership.
4. `render_text()` gained exactly one deterministic text fragment naming the selected instance,
   present only when `selected_instance` is not `None`, absent otherwise (no placeholder text
   like "instance: unknown" for the `None` case). Reproduce both branches yourself.
5. Confirm `_select_auto_route` and every other route-selection arithmetic in `staff.py` is
   untouched — `git status --short` must show no changes to `staff.py`, and this diff is confined
   to `block.py`/`test_staffing_block.py` only (check for stray edits to any other file, including
   untracked files, per the doctrine's scope-check rule).
6. Confirm the independent reviewer's own instance choice was **not** touched or invented by this
   diff (out of scope per the M3-2 packet) — `_select_review_route` in `staff.py` is untouched.

## Evidence you must reproduce yourself

```bash
cd /home/lee/projects/lee-llm-router
git status --short
git diff --stat -- src/lee_llm_router/staffing/block.py tests/test_staffing_block.py
PYTHONPATH=src .venv/bin/python -m pytest tests/test_staffing_block.py -q
.venv/bin/black --check src/lee_llm_router/staffing/block.py tests/test_staffing_block.py
.venv/bin/ruff check src/lee_llm_router/staffing/block.py tests/test_staffing_block.py
```

Report exact pass/fail counts. End with the literal line `REVIEW VERDICT: ACCEPT` or
`REVIEW VERDICT: REJECT`, and if REJECT, name the exact defect and which owned file/line it is
in.
