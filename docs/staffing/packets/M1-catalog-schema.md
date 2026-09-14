# Packet M1 — catalog + schema (channel instances)

Plan: `/home/lee/projects/chief-of-staff/docs/staffing-multi-account-plan.md`
("channel instances — many subscriptions per provider, universally").
Supervised via `/supervise`.

## Packet fields

Kind: impl
Declared size: 6 files, approximately 400 changed lines
Owned paths: `config/staffing/channels.yaml`, `config/staffing/schema/channels.schema.json`, `config/staffing/schema/attempt-record.schema.json`, `src/lee_llm_router/staffing/catalog.py`, `tests/test_staffing_catalog.py`, `tests/test_staffing_attempt_record.py`
Oracle: pytest tests/test_staffing_catalog.py tests/test_staffing_catalog_explain.py tests/test_staffing_attempt_record.py -q
Review: independent review required after the oracle passes

## Objective

Add an optional, additive `instances` list to the staffing channel catalog so a
subscription channel can name more than one account, plus a matching additive
`route.channel_instance` field on the attempt-record schema. A channel that
does not declare `instances` behaves exactly as it does today: it has one
implicit instance whose `instance_id` equals the channel's own `channel_id`.
Nothing about a single-instance channel's existing behavior, schema
requirements, or test expectations may change.

This packet is schema/catalog shape and loader plumbing only. It does not
choose an instance, read live headroom, stage a credential, or dispatch
anything (those are M2/M3/M4/M5, separately packetized and not part of this
packet).

## Owned paths (exact)

- `config/staffing/channels.yaml`
- `config/staffing/schema/channels.schema.json`
- `config/staffing/schema/attempt-record.schema.json`
- `src/lee_llm_router/staffing/catalog.py`
- `tests/test_staffing_catalog.py`
- `tests/test_staffing_attempt_record.py`

## Forbidden

