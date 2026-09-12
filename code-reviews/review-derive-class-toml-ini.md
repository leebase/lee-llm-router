# Code Review: Staffing Class Derivation for .toml and .ini Extensions

- **Date**: 2026-09-12
- **Reviewer**: Antigravity (Independent Slice Reviewer)
- **Slice**: `derive-class-toml-ini`
- **Scope**:
  - `src/lee_llm_router/staffing/derive_class.py`
  - `tests/test_staffing_derive_class.py`
  - `README.md`
  - `docs/derive-class-toml-ini-contract.md`
  - `plans/derive-class-toml-ini-implementation-plan.md`
  - `journeys/derive_class_toml_ini_user_journeys_manifest.json`
  - `artifacts/user-test/derive_class_toml_ini/result.json`
  - `artifacts/user-test/derive_class_toml_ini/findings-log.md`
- **Verdict**: **PASS** (Clean, 0 findings at or above severity threshold High; 0 findings overall)

---

## Checks Run

The following commands were executed or evaluated against the slice deliverables. A focused re-executable test was run directly by the reviewer, and the preserved system-validator records from earlier pipeline stages were reconciled in accordance with the Agent-Orch validator authority policy.

| Command | Execution Source | Exit Code | Result Summary |
|---------|------------------|-----------|----------------|
| `python3 -m pytest tests/test_staffing_derive_class.py -q` | Worker Re-executable Check | 0 | 28 passed in 0.30s |
| `python3 -m compileall tests/test_staffing_derive_class.py` | Preserved System Validator (`step_04_author_slice_tests`, validator 1) | 0 | Compiling 'tests/test_staffing_derive_class.py'... (duration: 0.128023s) |
| `python3 -m pytest tests/test_staffing_derive_class.py` | Preserved System Validator (`step_05_implement_slice`, validator 1) | 0 | 28 passed, 0 failed, 0 skipped in 0.32s (duration: 1.134916s) |
| `python3 -m pytest tests/test_staffing_derive_class.py` | Preserved System Validator (`step_07_repair_and_verify_slice`, validator 1) | 0 | 28 passed, 0 failed, 0 skipped in 0.32s (duration: 1.057359s) |
| `BLACK_NUM_WORKERS=1 python3 -m black --check src/lee_llm_router/staffing/derive_class.py tests/test_staffing_derive_class.py` | Preserved System Validator (`step_07_repair_and_verify_slice`, validator 2) | 0 | All done! 2 files would be left unchanged (duration: 0.301396s) |
| `python3 -m ruff check src/lee_llm_router/staffing/derive_class.py tests/test_staffing_derive_class.py` | Preserved System Validator (`step_07_repair_and_verify_slice`, validator 3) | 0 | All checks passed! (duration: 0.028783s) |
| `python3 -m compileall src/lee_llm_router/staffing/derive_class.py tests/test_staffing_derive_class.py` | Preserved System Validator (`step_07_repair_and_verify_slice`, validator 4) | 0 | Compiling production and test files... (duration: 0.031417s) |

### Reconciled System Validator Details

1. **Test Compilation (`step_04_author_slice_tests`, validator 1)**:
   - Evidence Hash: `8c3f92e5084e7d859a428a67fc6106dbb999eb15baaf8f1b9dee119d747fa8d7`
   - Exit Status: `0`, Passed: `True`, Duration: `0.128023s`
   - Output: `Compiling 'tests/test_staffing_derive_class.py'...\n`

2. **Implementation Pytest (`step_05_implement_slice`, validator 1)**:
   - Evidence Hash: `cd6f873234e316571aba2d2b6a437be5b6d7aae6390f39a14eeeaae830d40850`
   - Exit Status: `0`, Passed: `True`, Duration: `1.134916s`
   - Test Counts: `28 passed, 0 failed, 0 skipped` in `0.32s`

3. **Repair and Verify Pytest (`step_07_repair_and_verify_slice`, validator 1)**:
   - Evidence Hash: `a19a1167041699c8ff6da3bf224eee380cba6ec3968dbeb45879e95617b7aa85`
   - Exit Status: `0`, Passed: `True`, Duration: `1.057359s`
   - Test Counts: `28 passed, 0 failed, 0 skipped` in `0.32s`

