# Export path classification (P1-3)

Chief of Staff, 2026-09-16. Input to the P1-4 export check.

Externalizing the router requires that no **runtime** configuration value carry a
user-specific absolute path. It does **not** require erasing provenance. Citations recording
where a live crew block or a schema mapping was read from are historical evidence; rewriting
them to look portable would destroy the audit trail without making anything more portable.
Provenance is preserved, never laundered.

## The rule

An occurrence of a user-specific absolute path in shipped configuration is **provenance**,
and therefore allowed, if and only if it is one of:

1. **A comment line.** The path documents where a value came from and is never read.
2. **An `evidence_ref` value.** By contract in `crews.yaml`, `evidence_ref` cites the live
   source block a crew was migrated from. It is never dispatched, executed or opened.
3. **A schema documentation string** under `description`, `source_refs` or `source_paths`.
   These describe where a field's mapping was derived; they are not resolved at runtime.

Anything else is **runtime** and must not contain such a path.

The check is rule-based rather than a list of blessed line numbers, so it stays correct as
these files change.

## Measured state after P1-1 and P1-2

| File | Runtime | Provenance |
|---|---|---|
| `config/staffing/routes.yaml` | **0** | 9 comment lines |
| `config/staffing/crews.yaml` | **0** | 14 `evidence_ref` values, 1 comment line |
| `config/staffing/schema/attempt-record.schema.json` | **0** | 12 strings: `source_refs` ×6, `description` ×3, `source_paths` ×3 |
| `channels.yaml`, `policy.yaml`, `classes.yaml`, `terms.yaml` | **0** | 0 |

No runtime occurrence remains anywhere in shipped configuration. P1-1 removed the five
stage-worker directory paths; P1-2 removed the 33 harness binary paths.

## What this does not claim

The `evidence_ref` and schema citations still name paths that exist only on Lee's machine.
That is correct and intended: they record history, not configuration. A reader on another
machine cannot follow them, and does not need to — the value they carry is the assertion
that a specific block was migrated from a specific source at a specific time.
