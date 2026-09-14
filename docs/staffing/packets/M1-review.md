# Packet M1-review — independent review of the uncommitted M1 diff (channel instances: catalog + schema)

- Kind: `review`; Class: `review/judge/data-schema/s/python`; Owned paths: none (read-only; write nothing).
- Runtime bound: 20 minutes.
- Scope: the **uncommitted** working-tree diff in `/home/lee/projects/lee-llm-router` limited to
  `config/staffing/channels.yaml`, `config/staffing/schema/channels.schema.json`,
  `config/staffing/schema/attempt-record.schema.json`, `src/lee_llm_router/staffing/catalog.py`,
  `tests/test_staffing_catalog.py`, `tests/test_staffing_attempt_record.py` (`git diff -- <those>`).
  Ignore every other file. Packet under review: `docs/staffing/packets/M1-catalog-schema.md`; plan:
  `/home/lee/projects/chief-of-staff/docs/staffing-multi-account-plan.md` (M1).
- Context: the M1 worker chain stalled twice on Gemini, then failed only on Black formatting on
  Luna and DeepSeek; the supervising session then ran Black itself and stopped before a verified
  run or review. This review is that missing review.

## Judge (ACCEPT/REJECT each, with what you reproduced)
1. `channels.yaml`: subscription channels accept an optional `instances: [{instance_id, credential_ref, enabled}]`;
   a channel without it behaves as one implicit instance named after the channel; OpenCode Go's
   `fee_usd_month` carries a `10` entry effective 2026-09-14 (Lee) and the earlier `unknown` entry
   remains as history. The schema enforces the shape (unique instance ids, non-empty credential_ref).
2. `attempt-record.schema.json`: `route.channel_instance` is additive and optional; existing
   records validate unchanged (run the attempt-record tests and validate one real ledger row from
   `~/.local/state/lee-llm-router/attempts/A8Max.jsonl` against the schema).
3. `catalog.py`: the loader exposes instances (or the implicit one) with no behaviour change for
   single-instance channels; `lee-llm-router catalog explain` output is unchanged for current data.
4. Tests: `python3 -m pytest -q tests/test_staffing_catalog.py tests/test_staffing_catalog_explain.py tests/test_staffing_attempt_record.py`
   green; black/ruff clean on the Python files; nothing outside the six files is touched by this diff.
5. Anything that changes selection, dispatch, or headroom semantics in this packet is out of scope
   and contract-blocking (those are M2/M3).
End with `REVIEW VERDICT: ACCEPT` or `REVIEW VERDICT: REJECT`. Do not edit, commit, stash, or write.
