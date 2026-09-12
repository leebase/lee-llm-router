# Chief of Staff — Phase 3 answer 1 (2026-09-11): acceptance-run defects, headroom, and the path to close

The acceptance run did its job: it landed A1 as a reviewed commit and exposed three real
defects plus one hard constraint. Rulings (Chief, D213; recorded for the D214 seal):

1. **Protocol defect (skill).** After `staff` (crew or auto), the loop must dispatch with the
   block's chosen route: `run --route <impl primary>` for implementation and `--route <review
   primary>` for review, falling back along the block's same-role arrays only when the
   primary is ineligible at dispatch, and recording the fallback. `run` never re-selects
   inside a supervised loop. Fix the template, its parity tests, and reinstall.
2. **`verified_success: false — evidence_incomplete` on a passing, attested attempt** is a
   defect until proven otherwise: find whether the skill omitted `--supervisor-route`, or the
   attestation path in `run` requires something the skill did not pass; fix so that a passing
   oracle with an attested supervisor route verifies true; test both branches.
3. **Class over-tagging.** `impl/deterministic/authority+security/s/python` for a text-explain
   change came from prose mentions. Per D206, `domain_tags` derive only from an explicit
   `domain:` field in the packet or from owned-path patterns in the keyword table, never from
   free text. Fix `derive_class.py` and the table; re-derive the two acceptance items.
4. **A2 (import concurrency).** The rerun's candidate is rejected for the reasons the build
   supervisor gave (test-local surrogate; oversized diff). Repackage A2 per Rule B into
   `A2a` transaction held by both production import paths with a real multiprocessing test
   that exercises them, and `A2b` cleanup, each with its oracle.
5. **Headroom is the constraint, and it is not bypassed.** `openai-sub` weekly is at 7%,
   TOO FAST, reset 2026-09-14 20:34 CDT. Sol Low, Sol High, Luna XHigh, and Astra Low are
   `likely_exhausted` until then. Therefore, for the rest of Phase 3:
   - the build supervisor and the acceptance session run as **Sonnet 5 high via Claude
     Code** (`claude -p --model claude-sonnet-5 --permission-mode bypassPermissions`, headless,
     hard timeout, logged), attesting `claude-claude-sonnet-5-high-anthropic-sub` as the
     supervisor route (the ledger records the true route, not the crew's nominal one);
   - implementation stays on the explain-chosen proven route (GLM via Pi/OpenRouter) with
     Gemini 3.8 Flash as the eligible next rung; the OpenAI rungs are simply excluded and the
     block says so;
   - the gate reviewer falls back to **Sonnet 5 high via Claude Code, read-only** when Astra's
     channel is exhausted, recorded as a fallback with the reason (same rule as the DeepSeek
     fallback in Phase 0/1);
   - if any step has no eligible route at all, stop that step and record it; do not wait
     idle for the OpenAI reset unless nothing else can proceed.
6. **A second acceptance rerun is authorized** after fixes 1–4, because the consumed rerun
   was spent on a skill defect, not on the session's conduct. The rerun session receives only
   the installed `/supervise` body, the plan path, and `crew sol-low-glm-pi`.

Then P3-7: gate items 1–4, the gate review (fallback reviewer if needed), remediation, commits,
closing report in the D209 order. Chief re-runs the gate, reads the acceptance ledger, and
seals D214.
