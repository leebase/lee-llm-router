# Packet D224-2 — independent review of the five-harness shim repair

- Kind: `review`
- Class: `review/judge/none/s/python`
- Owned paths: none (read-only; write nothing). Whole review in your final reply.
- Scope: lee-llm-router commits `69c2e4f..bc8e02c` (`git log --oneline 69c2e4f..bc8e02c`).
  Authority: chief-of-staff `decisions.md` D224 ("`/supervise` requires native five-harness
  parity, including Pi"): Pi as a managed shim target at its native prompt-template location;
  plan path and mode bound explicitly, not via harness fallbacks; native command expansion
  exercised in every harness with the expanded prompt demonstrably containing the plan path
  and mode; Codex's actual user-facing invocation syntax recorded.
- Author: gemini-3.8-flash-high via agy (packet `docs/staffing/packets/D224-1-five-harness-shims.md`),
  plus the Chief's follow-up `bc8e02c`.

## Judge (ACCEPT / REJECT each, with what you reproduced)

1. `HARNESS_TAGS` has five entries and Pi renders to `<home>/.pi/agent/prompts/<command>.md`
   with Pi's frontmatter (`description`, `argument-hint`); marker/hash round-trips
   (`tests/test_shims.py`).
2. Both templates bind `$ARGUMENTS` explicitly with a parsing rule (plan path first, then
   `crew NAME` | `auto`; OpenCode quoted-string note), and the rendered bodies for all five
   targets contain the binding line (`tests/test_shims_parity.py`, five targets).
3. Codex's invocation is recorded as `/prompts:supervise <args>` in the rendered Codex shim.
4. `tests/test_shims_native_smoke.py` + `docs/staffing/shims-native-smoke.md`: read the
   report; then run `LEE_LLM_ROUTER_NATIVE_SMOKE=1 python3 -m pytest -q tests/test_shims_native_smoke.py -rs`
   yourself once (it installs a throwaway `argecho` template into a temp home per harness and
   invokes each harness's non-interactive mode; ~2 minutes, cheap models) and paste the
   result. Say whether the five replies demonstrably contain the plan path and mode.
5. The shim body never names a provider binary (the hard command boundary guard in the
   parity test) and the `lee-llm-router shims diff` against a temp home renders five targets.
6. Oracle `python3 -m pytest -q tests/test_shims.py tests/test_shims_parity.py tests/test_shims_native_smoke.py`
   and black/ruff on the touched Python files.

End with a single line `REVIEW VERDICT: ACCEPT` or `REVIEW VERDICT: REJECT`. Do not run the
full suite (the Chief runs it). Do not edit, commit, stash, install shims into the real home,
or write any file.
