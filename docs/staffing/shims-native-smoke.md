# Shims Native Expansion Smoke Report (Packet D224-1)

- Authority: Chief-of-staff `decisions.md` D224 (Lee: "it is supposed to work in all my harnesses: codex, claude, omp, pi, and opencode")
- Packet: `docs/staffing/packets/D224-1-five-harness-shims.md`
- Date: 2026-09-12
- Scope: Five harnesses (`claude-code`, `codex`, `omp`, `opencode`, `pi`), explicit `$ARGUMENTS` binding in `crew.md.tmpl` and `supervise.md.tmpl`, native non-interactive expansion smoke tests.

---

## 1. Summary of Harness Argument & Template Mechanisms

### Claude Code (`claude-code`)
- Target path: `<home>/.claude/commands/<command>.md`
- Invocation: `/supervise <plan-path> [crew NAME | auto]`, `/crew <auto|NAME>`
- Template format: Markdown with YAML frontmatter (`description`, `argument-hint`, `allowed-tools: Bash(lee-llm-router:*)`).
- Argument substitution: `$ARGUMENTS` is substituted with the supplied argument string.
- Non-interactive mode: `claude -p "<prompt>"` expands slash commands and executes them.

### Codex (`codex`)
- Target path: `<home>/.codex/prompts/<command>.md`
- Invocation: `/prompts:supervise <plan-path> [crew NAME | auto]`, `/prompts:crew <auto|NAME>`
- **Namespace note**: Codex namespaces custom prompts under `/prompts:<name>`. Its user-facing invocation is `/prompts:supervise <args>` and `/prompts:crew <args>`, not bare `/supervise`. This is recorded in the rendered frontmatter/description of the Codex shim and noted in the shim header so documentation does not falsely claim bare `/supervise` works in Codex.
- Template format: Markdown with YAML frontmatter (`description`, `argument-hint`).
- Argument substitution: Codex substitutes `$ARGUMENTS` (as well as `$1`, `$2`, etc.).
- Non-interactive mode: `codex exec "/prompts:<name> <args>"` expands custom prompts and processes them.

### Oh My Pi (`omp`)
- Target path: `<project>/.omp/prompts/<command>.md`
- Invocation: `/supervise <plan-path> [crew NAME | auto]`, `/crew <auto|NAME>`
- Template format: Markdown with YAML frontmatter (`description`, `argument-hint`).
- Argument substitution verification (from binary analysis of `omp`):
  OMP inspects template content for inline placeholders matching:
  ```js
  TOi = /\$(?:ARGUMENTS|@(?:\[\d+(?::\d*)?\])?|\d+)/;
  wOi = /\{\{[\s\S]*?(?:\b(?:arguments|ARGUMENTS|args)\b|\barg\s+[^}]+)[\s\S]*?\}\}/;
  ```
  When inline placeholders are present, it substitutes `$ARGUMENTS` or `$@` with the joined arguments string.
  When **no** inline placeholder is present in the template, OMP's `appendInlineArgsFallback` appends the unused arguments to the end of the template (`${e}\n\n${t}`).
  With explicit `$ARGUMENTS` binding near the top of the templates, OMP substitutes `$ARGUMENTS` in-place and does not append redundant arguments.
- Non-interactive mode: `omp -p "/<name> <args>"` expands prompt templates.

### Pi (`pi`)
- Target path: `<home>/.pi/agent/prompts/<command>.md`
- Invocation: `/supervise <plan-path> [crew NAME | auto]`, `/crew <auto|NAME>`
- Template format: Markdown with optional `description` and `argument-hint` YAML frontmatter.
- Argument substitution verification (from Pi prompt template documentation at `~/.npm-global/lib/node_modules/@earendil-works/pi-coding-agent/docs/prompt-templates.md`):
  Pi prompt templates support positional arguments (`$1`, `$2`), joined arguments (`$@` or `$ARGUMENTS`), and default/slicing syntax.
- Non-interactive mode: `pi -p "/<name> <args>"` expands prompt templates.

### OpenCode (`opencode`)
- Target path: `<home>/.config/opencode/command/<command>.md`
- Invocation:
  - Interactive mode (TUI): `/supervise <args>`, `/crew <args>`
  - Non-interactive mode (CLI): `opencode run --command supervise <args>`
- Template format: Markdown with optional YAML frontmatter (`description`, `agent`, `model`, etc.).
- Argument substitution: OpenCode substitutes `$ARGUMENTS` and `$1`, `$2` in custom commands.
- Non-interactive positional behavior (finding):
  When invoked as `opencode run "/argecho /tmp/plan-x.md auto"`, OpenCode does not intercept the slash command in positional mode; it treats the string as a natural-language prompt directed to its default agent (`build`), which attempts to run `/argecho` as a shell command.
  When invoked via `opencode run --command argecho <args>`, OpenCode correctly loads the command template from `.config/opencode/command/` and expands `$ARGUMENTS`.
  Per D224-1 instructions, this non-interactive limitation is documented with evidence rather than asserted around.

---

## 2. Native Expansion Smoke Results

Each test installed a throwaway template `argecho.md` into an isolated temporary home or project directory with the harness's frontmatter shape and exact body:
```markdown
Reply with one line and nothing else: ARGS=<$ARGUMENTS>
```
and invoked the harness with arguments `/tmp/plan-x.md auto`.

### 1. Claude Code (`claude-code`)
- **Command**:
  ```bash
  claude --model claude-haiku-4-5-20251001 -p "/argecho /tmp/plan-x.md auto"
  ```
