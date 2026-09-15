# Review packet M4-2 — wire credential staging into dispatch

Plan: `/home/lee/projects/chief-of-staff/docs/staffing-multi-account-plan.md`,
M4. Independent review of `docs/staffing/packets/M4-2-dispatch-credential-wiring.md`.
Author route: `agy-gemini-3-8-flash-high-gemini-sub` (excluded from this
review for independence).

Owned paths under review (read-only for you — do not edit): `src/lee_llm_router/staffing/run.py`, `src/lee_llm_router/doctor.py`, `tests/test_staffing_run.py`, `tests/test_doctor.py`

## Context

M4-1 (already committed, `src/lee_llm_router/staffing/credentials.py`)
resolves a channel instance's `credential_ref` to a real file and builds a
temporary staged "home" directory containing only that credential, laid out
where the `opencode`/`pi` harnesses read their auth from. M4-2 wires that
module into the actual `lee-llm-router run` dispatch path so a worker
subprocess launched against a multi-account channel only ever sees the one
credential belonging to the instance `staff`/`run` selected — never the
real `$HOME`'s credentials, never another instance's credential.

Verify by actually running (do not just read):

```bash
.venv/bin/python -m pytest tests/test_staffing_run.py tests/test_doctor.py -q
.venv/bin/python -m pytest -q
.venv/bin/black --check src/lee_llm_router/staffing/run.py src/lee_llm_router/doctor.py tests/test_staffing_run.py tests/test_doctor.py
.venv/bin/ruff check src/lee_llm_router/staffing/run.py src/lee_llm_router/doctor.py tests/test_staffing_run.py tests/test_doctor.py
```

If you have no command-execution tool available, say so explicitly and
review statically only — do not claim you ran commands you did not run.

## What to check

1. **Fail-closed ordering:** in `doctor.py`'s `_run_run()`, confirm the
   credential resolution/validation (missing file, or unsupported harness)
   happens *before* `register_run(...)` and before any subprocess is
   spawned — i.e. a failure here must never register a run or call `popen`.
   Trace the actual control flow, don't assume from the packet description.
2. **Single-instance channels are provably unchanged.** For a channel with
   no declared `instances` (today's normal case — `openai-sub`, `openrouter`,
   `anthropic-sub`, `gemini-sub` per `config/staffing/channels.yaml`),
   confirm no credential lookup is attempted at all and the `env` kwarg
   passed to `popen` is either absent or identical to before this packet
   (no `extra_env`/staging path is reachable).
3. **`extra_env` merge correctness in `run_supervised_dispatch`:** confirm
   it merges into a copy of `os.environ` (never mutates `os.environ` in
   place, never modifies the real process's own environment), and correctly
   coexists with the existing Linux provenance-marker injection (both must
   land in the same child env dict — check this isn't two competing
   `launch_kwargs["env"]` assignments where one silently overwrites the
   other).
4. **Credential isolation guarantees, traced end to end:** for a staged
   dispatch, the child subprocess's `HOME` (and `PI_CODING_AGENT_DIR` for
   `pi`) point only at the fresh temporary directory, that directory
   contains only the one resolved instance's credential content at the
   exact relative path the harness reads, and the directory is deleted
   after the dispatch completes (success, failure, or exception) — this
   should already be proven by M4-1, but confirm the M4-2 call sites don't
   bypass or duplicate that guarantee incorrectly (e.g. entering the context
   manager twice, or leaking the `with` block's env past its scope).
5. **The plan's declared scope boundary:** confirm no route dispatch through
   `omp`, `codex`, or `claude` harnesses is silently staged with a wrong or
   partial mechanism — an unsupported harness on a multi-instance channel
   must fail closed (exit 3), never silently dispatch unisolated.
6. Any other correctness, safety, or test-quality defect you find,
   including whether the new tests actually exercise real end-to-end
   behavior (e.g. via `doctor.main()`) versus merely asserting on internal
   call arguments in a way that could pass even if the wiring were subtly
   wrong.

## Verdict

State PASS/ACCEPT or REJECT with concrete findings, each citing the exact
line(s) and why it is a defect (not a style preference). If you ran the
commands above, quote their exit codes/output in your verdict.
