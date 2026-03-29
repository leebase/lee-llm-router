# WHERE_AM_I - Lee LLM Router

> **Quick orientation for AI agents.** Last updated: 2026-03-29

---

## Current Project Phase

| Attribute | Value |
|-----------|-------|
| **Project** | Lee LLM Router |
| **Profile** | Python package and vendorable source reference |
| **Phase** | P4 - Harness Reliability |
| **Sprint** | Sprint 7 |
| **Status** | Complete |

---

## Last Session Summary

**2026-03-29 - Sprint 7 shipped and docs swept**

- Added a repo-local pi harness fixture and regression coverage for success and failure classes
- Hardened `codex_cli` and `doctor` so pi harness failures are validated earlier and typed more clearly
- Verified the path with full tests plus a user-style `LLMRouter.complete()` pi harness run
- Swept the docs so the published pi harness examples and doctor guidance match the shipped behavior

---

## Immediate Next Steps

### For the Human

1. Resume any downstream vendored-snapshot migration work that was blocked on pi harness reliability
2. Decide whether to add an optional public doctor smoke mode for CLI harness roles
3. Decide whether broader harness-aware planning should become the next sprint now that the pi path is stable

### For the AI Agent

1. Read `AGENTS.md`
2. Read `context.md`
3. Read `result-review.md`
4. Read `product-definition.md`
5. Execute the top-ranked next action from `context.md`

---

## Current Context

```
What's happening now:
- lee-llm-router is complete through Sprint 6
- Sprint 7 has shipped pi coding harness hardening, regression coverage, and validation guidance

Blockers:
- no current blocker inside this repo for pi harness reliability
- remaining decisions are about what follow-on work should build on the stable baseline

Recent decisions:
- keep this repo as the upstream improvement lane
- downstream repos can adopt via explicit vendored snapshots instead of a live runtime dependency
- treat existing empty export destinations as valid targets, and reserve `--force` for non-empty replacement
- pi-style subprocess harnesses should prefer a structured JSON contract when reliability matters
```

---

*Update this file at the end of every session.*