4. **Code Formatting Check (`step_07_repair_and_verify_slice`, validator 2)**:
   - Evidence Hash: `92338bc62d289f313d874b8cb1f8f07d2980051dfc22981f7215502926e5a1b8`
   - Exit Status: `0`, Passed: `True`, Duration: `0.301396s`
   - Output: `2 files would be left unchanged.`

5. **Linter Check (`step_07_repair_and_verify_slice`, validator 3)**:
   - Evidence Hash: `3976acd94e7f4f8deab7e98e5b743e0e54b0f945d69552d11451ba7afd368952`
   - Exit Status: `0`, Passed: `True`, Duration: `0.028783s`
   - Output: `All checks passed!`

6. **Bytecode Compilation (`step_07_repair_and_verify_slice`, validator 4)**:
   - Evidence Hash: `0d9681520895e2bbff47f399092e80a445fb22a9266cfbaf5d0d23bec3021bdd`
   - Exit Status: `0`, Passed: `True`, Duration: `0.031417s`

---

## Acceptance Checks Against Contract

The implementation was checked directly against `docs/derive-class-toml-ini-contract.md`:

- **AC-1 (TOML Mapping)**: `src/lee_llm_router/staffing/derive_class.py` contains `".toml": "yaml-config"` in `_EXTENSION_LANGUAGES`. Calling `derive_class()` on a packet owning `pyproject.toml` derives `language="yaml-config"`. Verified by test `test_toml_owned_path_maps_to_yaml_config` and User Journey 1. **[PASS]**
- **AC-2 (INI Mapping)**: `src/lee_llm_router/staffing/derive_class.py` contains `".ini": "yaml-config"` in `_EXTENSION_LANGUAGES`. Calling `derive_class()` on a packet owning `tox.ini` derives `language="yaml-config"`. Verified by test `test_ini_owned_path_maps_to_yaml_config` and User Journey 2. **[PASS]**
- **AC-3 (Multi-Config Homogeneity)**: Packets owning multiple configuration files across `.toml`, `.ini`, `.yaml`, `.yml`, and `.json` derive `language="yaml-config"` rather than `"mixed"`. Verified by tests `test_toml_alongside_ini_stays_yaml_config`, `test_multi_config_formats_stay_yaml_config`, and User Journey 3. **[PASS]**
- **AC-4 (Heterogeneous Config and Code)**: Packets combining `.toml` or `.ini` with source code extensions (`.py`, `.sh`) derive `language="mixed"`. Verified by test `test_toml_and_ini_alongside_code_resolves_to_mixed` and User Journey 4. **[PASS]**
- **AC-5 (CLI Execution)**: `python3 -m lee_llm_router.doctor staff --from-packet <packet> --json` succeeds with exit status 0 for packets owning `.toml` and `.ini` files, emitting valid derivation records with `language="yaml-config"` without raising `PacketClassError`. Verified by live User Journeys 1, 2, 3, 4, and 5. **[PASS]**
- **AC-6 (Closed Taxonomy and Domain Tag Independence)**: The eight-value language taxonomy (`python`, `typescript`, `shell`, `c`, `sql`, `yaml-config`, `markdown`, `mixed`) is unchanged in `config/staffing/classes.yaml`. Domain tag keyword matching operates independently on owned path substrings regardless of configuration extensions. Verified by test `test_toml_ini_domain_tags_remain_independent` and User Journey 5. **[PASS]**

---

## Findings

| ID | Severity | File | Location | Problem | Proposed Fix |
|----|----------|------|----------|---------|--------------|
| — | None | — | — | No defects found. | None required. |

There are **0 Critical**, **0 High**, **0 Medium**, and **0 Low** findings. The slice implementation meets all specifications cleanly and does not introduce regressions or technical debt.

---

## Lens Notes

This review covers both halves of the slice: the code implementation and the user-facing verification evidence recorded in `artifacts/user-test/derive_class_toml_ini/findings-log.md` and `result.json`.

### Evaluation of User-Facing Defects and Simulation Log

