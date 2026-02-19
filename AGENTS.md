# Repository Guidelines

Lee LLM Router is a Python 3.10+ package that centralizes LLM routing, telemetry, and CLI tooling for LeeClaw and Meridian partners.

## Project Structure & Module Organization
- `src/lee_llm_router/` holds production code; focus on `router.py`, `policy.py`, `telemetry.py`, and `providers/` when altering routing, governance, or adapters.
- `tests/` mirrors the module layout. Extend the relevant `test_*.py` or add a new one using fixtures from `tests/conftest.py`.
- `docs/` contains user-facing references. Update `docs/config.md` or `docs/providers.md` whenever schemas or adapter behavior shift.
- Read and update `context.md`, `result-review.md`, and `sprint-plan.md` whenever work changes shared state.

## Build, Test, and Development Commands
```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"            # install runtime + tooling deps
pytest                               # run the full suite (54 tests today)
pytest tests/test_router.py -v       # focused router coverage
python -m build                      # create wheel + sdist for release smoke
lee-llm-router doctor --config tests/fixtures/llm_test.yaml
```

## Coding Style & Naming Conventions
- Run Black (line length 88) and Ruff on `src/` before review.
- Always import `annotations` from `__future__`, include type hints, and write Google-style docstrings for public functions.
- Classes use `PascalCase`, functions `snake_case`, constants `UPPER_SNAKE`, and protocols end with `Protocol`. Provider exceptions must chain into `LLMRouterError` with an appropriate `FailureType`.

## Testing Guidelines
- Pytest is required; name files and functions `test_*`. Prefer `MockProvider` for deterministic routing, `tmp_path` for filesystem checks, and `caplog` for telemetry assertions.
- Cover async paths with `await router.complete_async()` tests, and capture CLI behavior via the `doctor` and `trace` subcommands.
- Do not merge without `pytest` green locally; add regression tests for every bug fix or new CLI switch.

## Commit & Pull Request Guidelines
- Follow existing history: `feat(sprint5): async fallback telemetry [Phase 2]`. Include sprint/phase context plus a succinct summary.
- Commits should bundle code, docs, and tests for the task, plus updates to `context.md` and `result-review.md` when required.
- Pull requests must link to backlog items, summarize risks, and list verification steps (commands + expected status). Attach CLI output or screenshots whenever behavior or docs change.

## Security & Configuration Tips
- Keep secrets in env vars (`OPENROUTER_API_KEY`, etc.) and reference them via `api_key_env` inside YAML configs; never commit sample keys.
- Generate starter configs with `lee-llm-router template > config/llm.yaml`, then run `lee-llm-router doctor --config <path>` before publishing changes.
