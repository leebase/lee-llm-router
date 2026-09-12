# Packet D224-1 — `/supervise` and `/crew` shims: five harnesses, explicit argument binding, native smokes

- Kind: `impl`
- Class: `impl/deterministic/none/m/python`
- Declared size: about 8 files, at most 600 changed lines
- Owned paths: `src/lee_llm_router/shims.py`, `src/lee_llm_router/templates/shims/` (all files),
  `tests/test_shims.py`, `tests/test_shims_parity.py`, `tests/test_shims_native_smoke.py` (new),
  `docs/staffing/shims-native-smoke.md` (new report).
- Forbidden paths: everything else; in particular `doctor.py` beyond what `shims install/diff`
  already calls, `config/staffing/*`, the installed shim files under `~/.claude`, `~/.codex`,
  `~/.config/opencode`, `~/.pi`, and any project `.omp/` — do **not** run `shims install`
  against the real home; use a temp home (`LEE_LLM_ROUTER_SHIM_HOME`, see `resolve_home`).
- Authority: chief-of-staff `decisions.md` D224 (Lee: "it is supposed to work in all my
  harnesses: codex, claude, omp, pi, and opencode"). Findings from the Codex door, verified by
  the Chief: `HARNESS_TAGS` has four entries and omits Pi; the templates contain no
  `$ARGUMENTS`/`$1` binding and only say `<plan-path>` in prose; the parity test asserts
  exactly four targets.

## Changes

1. **Pi target.** Add `"pi"` to `HARNESS_TAGS`, `HARNESS_FORMS` ("Pi prompt template"),
   frontmatter extras, and `COMMAND_TARGET_FILENAMES`/target path resolution: global prompt
   template at `<home>/.pi/agent/prompts/<command>.md`. Pi's format (its docs at
   `~/.npm-global/lib/node_modules/@earendil-works/pi-coding-agent/docs/prompt-templates.md`):
   Markdown with optional `description` and `argument-hint` frontmatter; arguments via `$1`,
   `$@`/`$ARGUMENTS`. Marker/hash handling identical to the other targets.
2. **Explicit argument binding in both templates** (`supervise.md.tmpl`, `crew.md.tmpl`).
   Every harness in scope substitutes `$ARGUMENTS` (Claude Code, Codex custom prompts, Pi,
   OpenCode; OMP appends unused arguments — verify by reading OMP's docs or `omp --help` and
   record what you found). Add near the top of each template a binding block, e.g. for
   supervise:
   `Arguments as supplied: \`$ARGUMENTS\`` followed by the parsing rule: first token is the
   plan path; the remainder is `crew NAME` or `auto` (default `auto` when absent). Replace
   the prose-only `<plan-path>` references so the numbered loop reads the plan path from that
   bound line. For crew: the argument is the packet path or class string as the template
   already documents. If a harness needs a different placeholder, render it per harness
   through the existing per-harness frontmatter/extra mechanism — do not fork the template
   body.
3. **Codex invocation syntax.** Record in the rendered Codex frontmatter/description and in
   the report that Codex's user-facing invocation is `/prompts:supervise <args>` (custom
   prompts namespace), so the doc does not claim `/supervise` for Codex.
4. **Tests.** `test_shims_parity.py`: five targets, and a rendering assertion that each
   target's rendered body contains the literal `$ARGUMENTS` binding line. `test_shims.py`:
   Pi target path, frontmatter, marker round-trip, `shims diff` clean after install into a
   temp home.
5. **Native expansion smokes** (`tests/test_shims_native_smoke.py`, marked
   `@pytest.mark.native` and skipped unless `LEE_LLM_ROUTER_NATIVE_SMOKE=1`): for each of the
   five harnesses, install into a temp home a throwaway template `argecho.md` whose body is
   exactly `Reply with one line and nothing else: ARGS=<$ARGUMENTS>` (same frontmatter shape
   as the real shim for that harness), then invoke the harness in its non-interactive mode
   with `/argecho /tmp/plan-x.md auto` (Codex: `/prompts:argecho …`) and assert the reply
   contains `ARGS=</tmp/plan-x.md auto>`. Use the cheapest model each harness offers
   (Claude: `--model claude-haiku-4-5-20251001`; Codex: default; Pi: its default; OpenCode:
   default; OMP: default) and a 120 s timeout per harness. Run the smoke once yourself with
   the env var set and paste every harness's exact command and reply into
   `docs/staffing/shims-native-smoke.md`; a harness whose non-interactive mode cannot expand
   templates is reported as such with the evidence, not asserted around.

## Oracle

`python3 -m pytest -q tests/test_shims.py tests/test_shims_parity.py tests/test_shims_native_smoke.py`
(the native smoke file must pass in its skipped state; the live run is separate evidence).

## Required evidence

Oracle output; `LEE_LLM_ROUTER_NATIVE_SMOKE=1 python3 -m pytest -q tests/test_shims_native_smoke.py -rs`
output; the smoke report file; `python3 -m black --check` and `ruff check` on owned Python
files; `lee-llm-router shims diff` against a temp home showing five rendered targets;
`git status --short` showing only owned paths. End with a short report.

## Stop / escalation

Stop and report if a harness's template placeholder cannot be determined from its docs or
binary (say which and what you tried), if the smoke needs a credential you do not have, or if
the oracle fails twice for the same cause. Do not commit. Do not stash. Do not touch the real
installed shims. Do not write `decisions.md`.
