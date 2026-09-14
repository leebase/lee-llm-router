# Packet S7 — classify `.go` files; register the Sol xHigh route so a Codex supervisor can attest

- Kind: `impl`; Class: `impl/deterministic/data-schema/s/python`; Declared size: 5 files, ≤ 160 lines
- Owned paths: `config/staffing/classes.yaml`, `src/lee_llm_router/staffing/derive_class.py`,
  `config/staffing/routes.yaml`, `tests/test_staffing_derive_class.py`, `tests/test_staffing_catalog.py`
- Forbidden: everything else (`terms.yaml`, `channels.yaml`, `policy.yaml`, `staff.py`, `ladder.py`).
- Runtime bound: 20 minutes. Oracle: `python3 -m pytest -q tests/test_staffing_derive_class.py tests/test_staffing_catalog.py tests/test_staffing_catalog_explain.py`
- Authority: Lee 2026-09-14 forwarding the Codex door's `/supervise` failure: "The router
  taxonomy cannot classify .go files" and "The catalog has Sol High but not Sol xHigh; falsely
  attesting Sol High would corrupt the evidence ledger." Ordinary owner repair (D86/D87).

## Changes
1. `classes.yaml` language value set gains `go` (keep the list otherwise identical; add a
   one-line comment citing this packet). `derive_class.py` `_EXTENSION_LANGUAGES` maps `.go`
   → `go`; mixed-language derivation is unchanged. Tests: a packet owning `x.go` derives
   `language: go`; `.go` + `.py` derives `mixed`.
2. `routes.yaml`: add `codex-gpt-5-6-sol-xhigh-openai-sub` cloned from
   `codex-gpt-5-6-sol-high-openai-sub` with `effort: xhigh` and the dispatch template's
   `CODEX_STAGE_WORKER_REASONING_EFFORT=xhigh`; `status: active`; same channel, model, harness,
   usage_capture; place it next to the other Sol rows. Pricing needs no change (same model
   row). Tests: the catalog loads it; `catalog explain` lists it as eligible for an impl
   class with the same eligibility as Sol high; `route show codex-gpt-5-6-sol-xhigh-openai-sub`
   prints it.

## Required evidence
Oracle before/after; black/ruff on the two Python files; `lee-llm-router route show
codex-gpt-5-6-sol-xhigh-openai-sub`; `lee-llm-router staff --mode auto --role impl --class
impl/deterministic/none/s/go --json` succeeding (exit 0). Do not commit, stash, or write
`decisions.md`.
