# Packet P4-8-escalation-yaml — wire `escalation:` YAML key into `StepDefinition.escalation`

- Kind: `impl`
- Declared size: 2 files, at most 120 changed lines
- Owned paths: `src/agent_orch/playbook.py`, `tests/test_playbook.py`
- Oracle: `.venv/bin/python -m pytest -q tests/test_playbook.py`
- Review: independent, author route excluded
- Domain: none

## Background (read first)

P4-5 (Phase 4, committed `7751a07`) added `EscalationIntent` (`enabled: bool = False`,
`ladder: tuple[RoutingPreference, ...] = ()`) and `StepDefinition.escalation:
EscalationIntent | None = None` in `src/agent_orch/models.py`, plus the engine's ESCALATE
precedence step in `engine.py` that reads `step.escalation.enabled`/`step.escalation.ladder`.
All of that is real and tested (`tests/test_engine.py`).

But `src/agent_orch/playbook.py`'s `_parse_step` (the function that turns an authored
playbook YAML `steps:` entry into a `StepDefinition`) has **no parsing for an `escalation:`
key at all** — grep confirms zero occurrences of the string `escalation` anywhere in
`playbook.py`. A playbook YAML file that writes:

```yaml
escalation:
  enabled: true
  ladder:
    - harness: pi_cli
      model: deepseek-v4-pro
```

on a step today has that block silently discarded (unknown top-level step key — confirm
whether `_parse_step` rejects unknown keys outright or silently ignores them; if it currently
rejects, that's stricter but still means no working path from YAML to the engine mechanism).
Every `StepDefinition(escalation=...)` in the test suite today is constructed directly in
Python, not round-tripped through `load_playbook`. This is a real gap between the engine
mechanism and the only production path (LLM-authored YAML) that creates playbooks in
practice — closing it is required before any live cycle can exercise ESCALATE end to end
through the authoring pipeline rather than only through a hand-built `StepDefinition` in a
test.

## Requirement

Add a new `_parse_escalation(value: object, label: str) -> EscalationIntent | None` function
in `playbook.py`, mirroring the existing `_parse_token_exhaustion_fallback` (lines ~1057-1088)
and `_parse_routing`/`_parse_routing_preference` (lines ~1182-1229) patterns exactly:

- `value is None` -> return `None` (field absent, no escalation — today's exact behavior,
  unchanged for every existing playbook).
- Otherwise `_require_dict(value, label)`; allowed keys are exactly `{"enabled", "ladder"}`;
  unknown keys raise `PlaybookError` (same style as the two sibling parsers).
- `enabled`: optional, defaults to `False` if absent; must be a `bool` if present (raise
  `PlaybookError` on any other type, matching this file's existing type-checking style
  elsewhere for boolean fields, e.g. `lint_skip`).
- `ladder`: optional, defaults to `()` if absent; if present must be a list; each entry is
  parsed with the existing `_parse_routing_preference(entry, f"{label}.ladder[{i}]")` (reuse
  it verbatim — do not duplicate its field-parsing logic); a `None` result from
  `_parse_routing_preference` for any entry (i.e. an empty `{}` ladder rung) raises
  `PlaybookError` — same rule `_parse_routing_preference` already enforces for a `primary`/
  `fallback` entry, applied here to each rung.
- Wire the call into `_parse_step`, in the same place `token_fallback` is parsed (right before
  the final `return StepDefinition(...)`), as `escalation = _parse_escalation(
  payload.get("escalation"), f"{label}.escalation")`, and add `escalation=escalation` to the
  `StepDefinition(...)` constructor call. Do not add an `escalation` parameter to
  `load_playbook`'s top-level `defaults:` handling — per `models.py`, `escalation` is a
  per-step-only field (no `Playbook.default_escalation`), so there is no default-merging
  behavior to add, unlike `routing`/`token_exhaustion_fallback`.

## Tests (write these; existing tests must still pass unmodified)

In `tests/test_playbook.py`, near the existing token-exhaustion-fallback tests
(`test_load_playbook_parses_default_and_step_token_exhaustion_fallbacks` etc. — same file,
same style: build a minimal playbook YAML dict/string, call `load_playbook`, assert on the
parsed `StepDefinition`):

1. A step with no `escalation:` key parses with `step.escalation is None` (today's behavior,
   unchanged — regression guard).
2. A step with `escalation: {enabled: true, ladder: [{harness: pi_cli, model:
   deepseek-v4-pro}]}` parses to `step.escalation.enabled is True` and
   `step.escalation.ladder == (RoutingPreference(harness="pi_cli",
   model="deepseek-v4-pro", effort=None),)`.
3. A step with `escalation: {enabled: true}` (no `ladder` key) parses to
   `step.escalation.ladder == ()`.
4. A step with `escalation: {ladder: [...]}` (no `enabled` key) parses to
   `step.escalation.enabled is False`.
5. `escalation: {unknown_field: 1}` raises `PlaybookError` matching a message containing
   `unsupported fields`.
6. `escalation: {enabled: "yes"}` (non-bool) raises `PlaybookError`.
7. `escalation: {ladder: [{}]}` (an empty ladder rung) raises `PlaybookError` (same message
   shape `_parse_routing_preference` already raises for an empty routing-preference dict —
   assert on that shared message, don't invent a new one).

## Constraints

- Do not touch `engine.py`, `models.py`, or anything in Group A/B's already-committed diffs.
- Do not change `_parse_token_exhaustion_fallback` or `_parse_routing_preference` themselves —
  only call the existing `_parse_routing_preference`, don't inline a copy.
- No new top-level `steps[].escalation` default at the `defaults:` block level (see above).
