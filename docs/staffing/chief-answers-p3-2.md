# Chief of Staff — Phase 3 answer 2 (2026-09-12): headless mode, foreground dispatch, and the acceptance launch

Evidence: the second acceptance session (run 6, launched as `claude -p … '/supervise <plan>
crew sol-low-glm-pi'`) reached dispatch correctly on the crew's GLM route, then backgrounded
the `run` and ended its turn "to be notified" — which a headless one-shot session never is.
The worker died with the session (census cleaned one stale record; no attempt row). Two
earlier launches died on mechanics: a command file's YAML frontmatter passed as the prompt
argument, and a body with no arguments. Rulings:

1. **Skill defect, foreground rule.** The `/supervise` template gains, near the top: "Run every
   router command in the foreground and wait for it to return. Never background a `run`, a
   review, or a rollup; `run` has its own watchdog. Do not end your turn while a dispatched
   command is running." Parity tests; reinstall with `shims install --apply`; independent
   review; commit `feat(staffing P3): foreground dispatch in supervise`.
2. **Headless launch form, recorded in `phase3-contracts.md`:** from the repo root,
   `timeout 5400 claude -p --model claude-sonnet-5 --permission-mode bypassPermissions
   '/supervise /home/lee/projects/lee-llm-router/docs/staffing/phase3-acceptance-plan.md crew
   sol-low-glm-pi' < /dev/null > <log> 2>&1`, run **in the foreground of the build session**
   so the build session waits for it. Never pass the command file's contents as the prompt.
3. **Third acceptance run is authorized** after fix 1 (runs 4–6 were mechanics and a skill
   defect, not the session's conduct). Same uncoached content; judge only the ledger.
4. **Supervisor-authored fixes.** The close-out session authored fixes itself in P3-7-1..3
   (reviewed clean). Accepted for that round; from here, author through `run` on the
   explain-chosen route and review independently, as the doctrine says.

Then the gate (items 1–4), the gate review by Sonnet 5 read-only as the recorded Astra
fallback, remediation, commits, closing report in the D209 order to
`~/projects/chief-of-staff/tmp/staffing-p3/closing-report-sonnet.md`, ledgers, journal line.
