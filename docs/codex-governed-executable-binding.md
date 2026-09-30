# Governed Codex executable binding

Governed `run` honors the existing `LEE_LLM_ROUTER_CODEX_BINARY` explicit harness override. Without it, a CLI already found on PATH retains the normal bare `codex` invocation. If PATH has no Codex CLI, the router uses the executable exact-name `~/.local/bin/codex` installed for the current user. It neither changes PATH nor installs a CLI. A missing, broken, directory or non-executable fallback produces a named dispatch error; an explicit override remains the operator’s choice and never silently falls back.

Model, effort, JSON usage capture, workspace-write sandbox and skip-git-repo-check flags remain unchanged. This fallback is limited to governed Codex dispatch; other harnesses and user profiles are unchanged.