In `artifacts/user-test/derive_class_toml_ini/findings-log.md`, the evaluator reviewed all recording cycles for the slice:
- **No Product Defects Recorded**: In both Run 003dd9f505b8 and prior evaluation runs, 0 product findings were reproduced (`findings: []`).
- **User Simulation History Analysis**: In the initial simulation attempt for this slice, evaluator route execution and repository identity succeeded (`verified_true`), but the user simulation gate's automated claim re-execution failed because test packet paths were relative to a temporary directory rather than absolute. In Attempt 2 and Run 003dd9f505b8 Attempt 1, absolute paths were supplied, and all 5 user journeys executed cleanly and reliably against `python3 -m lee_llm_router.doctor staff`.
- **Honest Repair vs. Defect Suppression**: The repair in Attempt 2 addressed the harness path qualification without altering product behavior or relaxing assertions. No defects were suppressed, masked, or bypassed. Every journey verified real CLI behavior against the production entry point:
  1. Standalone `.toml` packet derived `yaml-config`.
  2. Standalone `.ini` packet derived `yaml-config`.
  3. Five-way homogeneous config (`.toml`, `.ini`, `.yaml`, `.yml`, `.json`) derived `yaml-config`.
  4. Heterogeneous packet (`.toml` + `.py`) derived `mixed`.
  5. Closed taxonomy verification confirmed the exact 8 canonical choices in `staff --help`, while an INI packet with an `authority` path keyword derived `yaml-config` with an owned-path `authority` domain tag.

### Architectural and Quality Lenses

| Lens | Findings | Evaluation Notes & Justification |
|------|----------|----------------------------------|
| **Correctness** | None | Mapping `.toml` and `.ini` to `yaml-config` in `_EXTENSION_LANGUAGES` correctly maps project configuration files to the canonical configuration class. Suffix normalization via `Path(path).suffix.lower()` ensures case-insensitivity. Distinct language reduction preserves single-category resolution or reduces multi-language sets to `mixed`. |
| **User-Facing Defects** | None | `artifacts/user-test/derive_class_toml_ini/findings-log.md` records 0 product defects across all 5 user journeys. All journeys passed against the live `python3 -m lee_llm_router.doctor staff` interface without workarounds, monkeypatching, or suppressed failures. |
| **Trust Boundary** | None | `derive_class()` and `doctor staff` remain pure and deterministic. The function performs only local Markdown parsing and dictionary lookups against `classes.yaml`. It never invokes network providers, makes external calls, or executes arbitrary code. Unsupported extensions fail closed with `PacketClassError`. |
| **Error Handling** | None | Unknown or missing extensions continue to raise `PacketClassError` immediately. Malformed packet structures, invalid size declarations, or unparseable fields fail closed. |
| **Observability** | None | Derivation records output complete provenance: `domain_source`, `domain_matches`, `declared_size`, `oracle`, `review`, and `class_key`. The `class_key` property reflects the canonical 5-part evidence key (`role/oracle/tags/size/language`). |
| **Tests** | None | 6 comprehensive regression tests in `tests/test_staffing_derive_class.py` thoroughly test standalone `.toml`, standalone `.ini`, homogeneous multi-config, heterogeneous code+config, and domain tag isolation. All 28 tests in the module pass in 0.30s. |
| **Docs** | None | `README.md` (lines 158–170), `docs/derive-class-toml-ini-contract.md`, and `plans/derive-class-toml-ini-implementation-plan.md` clearly document the `.toml` and `.ini` mapping to `yaml-config`, multi-path resolution rules, and closed taxonomy constraints. |
| **Simplicity** | None | The production diff is the absolute minimal change necessary: exactly 2 entries added to the internal `_EXTENSION_LANGUAGES` mapping. No schema alterations, no taxonomy expansion, and no auxiliary dependencies were introduced. |

---

## Verdict

**PASS**. The slice satisfies all contract requirements (AC-1 through AC-6), adheres strictly to repository guidelines, passes all tests and lint checks cleanly, and exhibits zero user-facing or architectural defects. The machine-readable companion artifact is written to `code-reviews/review-derive-class-toml-ini.verdict.json`.
