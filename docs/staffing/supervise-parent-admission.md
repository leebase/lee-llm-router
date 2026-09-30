# Supervise parent admission, version 1 — candidate 2026-09-29

New `/supervise` starts carry `run --unit-id PARENT --unit-state /absolute/STATE.jsonl
--unit-decision /absolute/decision.json`, in addition to all existing routing,
attestation, ownership, oracle and timeout flags. All three flags are required
together. Legacy starts and v2 attempt records retain their existing behavior.
No configuration, model eligibility, fallback or manual-primary policy changes.
The six-command supervision boundary remains unchanged.

Keep the parent journal in its existing WORK/STATE directory. Every substantive
child, diagnostic, review and repair uses the SAME identity/path. Admission uses
the existing bounded ledger writer lock; it serializes reservation and refuses
pending/unaccounted starts before provider launch. This version deliberately
serializes starts within a parent so each receives a reconciled value decision;
earlier disjoint-parallel instructions apply to legacy callers and genuinely
independent authorized work only. Schedule disjoint work inside this parent
serially. Never use new parent IDs, units or omitted flags to bypass inherited
resource accounting or refresh the allowance. It binds the parent identity to its journal in `unit-bindings.jsonl` beside
the existing per-host attempts ledger and rejects moved/deleted/reset journals.
It is an owner continuity check, not tamper protection against an owner deleting
both authoritative state and its per-host binding. Preserve both across cutover.

The router appends `start` (selected route/packet, timestamp, full supervisor
decision) and `finish` (persisted v2 attempt, elapsed seconds, truthful accounting).
A crash leaves a pending start. A missing attempt initially stays unaccounted,
regardless of green output; the bounded recovery below can reconcile start/time
without inventing a v2 record. Token/cost usage stays in the unchanged v2 record, including
`unavailable`; no token count or budget is invented. Launches admitted but failing
before provider construction consume a start conservatively. Earlier eligibility,
registry and admission refusals are separate pre-provider events recorded in WORK
by the supervisor, not fictitious provider starts.

## Decision JSON

Use `docs/staffing/supervise-parent-decision.example.json` as a shape example,
not task facts. Required fields:

- `version: 1`, stable `unit_id`, `completed_starts` (actual journal reservations).
- `previous`: null initially; thereafter SHA256 of the last start's decision,
  encoded as `json.dumps(decision, sort_keys=True).encode()`. This rejects stale
  child/resume snapshots and ordinary counter resets.
- `limits`: `{}` when Lee supplied no numeric cap. Otherwise optional `starts`,
  `seconds`, `reserve_starts`, `reserve_seconds`, and nonempty `authority` source.
  Limits stay identical throughout the parent. Time admission checks cumulative
  actual elapsed time plus the proposed timeout and reserved final capacity;
  starts admission likewise includes reserve. `final_review` can consume reserve.
  This minimal version supports start/time envelopes; other supplied resource
  limits still require supervisor accounting before launch and must not be silently
  substituted. Greater authority is a human policy decision, not an edited limit.
- `gaps`: authoritative acceptance rows. Each has stable `id`, `proposition`,
  frozen DoD `source`, `state` (OPEN/BLOCKED/PROVED/WAIVED/NOT_REQUIRED),
  `next_falsifier`, retained `history`. Non-open rows require `evidence`,
  `revision`, `observed_at`; WAIVED/NOT_REQUIRED also require an `authority`
  object with `source`, `scope`, `conditions`. Any row change appends history;
  waived/nonrequired changes additionally cite `governing_authority`. The complete ID/proposition/source/kind set freezes at inception and cannot
  grow, disappear or reset (including duplicate propositions). Include an OPEN
  row with kind independent_review at inception. New findings map to frozen rows.
  Governing scope changes need attributed authority and explicit handoff retaining
  counters; they cannot silently widen this transaction. Reopen only proofs affected by material
  changes. A task waiver cannot erase a final-release human gate.
- `assessments`: one entry per previous start, in journal order, with `start`,
  boolean `advanced`, boolean `denied`, inspected `evidence`. Prior entries are
  immutable. Multi-target starts additionally name advanced_targets; movement on
  one row never resets another row’s failure streak. `advanced` means actual proposition movement, not a passed test,
  file heartbeat or a new reviewer finding ID. Denial is permanent for that
  gap/capability, regardless of method label or hypothesis wording. Two consecutive nonadvancing attempts prohibit unchanged method.
