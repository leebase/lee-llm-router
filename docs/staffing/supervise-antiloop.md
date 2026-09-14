# Supervise Anti-Loop Protocol

The router terminates looping or hung workers structurally via explicit runtime flags:
- `--timeout <bound×60>`: Hard wall-clock ceiling; packets must declare a runtime bound.
- `--stall-minutes 10`: Joint-silence kill (no output and no owned-file change).
- `--progress-minutes 20`: No-progress kill (streamed activity without modifying owned files).
- `--stall-action`: Configures router kill action on stall or no-progress.

## Kill Kinds
Recorded as `platform_timeout` with provenance `dispatch kill: <kind>`:
- `ceiling`: Total run duration exceeded wall-clock timeout.
- `stall`: Joint silence — no output streamed and no owned-file change for the stall bound.
- `no_progress`: Worker streamed tokens without touching owned files.

## Authority & Observations
Lee (2026-09-13): "activity is not progress; a worker that streams without touching its owned files is killed by the router, not by the supervisor noticing." ("Activity ≠ progress. A hung worker is terminated by the router within its stall bound; a supervisor that waits past the bound is the loop.")
Observation (2026-09-12): Pi transport hang took 30 min before, 79 s with the ceiling.

## One-Repair Rule
A `stall` or `no_progress` timeout is a hung worker, not slowness: never re-dispatch unchanged. Repair once (halve packet, tighten owned paths/oracle, or lower `--timeout`); if it times out again, escalate immediately.

## Router-enforced (2026-09-14, S5b)
`lee-llm-router run` refuses an unchanged re-dispatch: same packet sha on the same route whose
latest attempt was killed for `stall` or `no_progress` exits 3 (`kind: unchanged_redispatch`)
before registration or launch. Ways through: change the packet, pass a strictly smaller
`--timeout` than the prior ceiling, or `--parent <attempt> --escalation-reason …`. A `ceiling`
kill or any other failure class does not trigger it. Live proof 2026-09-14: the stall-killed
hung-worker packet re-dispatched identically → refused naming attempt `router-run-7f2a68e5…`.
