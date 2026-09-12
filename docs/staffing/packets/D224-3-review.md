# Packet D224-3 — re-review after D224-2 REJECT (native smoke reproducibility)

- Kind: `review`
- Class: `review/judge/none/s/python`
- Owned paths: none (read-only; write nothing).
- Scope: lee-llm-router `bc8e02c..d82f239` on top of the D224-2 scope `69c2e4f..bc8e02c`.
- Your D224-2 review accepted items 1, 2, 3, 5, 6 and rejected item 4 because your own run
  of the native smoke failed all five harnesses, with two isolation defects named (OpenCode
  symlinked its whole real data dir including the log path; unregistered `native` marker)
  and one report gap (no five-pass transcript).

## Judge

1. Isolation: OpenCode now links only `auth.json` into a fresh temp data dir; the `native`
   marker is registered in `pyproject.toml`; OMP's real-HOME use is documented in the test
   with the reason. Read the diff. Say whether the two named defects are closed.
2. Transcript: `docs/staffing/shims-native-smoke.md` §5 carries the Chief's five-of-five run
   (`5 passed in 58.95s`) made outside any sandbox. **Do not re-run the smoke**: your
   reviewer session runs inside `codex exec -s workspace-write` with no network and a
   read-only home, which is why Claude/Codex timed out, Pi got `fetch failed`, OMP hit a
   read-only SQLite and OpenCode could not open its log in your D224-2 run. Judge the
   transcript and the test code instead, and state plainly that your sandbox cannot
   reproduce a live harness smoke.
3. Deterministic oracle: `python3 -m pytest -q tests/test_shims.py tests/test_shims_parity.py tests/test_shims_native_smoke.py`
   (native cases skip without the env var) and black/ruff on the touched files.

End with `REVIEW VERDICT: ACCEPT` or `REVIEW VERDICT: REJECT`. Do not edit, commit, stash,
install shims, or write any file.
