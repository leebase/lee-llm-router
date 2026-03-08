# WHERE_AM_I - Lee LLM Router

> **Quick orientation for AI agents.** Last updated: 2026-03-08

---

## Current Project Phase

| Attribute | Value |
|-----------|-------|
| **Project** | Lee LLM Router |
| **Profile** | Python package and vendorable source reference |
| **Phase** | P3 - Self-Contained Adoption |
| **Sprint** | Sprint 6 |
| **Status** | Complete |

---

## Last Session Summary

**2026-03-08 - Sprint 6 complete**

- Added `export-source` CLI for vendored package snapshots
- Export now emits provenance metadata (`.lee_llm_router_export.json`)
- Downstream architecture direction shifted from required runtime dependency to explicit snapshot adoption
- Validation passed: `71` tests green plus CLI doctor/export workflow checks

---

## Immediate Next Steps

### For the Human

1. Decide whether LeeClaw should vendor the router under a dedicated vendor path or merge it into its primary package tree
2. Choose whether future downstream adoption should prefer package releases, vendored snapshots, or both
3. Decide whether Sprint 7 should focus on downstream sync tooling or on consumer migration work

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
- vendored snapshot export is now a first-class downstream adoption path

Blockers:
- None in this repo
- downstream migration work remains in consumer repos

Recent decisions:
- keep this repo as the upstream improvement lane
- downstream repos can adopt via explicit vendored snapshots instead of a live runtime dependency
```

---

*Update this file at the end of every session.*
