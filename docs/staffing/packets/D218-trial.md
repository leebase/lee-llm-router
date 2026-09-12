# Packet D218-trial — `derive_class.py` `.json` owned-path extension

- Kind: `impl`
- Declared size: 2 files, at most 40 changed lines
- Owned paths: `src/lee_llm_router/staffing/derive_class.py`,
  `tests/test_staffing_derive_class.py`
- Requirement: `derive_class`'s owned-path language table (`_EXTENSION_LANGUAGES`,
  `src/lee_llm_router/staffing/derive_class.py:55`) has no entry for the `.json` extension,
  so `derive_class()`/`staff --from-packet` raises `PacketClassError` ("has no supported
  language extension") for any packet whose owned paths include a `.json` file (for example
  a JSON schema file). This was hit twice during Phase 4 Group A (P4-2, P4-2b) and worked
  around each time by staffing directly instead of `--from-packet`; recorded, not fixed, in
  `docs/staffing/needs-lee.md` ("Phase 4 Group A" section). Fix it now: add
  `".json": "yaml-config"` to `_EXTENSION_LANGUAGES`, mapping JSON files into the existing
  `yaml-config` language value (the closed eight-value taxonomy in
  `config/staffing/classes.yaml`/`config/staffing/schema/classes.schema.json` has no
  standalone JSON value and none may be added — `.yaml`/`.yml` already map to `yaml-config`
  for the same reason: JSON and YAML are both structured data/config formats). Do not touch
  any other extension mapping, the domain-keyword table, or any other function in this file.
- Oracle: `.venv/bin/pytest -q tests/test_staffing_derive_class.py`
- Review: independent review required after the oracle passes.
- Commit: `fix(staffing): map .json owned paths to yaml-config in derive_class`

## Forbidden paths

Any file not listed in Owned paths above, including `classes.yaml`,
`classes.schema.json`, `catalog.py`, or any other staffing module.

## Required evidence

- Full output of the Oracle command above (all tests passing).
- Full suite: `.venv/bin/python -m pytest -q` (report exact pass/fail counts).
- `.venv/bin/black --check` and `.venv/bin/ruff check` on every touched file.
- One live invocation of `staff --from-packet` (or `catalog explain` equivalent) against a
  packet whose owned paths include a `.json` file, showing it no longer raises
  `PacketClassError`, pasted into your report.

## Stop / escalation condition

Stop and report back without guessing if a `.json` owned path should ever resolve to
`"mixed"` instead of `"yaml-config"` in some case you find — do not invent a rule finer than
the one stated above; report the ambiguous case instead.
