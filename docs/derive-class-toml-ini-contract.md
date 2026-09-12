# Slice Contract: Mapping .toml and .ini Owned-Path Extensions to yaml-config

## Overview

This contract defines the delivery requirements for extending staffing class derivation in `src/lee_llm_router/staffing/derive_class.py` to support `.toml` and `.ini` file extensions in packet owned paths. Class derivation is a conservative, deterministic classification mechanism that inspects work packets and produces comparability and staffing metadata, specifically mapping owned file paths to canonical language classifications. At the slice baseline, `.yaml`, `.yml`, and `.json` map to the canonical `yaml-config` language category. This slice extends that mapping to `.toml` and `.ini` configuration formats, preventing `PacketClassError` when packets target project manifests or configuration files.

Routing intent is grounded in the closed eight-value language taxonomy established in D206 and enforced by `config/staffing/classes.yaml` and `config/staffing/schema/classes.schema.json`. The taxonomy comprises `python`, `typescript`, `shell`, `c`, `sql`, `yaml-config`, `markdown`, and `mixed`. TOML and INI configuration files, such as `pyproject.toml`, `Cargo.toml`, `tox.ini`, and `settings.ini`, belong to the `yaml-config` class because they share identical operational profiles and routing needs with YAML and JSON configurations. Deriving `yaml-config` for `.toml` and `.ini` routes tasks to the appropriate configuration staffing policies without fragmenting the catalog into unnecessary single-extension categories or triggering erroneous fallback behavior.

## Problem

Work packets passed to `derive_class()` or evaluated via the CLI command `python3 -m lee_llm_router.doctor staff --from-packet FILE` derive language exclusively from owned-path file extensions using the internal `_EXTENSION_LANGUAGES` table. At the slice baseline, `.yaml`, `.yml`, and `.json` are mapped to `yaml-config`, while `.toml` and `.ini` are absent. Consequently, a baseline packet owning a `.toml` or `.ini` file fails derivation with `PacketClassError: Owned path '...' has no supported language extension; language is derived only from owned-path extensions`.

This limitation was identified as an explicit follow-up concern during the D218 trial review (which introduced the `.json` mapping). Python repositories increasingly use `pyproject.toml` as standard project configuration, while legacy and tool configurations frequently use `tox.ini` or `.ini` files. Failing to classify these extensions blocks automated staffing workflows (`staff --from-packet`) and forces manual route specification.

The required outputs of this slice are:
1. Production code update in `src/lee_llm_router/staffing/derive_class.py` adding `".toml": "yaml-config"` and `".ini": "yaml-config"` to `_EXTENSION_LANGUAGES`.
2. Focused regression tests in `tests/test_staffing_derive_class.py` validating that standalone `.toml` and `.ini` paths derive `yaml-config`, multi-config combinations stay `yaml-config`, and cross-language paths derive `mixed`.
3. Contract and validation assets including `docs/derive-class-toml-ini-contract.md`, `journeys/derive_class_toml_ini_user_journeys_manifest.json`, and `tests/smoke_manifest.json`.

## Constraints

The implementation must adhere to the following architectural, operational, and validation constraints:
1. Closed Taxonomy Preservation (D206): The eight-value language taxonomy in `classes.yaml` is immutable for this slice. No new language values (such as `toml` or `ini`) may be added to `classes.yaml` or `classes.schema.json`.
2. Strict Extension Scope: In `src/lee_llm_router/staffing/derive_class.py`, modifications are strictly confined to adding `".toml": "yaml-config"` and `".ini": "yaml-config"` to `_EXTENSION_LANGUAGES`. No existing mappings, domain keywords, size estimation logic, or oracle parsers may be altered.
3. Multi-Path Consistency: Packets owning multiple configuration files with extensions across `.toml`, `.ini`, `.yaml`, `.yml`, and `.json` must resolve to `yaml-config`. If a configuration file is combined with an executable language (e.g., `.py`), language resolution must derive `mixed`.
4. Domain Tag Independence: Domain tags are derived from explicit `Domain:` fields or path keyword matching, never from language extension mappings. Adding `.toml` and `.ini` must not alter domain keyword resolution.
5. Deterministic Non-Dispatching Contract: `derive_class()` and `doctor staff` must remain pure and deterministic, never making network calls, invoking providers, or dispatching processes.
6. Validation Expectations: Verification requires passing the focused test suite (`pytest tests/test_staffing_derive_class.py`), maintaining a clean full test suite (`pytest`), adhering to formatting standards (`black --check` and `ruff check`), and executing live CLI validation via `python3 -m lee_llm_router.doctor staff --from-packet`.

## Acceptance Checks

- AC-1: The `_EXTENSION_LANGUAGES` table in `src/lee_llm_router/staffing/derive_class.py` contains `".toml": "yaml-config"`, and `derive_class()` derives `language="yaml-config"` for a packet whose owned paths contain a `.toml` file.
- AC-2: The `_EXTENSION_LANGUAGES` table in `src/lee_llm_router/staffing/derive_class.py` contains `".ini": "yaml-config"`, and `derive_class()` derives `language="yaml-config"` for a packet whose owned paths contain an `.ini` file.
- AC-3: A packet whose owned paths include multiple configuration formats (any combination of `.toml`, `.ini`, `.yaml`, `.yml`, and `.json`) resolves to `language="yaml-config"` and does not derive `"mixed"`.
- AC-4: A packet whose owned paths include a `.toml` or `.ini` file alongside a file of a different language category (such as `.py` or `.sh`) resolves to `language="mixed"`.
- AC-5: The CLI command `python3 -m lee_llm_router.doctor staff --from-packet <packet> --json` executes successfully with exit code 0 on packets owning `.toml` or `.ini` paths, outputting a JSON derivation record containing `language="yaml-config"` without raising `PacketClassError`.
- AC-6: The canonical 8-value language taxonomy (`python`, `typescript`, `shell`, `c`, `sql`, `yaml-config`, `markdown`, `mixed`) remains unchanged in `config/staffing/classes.yaml`, and domain tag keyword matching behaves identically.