- `dispatch`: `targets` (OPEN/BLOCKED gap IDs), `method` (stable causal ID),
  `capability`, `hypothesis`, `proposition`, finite `oracle`, `falsifier`,
  `alternatives`, `why`, `revision`, `phase` and `repair_round`. Phases are
  author/diagnose/repair/review/final_review. Bound comes from actual `--timeout`.
  The hypothesis/capability pair cannot be unchanged when a targeted method is
  renamed. Semantic equivalence and grants remain supervisor/reviewer judgments.
  Round begins at 0. A completed review closes its round; repair after it must
  use the next directed round (at most 2).
  Multiple packets in a directed round retain its number; changing it does not
  renew allowance. Review phases require existing `--role review --author-route`;
  existing family independence policy still enforces eligibility. After completed final review no substantive starts remain. Round 2 permits
  final review only, with no diagnosis/review cycling. An incomplete review
  execution permits one recovery attempt, never a fresh allowance. If the initial
  review covers unchanged final source, no duplicate review is needed. Keep or
  reopen review coverage honestly when material source changes, retaining evidence.

After an accounting failure, retain dispatcher/registry logs and inspect them.
A decision may include reconcile entries with start and evidence, optionally
attempt_id for an actual persisted v2 record. No successful v2 record is required.
The reservation retains the original host, Linux boot/controller incarnation,
unique inherited worker marker and selected route components. Before either
recovery path, admission proves the controller finished or died and scans the
original host's same-user processes for surviving marked workers. A readable environment containing the worker marker always refuses recovery.
If a same-user environment is unreadable, readable Linux creation ticks may
exclude only a process strictly older than the retained controller: it cannot
have inherited that controller’s fresh marker. Equal ticks are ambiguous at
Linux clock resolution; same-time/newer unreadable processes refuse recovery.
Missing, malformed or unreadable process creation identity, unknown controller
creation identity, and unsupported host evidence also refuse precisely; registry cleanup alone is insufficient. Stop the actual worker through
existing facilities first. On a reboot the original kernel's workers are gone.

With an actual record, match packet, selected route components and normalized
timezone-aware capture timestamp; retain its actual elapsed time and usage.
Without one, retain the consumed start, conservative reservation-to-reconciliation
elapsed upper bound, and explicitly unknown usage and outcome. Do not manufacture
execution success, consent, a token figure or billing. A supplied seconds cap must
accommodate that conservative time or admission refuses exhausted time; a missing
token/cost figure alone is not unknown start accounting. Other actual resource
caps remain supervisor-accounted and may require a precise incomplete refusal.
Linux process evidence enables this recovery; hosts without it cannot currently
prove orphan shutdown through this seam. Existing records/legacy calls remain
compatible. No routine Lee continuation approval is required.

## Value and authority remain supervisor responsibilities

Before another start or stop, WORK records remaining parent outcome, best
candidate/revision, useful evidence, failure hypothesis, alternatives and finite
next falsifier, cumulative resources/remaining authority, and disposition. Track
first useful result and last meaningful movement across resume. Diagnose once
when it eliminates a necessary uncertainty. A denied routed approval method must
not be retried with new syntax/model; an already authorized interactive capability
is a valid causal change, even when observed setup leaves full recall OPEN.

The contract bounds authoring → independent review → at most two directed
remediation rounds → final independent review. Supervisor triages review against
the frozen requirements; unrelated hardening cannot create scope. Run the actual
parent consuming journey early and at final acceptance. PROVED requires actual
specified evidence. Green leaves and proxy tests cannot replace a human gate
without an explicit scoped waiver. The router checks data/counters and does not
certify value, grants, method equivalence, valid waivers or LLM instruction-following.

Human escalation names exact decision/action, why now, alternatives actually
considered, recommendation and consequences. Continue useful independent work.
Economic or envelope stops preserve incomplete state; no "May I continue?" inside
existing authority. Acceptance, code review, behavioral evaluation and installation
are separate gates. No installation is performed by this candidate.

Review assessments include review_outcome: passed, blocking or incomplete,
with inspected evidence. A record proves accounting, never review success.
Incomplete execution permits one bounded recovery within the same round; a
completed blocking review requires the next directed repair round. Multiple
targets name advanced_targets explicitly; movement on another row never resets
the failed target’s method streak. Labels/capability claims remain subject to
independent evidence inspection.
