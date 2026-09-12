# Review Packet — P4-8-escalation-yaml

Independent review (read-only). Author route: `pi-deepseek-deepseek-v4-flash-openrouter`.

## What to inspect

Run `git -C /home/lee/projects/agent-orch diff -- src/agent_orch/playbook.py tests/test_playbook.py`
and review it against this requirement:

Add YAML parsing support for an optional `escalation:` key on a playbook step
(`escalation: {enabled: bool, ladder: [{harness, model, effort}, ...]}`), building an
`EscalationIntent` and wiring it into `StepDefinition.escalation`, mirroring the existing
`_parse_token_exhaustion_fallback`/`_parse_routing_preference` patterns in the same file.
Absent `escalation:` key must parse exactly as before (`step.escalation is None`).

## Verification already performed by the supervisor (for context, not to be trusted blindly)

- `env PYTHONPATH=src .venv/bin/python -m pytest -q tests/test_playbook.py` — 140 passed.
- Full agent-orch suite: 1936 passed, 9 skipped, 3 failed — the 3 failures are in
  `tests/test_codex_usage.py`, a pre-existing, unrelated baseline defect documented
  repeatedly elsewhere in this phase's ledger, not caused by this diff.
- `black --check` clean on both files; `ruff check` clean on both files except one
  pre-existing, untouched finding at `playbook.py:281` (not part of this diff).

## Your job

Confirm independently (do not just repeat the above): read the diff yourself, check the new
`_parse_escalation` function's logic against the stated requirement, check the new tests
actually exercise acceptance, defaults, and rejection paths, and check nothing outside the
two owned files changed. Report `REVIEW VERDICT: ACCEPT` or `REVIEW VERDICT: REJECT` with
Contract-blocking / Hardening / Future findings.
