# Independent Router-Owner Seam Review: Bonnie Integration

- **Review Target**: Router-Owner Transport and Workstream Seam (`src/lee_llm_router/staffing/`, `src/lee_llm_router/doctor.py`)
- **Reviewer**: Independent Reviewer (Router Owner Seam)
- **Verdict**: **PASS** (0 High, 0 Medium)
- **Scope**: Router-owner seam only; does not claim integrated Staff, customer, or Linode acceptance.
- **Material Files Reviewed**:
  1. `src/lee_llm_router/staffing/unit_admission.py`
  2. `src/lee_llm_router/staffing/executor.py`
  3. `src/lee_llm_router/staffing/run.py`
  4. `src/lee_llm_router/doctor.py`
  5. `tests/test_supervise_parent_admission.py`
  6. `tests/test_staffing_executor.py`
  7. `docs/staffing/supervise-parent-admission.md`
  8. `docs/staffing/protected-executor.md`

---

## 1. Executive Summary & Verdict

The router-owner seam introduces two coordinated mechanisms:
1. **Explicit workstream boundary handoffs** in `unit_admission.py` allowing ownership and authority transitions (e.g. bootstrapping authoring under Lee router-owner authority) while preserving whole-parent cumulative accounting, limits, gap sets, and assessment histories.
2. **Privileged host-governed transport execution** in `executor.py`, `run.py`, and `doctor.py` enabling trusted launcher prefixing at `popen` under strict host binding and immutability checks, without exposing parent state journals or granting workers self-confinement authority.

All 99 unit admission and staffing executor tests pass cleanly. Static verification confirms zero high or medium severity defects within the owner seam. Verdict is **PASS**.

---

## 2. Authority & Workstream Transition Analysis

- **Owner Delegation**: Lee explicit authority to act as repository owner for Bonnie is attributed via the version 1 `workstream` contract in parent decisions.
- **Review Window vs Whole-Parent Ledger**:
  - `_workstream_starts(starts, decision)` filters review and repair phases to the active `workstream` unit (`review_starts`), allowing a legitimate authoring/review cycle under the new owner.
  - All cumulative parent constraints remain enforced across the entire ledger (`starts`): total start counters (`len(starts) + 1`), total wall-clock seconds (`sum(f["seconds"])`), unchanging limits (`limits == previous.get("limits")`), gap propositions, unbroken assessment chains (`assessments[:len(old)] == old`), and method streak / definitive denial tracking.
  - New owner stages continue the existing parent ledger (starts 18/19 following start 17) rather than creating a disconnected ledger.
- **Contract Immutability & Anti-Evasion**:
  - `workstream` cannot disappear once introduced (`_require(old is None)`).
  - Stable workstream contracts cannot mutate within the same `id` (`_require(current == old)`).
  - Workstream IDs cannot be reused across starts (`all(s["decision"]["workstream"]["id"] != current["id"])`).
  - Boundary transitions require actual changed owner authority or changed owned surface paths; arbitrary renames are explicitly rejected.
  - Attributed authority is treated as supervisor assertion (consistent with `limits.authority`); no cryptographic grant is falsely claimed.

---

## 3. Prior Review Recovery & Phase Governance

- **Misclassification Handling**: The prior review recovery refusal stemmed from an incomplete environment review being classified as blocking. In `unit_admission.py`, `len(failed_reviews) < 2` permits one recovery for incomplete/failed reviews. Start 17 assessment is retained as incomplete.
- **No Third Repair Round**: The new owner unit represents a genuine governing boundary transition, not an evasive third repair round. Within any stable owned unit, the two-round repair cap (`0 <= round_number <= 2`) and author-after-review restrictions remain strictly enforced.
- **No Resource Refresh**: Scope authority handoffs do not grant additional execution budget or reset parent consumption counters.

---

## 4. Protected Executor & Transport Verification

- **Opt-In & Privileged Host Configuration**:
  - Invoked via `--executor-spec` and `--employee-id`; both flags are required together and mandate all three parent unit flags (`--unit-state`, `--unit-decision`, `--unit-id`).
  - Workers, tasks, and prompts cannot specify or influence the launcher prefix.
- **Strict Spec Parsing & Boundary Constraints (`load_executor_spec`)**:
  - Path must be canonical, absolute, and non-symlink; opened with `O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK` to reject symlinks and prevent FIFO read blocking.
  - Non-regular files (FIFOs, sockets, directories) fail immediately.
  - Hard byte bound (<= 65,536 bytes); strict JSON parser rejects duplicate keys and non-finite numbers (`NaN`, `Infinity`).
  - Fields are strictly constrained to v1 schema (`version=1`, nonempty string bounds <= 256 chars, no control chars).
  - `argv_prefix` is strictly bounded (1–32 literal strings <= 4,096 chars, no NUL bytes); `argv[0]` must be a canonical, non-symlink regular executable with `X_OK`.
- **Pre-Launch Validation & TOCTOU Protection**:
  - Initial validation verifies employee, parent transaction ID, and active target gap against the decision file before run selection.
  - Post-reservation validation in `doctor.py` re-checks the spec against the *retained* start event in the journal, preventing mutable decision tampering.
- **Child Invocation & State Protection**:
  - Router constructs governed provider arguments and substitutes the prompt first; `trusted_executor_argv_prefix` is prepended only at `base_popen` with `shell=False`.
  - Child inherits original `cwd`, stdin pipe, native stream capture, watchdog, and timeout controls.
  - Parent state journal (`STATE.jsonl`) remains strictly host-owned and unexposed to the child.
- **Attempt ID Allocation & Provenance**:
  - Host allocates `attempt_id` prior to reserving start and setting `LEE_EMPLOYEE_ATTEMPT_ID`.
  - Identical `attempt_id` is recorded in the START journal entry, attempt record v2, and `protected-executor-v1` provenance note (with SHA-256 of spec bytes, omitting raw launcher argv).
  - Both credential and non-credential branches correctly merge bindings and pass the executor argv prefix.
  - Failures and orphans trigger `finish_start` with `accounted: False`, requiring explicit reconciliation with zero silent loss.
  - Unavailable usage reports `unknown`; no fictitious token billing is emitted.

---

## 5. Test Reproductions & Evidence

```
$ python3 -m pytest -q tests/test_staffing_executor.py tests/test_supervise_parent_admission.py
........................................................................ [ 72%]
...........................                                              [100%]
99 passed in 25.43s

$ python3 -m pytest -q tests/test_staffing_run_authorization.py
............                                                             [100%]
12 passed in 5.71s
```

All 99 unit admission and protected executor tests pass, covering:
- Spec shape validation, symlink rejection, FIFO non-blocking rejection, and size boundaries.
- CLI binding verification across accepted, failure, and mismatched supervisor parameters.
- Preservation of stdin, environment, and native JSON usage streaming through real prefix wrappers.
- Cumulative parent accounting across owner workstream transitions and prevention of contract mutation.

---

## 6. Consuming Limitations & Out-of-Scope Demands

1. **Prefix is Not Confinement**: The argv prefix transport seam merely prepends a trusted host launcher; isolation and namespace containment depend on the downstream Staff sandbox adapter.
2. **Observability vs Authentication**: The `LEE_EMPLOYEE_*` environment variables provide process context/observability, not unforgeable child authentication.
3. **Supervisor Attribution**: Authority transitions rely on supervisor verification; no cryptographic attestation is asserted.
4. **Boundary of Acceptance**: This review certifies the router-owner seam only. End-to-end Linode deployment, customer acceptance, and multitenant network cost guarantees remain deferred to subsequent integrated testing.
