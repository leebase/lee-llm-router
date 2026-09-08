You are the independent reviewer for Crew Resolver Sprint 4 in ~/projects/lee-llm-router (read-only sandbox; you may run the CLIs via `PYTHONPATH=src .venv/bin/python -m lee_llm_router.doctor ...` with `--no-event` or `--events-file /dev/null`-style scratch paths; you cannot run pytest — the supervisor's run is authoritative and is quoted below). Never run `shims install --apply` outside `LEE_LLM_ROUTER_SHIM_HOME=<tmp>`; never edit anything.

Report findings as High / Medium / Low with file:line, a reproduction, and why it violates the contract. End with `VERDICT: PASS` (no High/Medium) or `VERDICT: FAIL`. Do not pad; no findings is a valid outcome.

## Sprint done condition (plan)
Each shim, invoked in its harness, produces the same resolution for the same crew/role as the CLI, and the event ledger shows four entries with distinct harness tags. Verifiable form this sprint (apply is Lee's): `shims install --dry-run` renders all four; a test runs each rendered shim's exact `lee-llm-router resolve` line as a subprocess and asserts four events with four distinct `harness` values and equal route identity. Packet 1 is the D188 rule change.

## Contracts (authoritative; the supervisor wrote these once and packets quoted them)
## C1 — D188 role-scoped Gemini 3.1 Pro (replaces the blanket refusal)

1. Two role classes exist: `coding` and `planning_review`.
2. The role-name → role-class mapping is ONE readable constant in `src/lee_llm_router/crews.py`
   (resolver config, never `crews.yaml`), named `ROLE_CLASS_BY_ROLE`, with a comment citing
   decisions.md D188 and stating that the stage assignment is the supervisor's judgment recorded
   for Lee's confirmation. Contents:
   - `author` → `coding`
   - `envision`, `ideate` → `planning_review` (planning)
   - `reconsider`, `score` → `planning_review` (review)
   - governed roles: `primary` → `coding`; `reviewer`, `judge` → `planning_review`
3. `ROLE_SCOPED_MODELS = frozenset({"gemini-3.1-pro"})` replaces `FORBIDDEN_MODELS`.
   `is_role_scoped(model)` replaces `is_forbidden(model)`. `role_class(role)` returns the class
   or raises `CrewsConfigError` naming the role and the known roles. `NEVER_AUTOMATIC_MODELS`
   and `is_never_automatic` are unchanged.
4. Citation constant: `ROLE_SCOPED_CITATION = "decisions.md D188"` replaces `FORBIDDEN_CITATION`.
   Every refusal or skip under this rule cites it.
5. A role outside the mapping fails closed in every mode: `ResolutionError`, exit 3, kind
   `config`, message names the role and the known roles, cites D188. Never "assume planning".
   (This check runs after the existing unknown-crew / unknown-stage checks, so those messages
   are unchanged.)
6. For a `coding` role, a role-scoped model:
   - strict: the named worker is refused — exit 3, kind `forbidden`, message names the worker,
     the model, the role, the class, and cites D188.
   - flex: skipped, never chosen; the reason names each skipped worker in the form
     `skipped <worker_id> (role-scoped model <model> is never automatic for coding role
     '<role>', decisions.md D188)`; if every candidate is skipped → exit 3, kind `forbidden`.
   - bind: refused — exit 3, kind `forbidden`, regardless of `--authorized-by`.
7. For a `planning_review` role, a role-scoped model is an ordinary worker: eligible in strict,
   flex, and bind, subject to exactly the same headroom and never-automatic rules as any other
   worker, with no special wording in the reason.
8. `doctor --crews`: the forbidden-model warning becomes a role-scoped note. Warn only where a
   crew stage whose role class is `coding` names a worker that resolves to a role-scoped model:
   `Crew '<crew>' stage '<stage>' uses role-scoped model '<model>' in a coding role; the
   resolver will never choose it there (decisions.md D188)`. A stage name with no role class
   is also a warning (`stage '<name>' has no role class (decisions.md D188)`). Summary line
   says `N role-scoped warning(s)` instead of `N forbidden-model warning(s)`. Exit code
   semantics unchanged (warnings do not fail doctor).
9. Live-file expectation (evidence, not a test fixture): `gemini-pro-crew` names
   `antigravity_gemini31_pro` at `envision` and `reconsider` only, so `doctor --crews` on the
   live file reports 0 role-scoped warnings, and `resolve --crew gemini-pro-crew --role envision
   --mode strict --no-event` exits 0 choosing `antigravity_gemini31_pro` (given headroom).
10. Tests required (fixture crews file, not the live one): strict × {coding, planning_review},
    flex × {coding, planning_review} including "skipped and named" and "all skipped → exit 3",
    bind × {coding, planning_review}, the unmapped-role case in each of the three modes, the
    `role_class` helper, `ROLE_CLASS_BY_ROLE` containing exactly the eight names above, and
    the doctor warning in both the coding-stage case and the planning-stage (no warning) case.
11. `docs/config.md`'s resolver rule table gains a row for this rule and loses the blanket
    "Gemini 3.1 Pro always refused" wording.

## C2 — `resolve` accepts `CREW ROLE` as positionals (shim substrate)

1. `lee-llm-router resolve CREW ROLE [options]` is equivalent to
   `lee-llm-router resolve --crew CREW --role ROLE [options]`. `--crew`/`--role` are no longer
   `required=True` in argparse; validation happens after parsing.
2. Exactly one form per invocation: positionals given together with `--crew` or `--role`,
   or one positional without the other, or more than two positionals → exit 3, kind `usage`,
   one-line message with the two accepted forms. Zero positionals and no flags → the same
   exit-3 usage error (not argparse's exit 2).
3. The fast-path parser (`_try_fast_resolve`) accepts the positional form; anything it does
   not understand still falls back to argparse. Both paths give byte-identical output for the
   same request.
4. Every shim (C3) uses the positional form: `lee-llm-router resolve $ARGUMENTS --mode flex
   --harness <tag> --json`, because `$ARGUMENTS` is the one substitution token all four
   harnesses support (verified in the binaries, see execution-log 2026-09-07 Sprint 4 open).

## C3 — Shims: generated, never hand-written

1. One template source: `src/lee_llm_router/templates/shims/crew.md.tmpl` (packaged data,
   listed in `pyproject.toml` package data if the build needs it). `src/lee_llm_router/shims.py`
   renders it per harness. No per-harness template files.
2. Four targets, harness tags fixed:
   | tag | path | form |
   |---|---|---|
   | `claude-code` | `~/.claude/commands/crew.md` | Claude Code slash command; frontmatter `description`, `argument-hint: <crew> <role>`, `allowed-tools: Bash(lee-llm-router:*)` |
   | `codex` | `~/.codex/prompts/crew.md` | Codex custom prompt; frontmatter `description`, `argument-hint` |
   | `omp` | `<project>/.omp/prompts/crew.md` (default project: cwd; `--project PATH` overrides) | OMP prompt template; frontmatter `description`, `argument-hint` |
   | `opencode` | `~/.config/opencode/command/crew.md` | OpenCode command file; frontmatter `description`, `agent: build` is NOT set (leave the user's default agent); no edit to `opencode.jsonc` |
   Home is `Path.home()` unless `LEE_LLM_ROUTER_SHIM_HOME` is set (tests use a tmp home).
   Directories that do not exist are created only by `--apply`.
3. Every rendered body is the same text apart from the harness tag: it tells the harness to
   run exactly `lee-llm-router resolve $ARGUMENTS --mode flex --harness <tag> --json`, then
   print worker, model, effort, headroom, reason from the JSON, and offer the exact
   `lee-llm-router dispatch --crew <crew> --role <role> --mode flex --harness <tag>
   --prompt-file <path>` line for the user to run. The shim never dispatches on its own, never
   invokes a provider binary, and never edits anything. One line `<!-- lee-llm-router shim
   v1 sha256=<hex> -->` is the marker: the hash covers the body below the marker line.
4. CLI:
   - `lee-llm-router shims install --dry-run` prints, for each target: the absolute path, the
     action it would take (`create` / `update` / `unchanged` / `refuse: not generated by
     lee-llm-router`), and the full content; touches nothing; exit 0.
   - `--apply` writes each target (creating parent directories), refusing to overwrite a file
     whose marker/hash does not match one we generated unless `--force`; exit 0 on success,
     exit 1 if any target was refused (the others are still written), exit 3 on usage error.
     `--dry-run` and `--apply` are mutually exclusive; neither given → usage exit 3.
   - `lee-llm-router shims diff` prints a unified diff per installed target that differs from
     the current render, `missing` for a target not installed, nothing for identical; exit 0
     if no drift, exit 1 if any drift or missing.
   - `--harness <tag>` (repeatable) limits install/diff to the named targets.
5. Parity: for the same crew and role, `resolve` output through each shim's command line is
   byte-identical after removing `ts`, `harness`, and `event_path` from the JSON; the four
   event records carry four distinct `harness` values and equal `route_id`.
6. Docs: `docs/config.md` gains a "Harness shims" section (targets table, marker, drift).

## C4 — Performance gate
`resolve` median of 5 cold runs on the live inputs stays under 50 ms. Re-measured at sprint
close; optimise only if it regresses above 50.


## What to check
1. C1: run the resolver against a scratch crews file you write under /tmp (via `--crews-file`) with a role-scoped worker in `author` and in `envision`; exercise strict/flex/bind in both; exercise an unmapped role. Compare against C1 §5–§7 exactly (exit codes, `kind`, wording, citation).
2. C2: positional vs flag parity and every usage-error case (§2).
3. C3: `shims install --dry-run --project /tmp` output; marker/hash; refuse/force/diff semantics by reading the code (you cannot write outside the sandbox) — or by using `LEE_LLM_ROUTER_SHIM_HOME` pointing at a sandbox-writable tmp if one exists.
4. Read the tests: do they cover the matrix the contracts require, or do they test the implementation's happy path?
5. Anything in the diff outside the packets' allowed files, any `builtins` tricks, any provider binary invoked by a shim, any write to `~/.config/opencode/opencode.jsonc`.
