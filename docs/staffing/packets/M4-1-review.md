# Review packet M4-1 — credential staging module

Plan: `/home/lee/projects/chief-of-staff/docs/staffing-multi-account-plan.md`,
M4. Independent review of the combined result of
`docs/staffing/packets/M4-1-credential-staging-module.md`,
`M4-1-fix1-eager-unsupported-harness.md` (fixed a real defect: an
unsupported-harness call did not raise until the `with` block was entered),
and `M4-1-fix2-black-format.md` (Black formatting only). Author route:
`pi-gpt-5-6-luna-xhigh-openai-sub` (excluded from this review for
independence).

Owned paths under review (read-only for you — do not edit): `src/lee_llm_router/staffing/credentials.py`, `tests/test_staffing_credentials.py`

## What to check

Read `src/lee_llm_router/staffing/credentials.py` and
`tests/test_staffing_credentials.py` in full. This module resolves a
`credential_ref` string to a real file under
`~/.local/state/lee-llm-router/credentials/<ref>.json` and builds a
temporary, isolated "staging home" directory containing a copy of exactly
one credential, laid out at the relative path a supported coding harness
(`opencode` or `pi`) expects, plus the env vars needed to point that
harness's subprocess at the staging home. This module does **not** wire
into actual dispatch yet (that is a separate, not-yet-run packet, M4-2) —
review this purely as a standalone, independently correct module.

Verify by actually running (do not just read):

```bash
.venv/bin/python -m pytest tests/test_staffing_credentials.py -q
.venv/bin/black --check src/lee_llm_router/staffing/credentials.py tests/test_staffing_credentials.py
.venv/bin/ruff check src/lee_llm_router/staffing/credentials.py tests/test_staffing_credentials.py
```

If you have no command-execution tool available, say so explicitly in your
verdict and review statically only — do not claim you ran commands you did
not run.

Check specifically:

1. **Real credential files are never read for writing, never modified, never
   copied outside a throwaway temp directory, and never referenced by path
   in a way that would leak into logs/artifacts.** `resolve_credential_path`
   must be read-only. `stage_harness_home`'s `shutil.copyfile` must copy
   *from* the real credential file *to* the staging home, never the reverse.
2. **Fail-closed correctness:** a missing credential file raises
   `CredentialStagingError(kind="missing_credential")` before any staging
   directory is created. An unsupported harness (anything other than
   `"opencode"`/`"pi"`, including `"omp"`) raises
   `CredentialStagingError(kind="unsupported_harness")` **immediately on
   call, before `tempfile.mkdtemp` runs** — even if the caller never enters
   the returned `with` block. Confirm `stage_harness_home` is a plain
   function that validates eagerly and only returns a context manager
   (backed by a private `@contextmanager` generator) after validation
   passes — not a bare `@contextmanager` generator itself, which would defer
   all validation to `__enter__()`.
3. **Cleanup is unconditional:** the staging home is deleted whether the
   caller's `with` block succeeds or raises. No temp directory should ever
   survive past the `with` block under any test scenario.
4. **Correct per-harness layout:** `opencode` → `<HOME>/.local/share/opencode/auth.json`,
   only `HOME` set. `pi` → `<HOME>/.pi/agent/auth.json` with both `HOME` and
   `PI_CODING_AGENT_DIR` (`= <HOME>/.pi/agent`) set. Confirm the code
   actually produces this layout and the tests actually assert it (not just
   assert something weaker).
5. **Test fixture hygiene:** confirm the fake credential bytes used in tests
   (`_FAKE_CREDENTIAL`) are clearly fabricated placeholder content, not
   anything resembling a real API key/token shape, and that no test touches
   a real path under `~/.local/state/lee-llm-router/credentials/`.
6. Any other correctness, safety, or test-quality defect you find.

## Verdict

State PASS/ACCEPT or REJECT with concrete findings, each citing the exact
line(s) and why it is a defect (not a style preference). If you ran the
commands above, quote their exit codes/output in your verdict.
