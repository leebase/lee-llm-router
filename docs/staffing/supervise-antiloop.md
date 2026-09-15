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

## Router-enforced no-work refusal (2026-09-15, S5c)

A clean worker exit is not, by itself, progress. A dispatch is **no effective work** only when
all of the following are positively evidenced: the worker exited 0 without a timeout, no
verification oracle ran, every owned path was measured as unchanged, **and stdout carries no
substantive answer/result**. A real answer in stdout (plain prose, or a non-empty `content`/
`text`/`response`/`output_text` field inside a JSON event stream) is work even when the worker
only read files, so planning and review workers are never accused. Top-level JSON strings and
string arrays are also valid answer shapes. A terminal usage receipt alone is not work. Text
in lifecycle, error, status, completion, or usage event context remains metadata even when it
is stored under `content`, `text`, `output`, `message`, `result`, or nested generic maps.
Event discrimination reads `type`, `event`, and recognized terminal scalar `status` values,
so status-only records and top-level arrays of event records retain metadata context through
all generic descendants. Completion metadata leaves that context only through a direct
generated-message slot (`message`, `item`, or `response`) on the completion event itself,
whose object explicitly identifies assistant/agent text; this includes
`response.output_text`. Generic `detail`, `payload`, and status containers cannot regrant
answer permission through a deeper generated-message slot; role and typed-result hints
anywhere under those containers remain metadata. Top-level typed result objects and untyped
Antigravity `status=SUCCESS,response=...` objects remain legitimate answers.

Such a run is recorded as a governed failure with the committed schema-valid class
`platform_env` (the no-launch/no-work platform surface; the filed needs-lee note of 2026-09-14
proposed exactly this class) and the provenance note
`dispatch no-work: ... no result/answer in stdout ... recorded as a platform_env governed
failure ...`. `lee-llm-router run` appends that one truthful schema-valid attempt and then
returns the governed nonzero result (exit 3), so a caller cannot mistake the no-work invocation
for a successful command. `lee-llm-router run` also refuses an unchanged re-dispatch of that
exact packet sha on that exact route (`kind: unchanged_redispatch`, exit 3) before registration
or launch, the same bounded stop as a `stall` or `no_progress` kill.

One repair, then stop. The first no-work attempt may be re-dispatched exactly once as an
explicit escalation (`--parent <attempt> --escalation-reason …`). When the immediately
preceding attempt on the same packet and route is itself no-work, the one repair is spent: no
`--parent` link reopens the identical cycle, and the refusal names both attempts. Legitimate
recovery stays open: a materially changed packet (new sha), a different route, a prior attempt
with a work result, an owned-path change, or verification (oracle) evidence is never no-work
and never refused. An unmeasured owned-path set is never accused, and any owned-path change,
oracle, nonzero exit, timeout, or substantive stdout answer is never no work.

As a final bound for an unknown future metadata spelling, every clean, unverified,
no-oracle, unchanged-path dispatch records an exact SHA-256 stdout/stderr result fingerprint
from a canonical JSON object. One first read-only answer and one retry remain allowed. If the
two consecutive results for the same packet and route have the same fingerprint, the next
unchanged dispatch is refused before registration or launch. Changed packet, route, stdout or
stderr result evidence, owned-path evidence, or oracle evidence resets the comparison. This
contains repeated unchanged no-progress without globally disabling retries or quarantining a
first legitimate read-only answer.