- **Exit code**: 0
- **Model used**: `claude-haiku-4-5-20251001`
- **Timeout**: 120 s
- **Exact reply (stdout)**:
  ```
  ARGS=</tmp/plan-x.md auto>
  ```
- **Status**: PASSED. Template expanded `$ARGUMENTS` to `/tmp/plan-x.md auto`.

### 2. OpenAI Codex (`codex`)
- **Command**:
  ```bash
  codex exec "/prompts:argecho /tmp/plan-x.md auto"
  ```
- **Exit code**: 0
- **Model used**: Default (`gpt-5.6-luna`)
- **Timeout**: 120 s
- **Exact reply (stdout)**:
  ```
  codex
  ARGS=</tmp/plan-x.md auto>
  tokens used
  24,737
  ```
- **Status**: PASSED. Custom prompt expanded `$ARGUMENTS` under the `/prompts:` namespace.

### 3. Oh My Pi (`omp`)
- **Command**:
  ```bash
  omp -p "/argecho /tmp/plan-x.md auto"
  ```
- **Exit code**: 0
- **Model used**: Default
- **Timeout**: 120 s
- **Exact reply (stdout)**:
  ```
  ARGS=</tmp/plan-x.md auto>
  ```
- **Status**: PASSED. Prompt template expanded `$ARGUMENTS` via project directory `.omp/prompts/argecho.md`.

### 4. Pi (`pi`)
- **Command**:
  ```bash
  pi -p "/argecho /tmp/plan-x.md auto"
  ```
- **Exit code**: 0
- **Model used**: Default
- **Timeout**: 120 s
- **Exact reply (stdout)**:
  ```
  ARGS=</tmp/plan-x.md auto>
  ```
- **Status**: PASSED. Global prompt template expanded `$ARGUMENTS` via `~/.pi/agent/prompts/argecho.md`.

### 5. OpenCode (`opencode`)
- **Command (Positional invocation per prompt)**:
  ```bash
  opencode run "/argecho /tmp/plan-x.md auto"
  ```
- **Exit code**: 0
- **Model used**: Default (`gpt-5.6-luna`)
- **Timeout**: 120 s
- **Exact reply (stdout)**:
  ```
  I’ll verify the plan file and whether `/argecho` is available, then run the requested command if the inputs are present.
  `/tmp/plan-x.md` does not exist, so `/argecho /tmp/plan-x.md auto` could not be run.
  ```
- **Stderr snippet**:
  ```
  > build · gpt-5.6-luna
  $ ls -l "/tmp/plan-x.md" && command -v argecho || true
  ls: cannot access '/tmp/plan-x.md': No such file or directory
  ```
  When invoked with `--command argecho`, OpenCode successfully expands `.config/opencode/command/argecho.md` and substitutes `$ARGUMENTS`.

---

## 3. Verification Evidence

### Pytest Oracle Output (Skipped Native Smokes)
```
$ python3 -m pytest -q tests/test_shims.py tests/test_shims_parity.py tests/test_shims_native_smoke.py
.............................sssss                                       [100%]
29 passed, 5 skipped, 1 warning in 12.44s
```

### Pytest Live Native Smoke Output (`LEE_LLM_ROUTER_NATIVE_SMOKE=1`)
```
$ LEE_LLM_ROUTER_NATIVE_SMOKE=1 python3 -m pytest -q tests/test_shims_native_smoke.py -rs
....s                                                                    [100%]
=========================== short test summary info ============================
SKIPPED [1] tests/test_shims_native_smoke.py:268: OpenCode non-interactive mode ('opencode run') does not expand slash command templates from positional message; exit=0, stdout='`argecho` is not installed or available on `PATH`. `/tmp/plan-x.md` exists but only contains `# Plan X`.'
4 passed, 1 skipped, 1 warning in 94.77s (0:01:34)
```

### Black & Ruff Checks on Owned Files
```
$ python3 -m black --check src/lee_llm_router/shims.py tests/test_shims.py tests/test_shims_parity.py tests/test_shims_native_smoke.py
All done! ✨ 🍰 ✨
4 files would be left unchanged.

$ python3 -m ruff check src/lee_llm_router/shims.py tests/test_shims.py tests/test_shims_parity.py tests/test_shims_native_smoke.py
All checks passed!
```

### Shims Diff Against Temp Home Showing Five Targets
```
$ LEE_LLM_ROUTER_SHIM_HOME=/tmp/tmp_home lee-llm-router shims diff --project /tmp/tmp_proj
missing: /tmp/tmp_home/.claude/commands/crew.md
missing: /tmp/tmp_home/.codex/prompts/crew.md
missing: /tmp/tmp_proj/.omp/prompts/crew.md
missing: /tmp/tmp_home/.config/opencode/command/crew.md
missing: /tmp/tmp_home/.pi/agent/prompts/crew.md
```
And for supervise:
```
$ LEE_LLM_ROUTER_SHIM_HOME=/tmp/tmp_home lee-llm-router shims diff --command supervise --project /tmp/tmp_proj
missing: /tmp/tmp_home/.claude/commands/supervise.md
missing: /tmp/tmp_home/.codex/prompts/supervise.md
missing: /tmp/tmp_proj/.omp/prompts/supervise.md
missing: /tmp/tmp_home/.config/opencode/command/supervise.md
missing: /tmp/tmp_home/.pi/agent/prompts/supervise.md
```
After installation into the temp home, `shims diff` exits 0 cleanly with empty output.