Every other file in the repository, in particular:
- `src/lee_llm_router/availability.py`, `chief-of-staff/scripts/ai-subs.sh`,
  `scripts/refresh_availability.sh` (M2's owned paths — do not touch)
- `src/lee_llm_router/staffing/staff.py`, `src/lee_llm_router/staffing/eligibility.py`
  (M3's owned paths)
- `src/lee_llm_router/staffing/run.py` (M4's owned path)
- `src/lee_llm_router/staffing/evidence_report.py` (M5's owned path)
- Any real credential file under `~/.local/state/lee-llm-router/credentials/`
  — this packet never reads, writes, or references credential contents, only
  the shape of a `credential_ref` string field.
- `context.md`, `sprint-plan.md`, `result-review.md` (the supervisor updates
  these after the packet is verified, not the worker)

## Required changes

1. **`config/staffing/schema/channels.schema.json`** — add an optional
   `instances` array property to the `$defs/channel` object (NOT added to
   `required`, so every existing channel document — including this repo's own
   `channels.yaml` before this change — stays valid with no `instances` key).
   Each item is an object with `additionalProperties: false` and exactly
   three required properties:
   - `instance_id`: nonempty string
   - `credential_ref`: nonempty string (a reference/pointer string, e.g. a
     credential-store path fragment — never a literal secret; this schema
     defines shape only, same convention as `replacement_price_ref`)
   - `enabled`: boolean
   Reuse the existing `$defs/nonemptyString` def. `instances` itself, when
   present, is a non-empty array with `uniqueItems: true` and unique
   `instance_id` values (enforce uniqueness of `instance_id` the same way
   `channel_id` uniqueness is documented elsewhere in this schema family — if
   there is no existing precedent for cross-item uniqueness-by-key inside
   this schema file, it is acceptable to enforce only `uniqueItems: true` on
   the whole array here and note in a schema comment that duplicate
   `instance_id` values are a loader-level check, consistent with this
   schema's stated "shape only" scope).

2. **`config/staffing/channels.yaml`** — two changes:
   - Add the fee fact from the plan: OpenCode Go's `fee_usd_month` gains a
     new dated entry `{effective_from: "2026-09-14", value: 10}` appended
     after the existing `unknown` entry (do not remove the `unknown` entry —
     it is the historical record for dates before 2026-09-14; the loader/
     consumers pick the latest-effective entry, which is existing behavior
     this packet does not change).
   - Do NOT add an `instances:` list to any channel in this committed file
     yet — a live second OpenCode Go account exists (credential already
     placed by Lee at
     `~/.local/state/lee-llm-router/credentials/opencode-go/b.json`,
     outside every repo, never read by this packet), but wiring the real
     `opencode-go` channel to two named instances is authorized by this
     packet's *schema and loader* work, not a live-account wiring decision —
     leave that for M2/M3 where headroom-per-instance and selection actually
     consume it. If you judge that M1 should also declare the two
     `opencode-go` instances (`a` and `b`) in `channels.yaml` now, since the
     schema you're adding explicitly exists to describe exactly this case,
     that is acceptable and even expected — just use `instance_id: a` and
     `instance_id: b`, and `credential_ref` as a pointer string (e.g.
     `opencode-go/a`, `opencode-go/b`) never a literal path into the
     credential store contents, and set `enabled: true` for both. Either
     choice is fine as long as the backward-compatibility tests below pass
     and every existing single-instance channel is left with no `instances`
     key.

3. **`config/staffing/schema/attempt-record.schema.json`** — in the single
   canonical `$defs/route` object (the one with description starting "Route
   identity is exactly the tuple (model, effort, harness, channel)..."), add
   one new optional property `channel_instance`: `anyOf` nonempty string or
   null, same pattern as the existing `provider` property immediately above
   it (optional observed metadata, never invented, null/absent when the
   source records no instance). Do not add it to `required`. Do not touch
   any of the other six `"route":` occurrences in this file (lines ~231,
   1251, 1333, 1560, 1807 in the current file are examples/other $defs, not
   the canonical `$defs/route` at the end of the `$defs` block — only the one
   actually referenced via `"$ref": "#/$defs/route"` needs the change, since
   every other route-shaped object already points at it by reference).

4. **`src/lee_llm_router/staffing/catalog.py`** — add a new frozen dataclass
   `ChannelInstance` with fields `instance_id: str`, `credential_ref: str`,
   `enabled: bool`, export it in `__all__`. Add a field `instances:
   tuple[ChannelInstance, ...] = ()` to the existing `Channel` dataclass
   (default empty tuple — this dataclass is built generically by `_build()`/
   `_convert()` using `dataclasses.fields()` and `get_type_hints()`, so an
   optional tuple-of-dataclass field with a default should convert
   automatically the same way other tuple-of-dataclass fields already do;
   verify this by running the loader against a fixture channel that declares
   `instances` and one that omits it). Add one small pure helper — a method
   or a free function, your choice, but name it clearly, e.g.
   `Channel.effective_instances() -> tuple[ChannelInstance, ...]` — that
   returns `self.instances` when non-empty, or otherwise synthesizes exactly
   one `ChannelInstance(instance_id=self.channel_id, credential_ref=self.channel_id, enabled=True)`
   as the implicit single-instance default the plan describes ("absent = one
   implicit instance named the channel id"). Do not wire this helper into
   any selection, headroom, or dispatch logic — no such logic exists yet in
   this packet's owned files, and none should be added here.

## Tests (required, in the owned test files)

In `tests/test_staffing_catalog.py`:
- A channel document with an explicit `instances` list loads into
  `Channel.instances` with the right typed `ChannelInstance` values, and
  `effective_instances()` returns exactly those instances unchanged.
- A channel document with no `instances` key (the existing fixture shape
  already in this test file) loads with `Channel.instances == ()`, and
  `effective_instances()` returns exactly one synthesized instance whose
  `instance_id` and `credential_ref` equal the channel's `channel_id`, and
  `enabled is True`.
- Schema validation: an `instances` entry missing one of the three required
  keys, or carrying an unknown key, is rejected by
  `channels.schema.json` validation with a clear error (existing
  `StaffingCatalogError` path — follow the file's existing test pattern for
  schema-rejection tests).
- Backward compatibility: `load_staffing_catalog` against the real
  `config/staffing/channels.yaml` in this repo (already exercised by an
  existing test in this file or `tests/test_staffing_catalog_explain.py` —
  reuse the existing fixture-loading pattern) still succeeds after your
  `channels.yaml` edit, and every channel that does not declare `instances`
  still round-trips through `effective_instances()` to its single implicit
  default.

In `tests/test_staffing_attempt_record.py`:
- An attempt-record fixture (reuse or extend an existing fixture under
  `tests/fixtures/staffing/`) with `route.channel_instance` set to a nonempty
  string validates successfully against
  `config/staffing/schema/attempt-record.schema.json`.
- An existing attempt-record fixture with no `channel_instance` key at all
  still validates successfully (the field is additive/optional — this is
  the backward-compatibility proof for the schema change).
- `channel_instance: null` is accepted (matches the `provider` field's
  existing null-allowed convention).

## Before you finish

Run `.venv/bin/black src/lee_llm_router/staffing/catalog.py tests/test_staffing_catalog.py tests/test_staffing_attempt_record.py` (no `--check`, so it actually rewrites the files) as your own last edit, then re-run every command in the Oracle section below yourself and confirm each exits 0, before you report done. A prior dispatch of this exact packet passed pytest (233 passed, 1 skipped) but failed `black --check` on `tests/test_staffing_catalog.py` around the `ChannelInstance`/`expected`-tuple assertions near line 410-460 (long constructor calls and an `assert all(...)` that Black wants collapsed onto fewer lines); running `black` (not `black --check`) on your own changed files before finishing fixes exactly this class of failure.

## Oracle (deterministic, required)

Run, in order, from the repo root with the project's `.venv`:

```bash
PYTHONPATH=src .venv/bin/python -m pytest tests/test_staffing_catalog.py tests/test_staffing_catalog_explain.py tests/test_staffing_attempt_record.py -q
PYTHONPATH=src .venv/bin/python -m pytest -q
.venv/bin/black --check src/lee_llm_router/staffing/catalog.py tests/test_staffing_catalog.py tests/test_staffing_attempt_record.py
.venv/bin/ruff check src/lee_llm_router/staffing/catalog.py tests/test_staffing_catalog.py tests/test_staffing_attempt_record.py
```

All four commands must exit 0. The full-suite `pytest -q` run must show
strictly more passed tests than the pre-packet baseline (currently 1820
passed, 6 skipped per the last recorded full-suite run in
`result-review.md` — confirm the current baseline yourself with `git stash`
or by checking the count before you start, since other uncommitted work may
have changed it) and zero new failures.

## Runtime bound

30 minutes.

## Required evidence

- Full stdout of all four oracle commands, each showing exit 0.
- `git diff --stat` limited to exactly the six owned paths above (no other
  file touched, including no `__pycache__`/`.pyc` — those must not be
  git-added even if present on disk).
- A one-paragraph note confirming whether `channels.yaml` was given the two
  `opencode-go` instances or left with no `instances` key, and why.

## Stop / escalation condition

If `channels.schema.json`'s existing `additionalProperties: false` /
`required` shape for `$defs/channel` cannot be extended additively without
touching an existing required-field list (i.e. if adding `instances` would
force every existing channel document to declare it), stop and report the
exact schema conflict rather than loosening `required` on an unrelated
field. If the generic `_build()`/`_convert()` reflection in `catalog.py`
cannot convert a tuple of the new `ChannelInstance` dataclass without
non-trivial changes to `_convert()`'s control flow, stop and report exactly
what conversion case fails (with the traceback) rather than special-casing
`Channel` construction by hand outside the generic path.
